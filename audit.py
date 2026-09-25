"""Збір відповідей LLM на небрендовані запити та метрики AI-видимості брендів."""

import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from urllib.parse import urlparse

import httpx
import pandas as pd

from design import INDUSTRIES

API_URL = "https://openrouter.ai/api/v1/chat/completions"
CATALOG_URL = "https://openrouter.ai/api/v1/models"

RETRYABLE_STATUSES = (408, 429, 500, 502, 503, 504)

GEO_PREFIX = {"uk": "Я живу в Україні. ", "en": "I live in Ukraine. "}

BANK_BRANDS = INDUSTRIES["bank"]["brands"]
BANK_BRAND_DOMAINS = INDUSTRIES["bank"]["domains"]
BANK_QUERIES = [(intent, uk) for intent, uk, _ in INDUSTRIES["bank"]["queries"]]

DOMAIN_TYPES = {
    "wikipedia": ["wikipedia.org"],
    "regulator_gov": ["bank.gov.ua", "gov.ua", "fg.gov.ua"],
    "fin_portal": [
        "minfin.com.ua", "finance.ua", "bankchart.com.ua", "finance.liga.net", "prostobank.ua", "banker.ua",
        "financer.com.ua", "forinsurer.com", "banksrating.com.ua", "uba.top", "inventure.com.ua", "kosht.media",
    ],
    "media": [
        "epravda.com.ua", "pravda.com.ua", "forbes.ua", "liga.net", "ain.ua", "dou.ua",
        "nv.ua", "unian.ua", "ukrinform.ua", "interfax.com.ua", "delo.ua", "mind.ua", "suspilne.media",
        "rbc.ua", "focus.ua", "obozrevatel.com", "24tv.ua", "thepage.ua", "ua.news", "today.ua", "informator.ua",
    ],
    "social_forum": ["reddit.com", "facebook.com", "youtube.com", "t.me", "instagram.com", "x.com", "tiktok.com"],
}

JUDGE_PROMPT = """Ти аналізуєш відповідь ШІ-асистента на споживчий запит.
Знайди всі згадані комерційні бренди (компанії, сервіси) і для кожного оціни ставлення до нього у відповіді.

Поверни лише JSON такого вигляду:
{"brands": [{"name": "<назва як у тексті>", "sentiment": -1 | 0 | 1, "recommended": true | false}]}

sentiment: 1 — позитивно, 0 — нейтрально або змішано, -1 — негативно.
recommended: true, якщо відповідь прямо радить цей бренд користувачу.
Якщо брендів немає, поверни {"brands": []}."""


JUDGE_SCHEMA = {
    "name": "brand_judgement",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["brands"],
        "properties": {
            "brands": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["name", "sentiment", "recommended"],
                    "properties": {
                        "name": {"type": "string"},
                        "sentiment": {"type": "integer", "enum": [-1, 0, 1]},
                        "recommended": {"type": "boolean"},
                    },
                },
            }
        },
    },
}


def build_queries(industry, raw_queries):
    return [
        {"query_id": f"{industry}-{i:02d}", "industry": industry, "intent": intent, "text": text}
        for i, (intent, text) in enumerate(raw_queries, start=1)
    ]


def build_industry_queries(industry, lang):
    text_index = {"uk": 1, "en": 2}[lang]
    return build_queries(industry, [(q[0], q[text_index]) for q in INDUSTRIES[industry]["queries"]])


def build_tasks(model_configs, queries, repeats, lang="uk", geo=True):
    return [
        {
            "model": cfg["model"],
            "web_search": cfg["web_search"],
            "web_plugin": cfg["web_search"] and not cfg.get("native_search", False),
            "query_id": q["query_id"],
            "industry": q["industry"],
            "intent": q["intent"],
            "lang": lang,
            "geo": geo,
            "repeat": r,
            "prompt": (GEO_PREFIX[lang] if geo else "") + q["text"],
        }
        for cfg in model_configs
        for q in queries
        for r in range(1, repeats + 1)
    ]


def task_key(t):
    return (t["model"], t["web_search"], t["query_id"], t["lang"], t["geo"], t["repeat"])


def fetch_catalog_prices():
    data = httpx.get(CATALOG_URL, timeout=30).json()["data"]
    return {
        m["id"]: {
            "prompt": float(m["pricing"]["prompt"]),
            "completion": float(m["pricing"]["completion"]),
            "web_search": float(m["pricing"].get("web_search") or 0),
        }
        for m in data
    }


def estimate_cost(tasks, prices, prompt_tokens=60, completion_tokens=1000, web_context_tokens=45000):
    """Груба оцінка. Веб-плагін додає плату за пошук і токени знайдених сторінок у вхід;
    обсяг цих токенів відкалібровано за димовим тестом 2026-09-18 (≈$0.10 за виклик gpt-5.6-sol)."""
    rows = []
    for t in tasks:
        p = prices[t["model"]]
        cost = prompt_tokens * p["prompt"] + completion_tokens * p["completion"]
        if t["web_search"]:
            cost += p["web_search"]
        if t["web_plugin"]:
            cost += web_context_tokens * p["prompt"]
        rows.append({"model": t["model"], "web_search": t["web_search"], "cost_usd": cost})
    df = pd.DataFrame(rows)
    return df.groupby(["model", "web_search"]).agg(calls=("cost_usd", "size"), cost_usd=("cost_usd", "sum")).round(2)


def post_chat(client, payload, attempts=4):
    for attempt in range(attempts):
        resp = client.post(API_URL, json=payload)
        if resp.status_code == 200:
            body = resp.json()
            if "error" not in body:
                return body
        elif resp.status_code not in RETRYABLE_STATUSES:
            raise RuntimeError(f"OpenRouter {resp.status_code}: {resp.text[:300]}")
        time.sleep(2 ** attempt * 2)
    raise RuntimeError(f"OpenRouter не відповів після {attempts} спроб: {resp.status_code} {resp.text[:300]}")


def call_model(client, task, max_tokens=16000):
    payload = {
        "model": task["model"],
        "messages": [{"role": "user", "content": task["prompt"]}],
        "max_tokens": max_tokens,
        "usage": {"include": True},
    }
    if task["web_plugin"]:
        payload["plugins"] = [{"id": "web"}]
    body = post_chat(client, payload)
    message = body["choices"][0]["message"]
    return {
        **task,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "served_model": body.get("model"),
        "provider": body.get("provider"),
        "finish_reason": body["choices"][0].get("finish_reason"),
        "response_text": message.get("content") or "",
        "citations": extract_citations(message),
        "usage": body.get("usage"),
        "raw": body,
    }


def extract_citations(message):
    urls = []
    for a in message.get("annotations") or []:
        if a.get("type") == "url_citation":
            url = (a.get("url_citation") or {}).get("url")
            if url and url not in urls:
                urls.append(url)
    return urls


def load_jsonl(path):
    path = Path(path)
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def make_client(api_key=None, timeout=180):
    api_key = api_key or os.environ["OPENROUTER_API_KEY"]
    return httpx.Client(headers={"Authorization": f"Bearer {api_key}"}, timeout=timeout)


def run_collection(tasks, path, workers=6):
    """Дописує результати у JSONL; уже зібрані ключі пропускає, тож запуск можна переривати й повторювати."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    done = {task_key(r) for r in load_jsonl(path)}
    pending = [t for t in tasks if task_key(t) not in done]
    print(f"Зібрано раніше: {len(done)}, до виконання: {len(pending)}")

    failed = []
    with make_client() as client, path.open("a", encoding="utf-8") as out, ThreadPoolExecutor(workers) as pool:
        futures = {pool.submit(call_model, client, t): t for t in pending}
        for i, future in enumerate(as_completed(futures), start=1):
            try:
                out.write(json.dumps(future.result(), ensure_ascii=False) + "\n")
                out.flush()
            except Exception as e:
                failed.append((futures[future], repr(e)))
            if i % 25 == 0 or i == len(pending):
                print(f"  {i}/{len(pending)} (помилок: {len(failed)})")
    return failed


def seed_from(source_path, target_path, wanted_keys, key_of=task_key):
    """Копіює вже зібрані записи (наприклад, з пілота) у файл повного зрізу, щоб не платити за них удруге."""
    target_path = Path(target_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    present = {key_of(r) for r in load_jsonl(target_path)}
    fresh = [r for r in load_jsonl(source_path) if key_of(r) in wanted_keys and key_of(r) not in present]
    with target_path.open("a", encoding="utf-8") as f:
        f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in fresh)
    return len(fresh)


def set_aside_truncated(responses_path, judgements_path):
    """Переносить неповні відповіді (обрізані за max_tokens, з помилкою провайдера, порожні) та їхні оцінки
    в окремі файли, щоб збір зібрав їх наново."""
    records = load_jsonl(responses_path)
    truncated = {task_key(r) for r in records if r["finish_reason"] in ("length", "error") or not r["response_text"]}
    if not truncated:
        return 0
    for path, key_of in ((Path(responses_path), task_key), (Path(judgements_path), lambda j: tuple(j["key"]))):
        rows = load_jsonl(path)
        kept = [r for r in rows if key_of(r) not in truncated]
        aside = [r for r in rows if key_of(r) in truncated]
        if aside:
            with path.with_name(path.stem + "_truncated.jsonl").open("a", encoding="utf-8") as f:
                f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in aside)
            with path.open("w", encoding="utf-8") as f:
                f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in kept)
    return len(truncated)


def find_mentions(text, brand_patterns):
    """Повертає бренди в порядку першої появи; rank 1 — згаданий першим."""
    hits = []
    for brand, pattern in brand_patterns.items():
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if m:
            hits.append((m.start(), brand))
    hits.sort()
    length = max(len(text), 1)
    return [
        {"brand": brand, "rank": rank, "relative_pos": round(pos / length, 4)}
        for rank, (pos, brand) in enumerate(hits, start=1)
    ]


def match_brand(name, brand_patterns):
    """Зіставляє назву, яку навів суддя, з відстежуваним брендом: спершу за точною назвою, потім за шаблоном."""
    normalized = re.sub(r"[’‘`]", "'", name).strip().lower()
    for brand in brand_patterns:
        if normalized == brand.lower():
            return brand
    for brand, pattern in brand_patterns.items():
        if re.search(pattern, name, flags=re.IGNORECASE):
            return brand
    return None


def classify_domain(url, brand_domains):
    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    for brand, domains in brand_domains.items():
        if any(host == d or host.endswith("." + d) for d in domains):
            return host, "brand_site", brand
    for kind, domains in DOMAIN_TYPES.items():
        if any(host == d or host.endswith("." + d) for d in domains):
            return host, kind, None
    return host, "other", None


def judge_response(client, record, judge_model):
    payload = {
        "model": judge_model,
        "messages": [
            {"role": "system", "content": JUDGE_PROMPT},
            {"role": "user", "content": record["response_text"]},
        ],
        "temperature": 0,
        "max_tokens": 6000,
        "response_format": {"type": "json_schema", "json_schema": JUDGE_SCHEMA},
        "usage": {"include": True},
    }
    body = post_chat(client, payload)
    brands = json.loads(body["choices"][0]["message"]["content"])["brands"]
    return {
        "key": list(task_key(record)),
        "judge_model": judge_model,
        "brands": brands,
        "usage": body.get("usage"),
    }


def run_judging(records, path, judge_model, workers=8):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    done = {tuple(j["key"]) for j in load_jsonl(path)}
    pending = [r for r in records if task_key(r) not in done and r["response_text"]]
    print(f"Оцінено раніше: {len(done)}, до виконання: {len(pending)}")

    failed = []
    with make_client() as client, path.open("a", encoding="utf-8") as out, ThreadPoolExecutor(workers) as pool:
        futures = {pool.submit(judge_response, client, r, judge_model): r for r in pending}
        for i, future in enumerate(as_completed(futures), start=1):
            try:
                out.write(json.dumps(future.result(), ensure_ascii=False) + "\n")
                out.flush()
            except Exception as e:
                failed.append((task_key(futures[future]), repr(e)))
            if i % 50 == 0 or i == len(pending):
                print(f"  {i}/{len(pending)} (помилок: {len(failed)})")
    return failed


def config_key(item):
    return (item["model"], item["web_search"])


def filter_to_configs(records, model_configs):
    wanted = {config_key(c) for c in model_configs}
    return [r for r in records if config_key(r) in wanted]


def model_label(record):
    name = record["model"].split("/")[-1]
    return f"{name} +web" if record["web_search"] else name


def detect_language(text):
    """Розрізняє українську й російську за літерами, яких немає в іншій абетці."""
    uk = len(re.findall(r"[іїєґ]", text, flags=re.IGNORECASE))
    ru = len(re.findall(r"[ыэъё]", text, flags=re.IGNORECASE))
    if uk == ru == 0:
        return "en" if re.search(r"[a-z]", text, flags=re.IGNORECASE) else "unknown"
    return "uk" if uk >= ru else "ru"


def responses_frame(records):
    if not records:
        raise ValueError("Немає зібраних відповідей: спершу виконай збір.")
    df = pd.DataFrame([{k: v for k, v in r.items() if k != "raw"} for r in records])
    df["model_label"] = [model_label(r) for r in records]
    df["cost_usd"] = [(r.get("usage") or {}).get("cost") for r in records]
    df["truncated"] = df["finish_reason"].eq("length")
    df["response_lang"] = df["response_text"].map(detect_language)
    return df


def mentions_frame(records, brand_patterns):
    rows = []
    for r in records:
        for m in find_mentions(r["response_text"], brand_patterns):
            rows.append({
                "model_label": model_label(r), "web_search": r["web_search"], "query_id": r["query_id"],
                "intent": r["intent"], "lang": r["lang"], "geo": r["geo"], "repeat": r["repeat"], **m,
            })
    return pd.DataFrame(rows)


def visibility_table(responses, mentions, by="model_label"):
    """Частка відповідей зі згадкою бренду, середній ранг і частка перших місць — у розрізі `by`."""
    totals = responses.groupby(by).size().rename("responses")
    grouped = mentions.groupby([by, "brand"])
    table = pd.DataFrame({
        "mentions": grouped.size(),
        "mean_rank": grouped["rank"].mean().round(2),
        "first_place": grouped["rank"].apply(lambda s: (s == 1).sum()),
    }).reset_index()
    table = table.merge(totals, on=by)
    table["mention_rate"] = (table["mentions"] / table["responses"]).round(3)
    table["first_place_rate"] = (table["first_place"] / table["responses"]).round(3)
    return table.drop(columns=["first_place"])


def share_of_voice(mentions, by="model_label"):
    counts = mentions.groupby([by, "brand"]).size().rename("mentions").reset_index()
    counts["share_of_voice"] = (counts["mentions"] / counts.groupby(by)["mentions"].transform("sum")).round(3)
    return counts


def repeat_stability(responses, mentions):
    """Середній коефіцієнт Жаккара між наборами брендів у повторах одного запиту однією моделлю."""
    cell = ["model_label", "query_id", "lang", "geo"]
    sets = {key: set(g["brand"]) for key, g in mentions.groupby(cell + ["repeat"])}
    rows = []
    for key, g in responses.groupby(cell):
        brand_sets = [sets.get((*key, rep), set()) for rep in g["repeat"]]
        pairs = [
            len(a & b) / len(a | b) if a | b else 1.0
            for a, b in combinations(brand_sets, 2)
        ]
        if pairs:
            rows.append({**dict(zip(cell, key)), "jaccard": sum(pairs) / len(pairs)})
    return pd.DataFrame(rows)


def sentiment_frame(records, judgements, brand_patterns):
    by_key = {task_key(r): r for r in records}
    rows = []
    for j in judgements:
        record = by_key.get(tuple(j["key"]))
        if record is None:
            continue
        for b in j["brands"]:
            name = str(b.get("name", ""))
            tracked = match_brand(name, brand_patterns)
            rows.append({
                "model_label": model_label(record), "query_id": record["query_id"], "repeat": record["repeat"],
                "lang": record["lang"], "geo": record["geo"], "brand": tracked or name, "tracked": tracked is not None,
                "sentiment": b.get("sentiment"), "recommended": bool(b.get("recommended")),
            })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    # Суддя може назвати один бренд кількома іменами («Приват24», «ПриватБанк») — зводимо до одного рядка на відповідь.
    per_response = ["model_label", "query_id", "repeat", "lang", "geo", "brand", "tracked"]
    return df.groupby(per_response, as_index=False).agg(sentiment=("sentiment", "mean"), recommended=("recommended", "any"))


def citations_frame(records, brand_domains):
    rows = []
    for r in records:
        for url in r.get("citations") or []:
            host, kind, brand = classify_domain(url, brand_domains)
            rows.append({
                "model_label": model_label(r), "query_id": r["query_id"], "repeat": r["repeat"], "lang": r["lang"],
                "url": url, "domain": host, "domain_type": kind, "brand": brand,
            })
    return pd.DataFrame(rows)
