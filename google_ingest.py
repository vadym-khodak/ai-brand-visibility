"""Зводить записи Google AI Overview (пілот + денні вивантаження) до формату відповідей LLM у data/google_responses.jsonl."""

import json
import re
import sys
from pathlib import Path

DATA = Path(__file__).parent / "data"
OUT = DATA / "google_responses.jsonl"
MODEL = "google/ai-overview"

HEADER_NOISE = [
    r"^Огляд від ШІ\s*",
    r"^AI Overview\s*",
    r"^Відповідь у режимі ШІ:\s*[\"«][^\"»]*[\"»]\s*",
    r"^AI Mode reply for (I live in Ukraine\. )?[^?.!]*[?.!]?\s*",
]
SOURCE_PANEL = re.compile(r"Спільна \d+ файл\w*|Shared \d+ files?|Related links|Show less")
SOURCE_SUFFIX = re.compile(r"\.?\s*(Пов’язані результати|Related results)\.?$")
SOURCE_SPLIT = re.compile(r"\s+[–-]\s+")


def clean_text(text):
    """Прибирає заголовок блоку й панель джерел, яку Google показує після тексту відповіді."""
    for pattern in HEADER_NOISE:
        text = re.sub(pattern, "", text)
    panel = SOURCE_PANEL.search(text)
    return (text[:panel.start()] if panel else text).strip()


def parse_sources(labels):
    """'Мінфін (і ще 1) – "Заголовок". Пов’язані результати.' -> ('Мінфін', 'Заголовок')"""
    seen, out = set(), []
    for label in labels or []:
        label = SOURCE_SUFFIX.sub("", label.strip())
        if re.search(r"Відкриється в новій вкладці|Opens in new tab|Докладніше|Learn more", label):
            continue
        parts = SOURCE_SPLIT.split(label, maxsplit=1)
        # З 23.09.2026 Google показує лише назву джерела («Мінфін», «Reddit · r/Ukraine_UA»), без заголовка.
        name = re.sub(r"\s*\((і ще \d+|\+\d+)\)\s*$", "", parts[0]).strip()
        name = re.sub(r"\s*·.*$", "", name)
        title = parts[1].strip().strip('"“”') if len(parts) > 1 else ""
        if name and name not in seen:
            seen.add(name)
            out.append({"name": name, "title": title})
    return out


def normalize(raw, repeat, day):
    query_id = raw.get("query_id") or raw["id"]
    labels = raw.get("sources_all") or raw.get("sources") or []
    return {
        "model": MODEL,
        "web_search": True,
        "web_plugin": False,
        "query_id": query_id,
        "industry": query_id.split("-")[0],
        "intent": raw["intent"],
        "lang": raw["lang"],
        "geo": True,
        "geo_method": "gl=ua",
        "repeat": repeat,
        "collection_day": day,
        "timestamp": raw.get("ts") or raw.get("timestamp"),
        "aio_present": bool(raw.get("aio")),
        "finish_reason": "stop" if raw.get("aio") else "no_aio",
        "response_text": clean_text(raw.get("text", "")) if raw.get("aio") else "",
        "raw_text": raw.get("text", ""),
        "citations": [],
        "source_names": parse_sources(labels),
        "usage": None,
    }


def load_day(path):
    if path.suffix == ".jsonl":
        with path.open(encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]
    return json.loads(path.read_text(encoding="utf-8"))


def main(day_files, out=OUT, rebuild=False):
    """day_files: список 'repeat=path[,path]' — файли одного дня збору."""
    existing = {}
    if OUT.exists() and not rebuild:
        for line in OUT.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            existing[(r["query_id"], r["lang"], r["repeat"])] = r
    added = 0
    for spec in day_files:
        repeat, paths = spec.split("=", 1)
        repeat = int(repeat)
        for p in paths.split(","):
            for raw in load_day(DATA / p):
                rec = normalize(raw, repeat, day=p)
                key = (rec["query_id"], rec["lang"], rec["repeat"])
                if key not in existing:
                    existing[key] = rec
                    added += 1
    with out.open("w", encoding="utf-8") as f:
        for rec in sorted(existing.values(), key=lambda r: (r["repeat"], r["lang"], r["query_id"])):
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"додано {added}, разом {len(existing)} записів у {out.name}")


ALL_RUNS = ["1=google_aio_pilot.jsonl,google_aio_day1.json", "2=google_aio_day2.json",
            "3=google_aio_day3_partial.json,google_aio_day3_part2.json", "4=google_aio_day4.json", "5=google_aio_day5.json"]

if __name__ == "__main__":
    if sys.argv[1:] == ["--rebuild"]:
        main(ALL_RUNS, rebuild=True)
    elif sys.argv[1:2] == ["--geo"]:
        main([f"1={sys.argv[2]}"], out=DATA / "google_geo_responses.jsonl", rebuild=True)
    else:
        main(sys.argv[1:] or ALL_RUNS[:1])
