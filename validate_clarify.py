"""Валідація детектора запиту контексту (clarify.py) двома LLM-анотаторами різних розробників.

Стратифікована вибірка: для кожної системи окремо відповіді, які детектор позначив і не позначив.
Анотатор бачить лише кінцівку відповіді й розрізняє запит особистого контексту та загальну пропозицію допомоги,
тож можна відокремити персоналізаційний запит від звичайного UX-патерну.
"""

import json
import random
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

import audit
import clarify

ANNOTATORS = ["openai/gpt-5.6-luna", "anthropic/claude-sonnet-5"]
OUT = Path("data/clarify_annotations.jsonl")
SAMPLE = Path("data/clarify_sample.jsonl")
HUMAN = Path("data/clarify_human_check.csv")
FULL = Path("data/clarify_full.jsonl")
TAIL = 1500
PER_STRATUM = {"google": (50, 30), "api": (20, 20)}

PROMPT = """You are annotating the ending of an answer that a generative search system or chatbot gave to a consumer question (e.g. "Which bank in Ukraine is the best?"). You see only the last part of the answer.

Classify how the answer ENDS (its final sentences addressed to the user):
- "context_request": the answer asks the user to provide information about THEIR OWN situation so that the recommendation can be tailored: e.g. city or region, budget or amount, purpose or needs, the specific product, parcel, medication, preferences, usage pattern. Conditional invitations count ("If you tell me your city and budget, I can suggest...").
- "generic_offer": the answer offers further help or asks a question WITHOUT requesting information about the user's situation: e.g. "Would you like me to compare these banks?", "Let me know if you need more details", "Want a table?".
- "none": the answer ends without addressing the user with a question, request, or offer.

If both a context request and a generic offer are present, choose "context_request".
Also list which kinds of user context are requested (empty list unless context_request): location, budget, purpose, product, preferences, other.
Answer in JSON."""

SCHEMA = {
    "name": "ending",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "label": {"type": "string", "enum": ["context_request", "generic_offer", "none"]},
            "context_types": {"type": "array", "items": {"type": "string", "enum": ["location", "budget", "purpose", "product", "preferences", "other"]}},
        },
        "required": ["label", "context_types"],
        "additionalProperties": False,
    },
}


GOOGLE = "ai-overview +web"


def system_of(record):
    return audit.model_label(record)


def build_sample(seed=7):
    google = [r for r in audit.load_jsonl("data/google_responses.jsonl") if r["aio_present"]]
    api = audit.load_jsonl("data/full_responses.jsonl")
    rng = random.Random(seed)
    sample = []
    for system in sorted({system_of(r) for r in google + api}):
        pool = [r for r in google + api if system_of(r) == system and r["response_text"]]
        n_pos, n_neg = PER_STRATUM["google" if system == GOOGLE else "api"]
        for flag, n in ((True, n_pos), (False, n_neg)):
            stratum = [r for r in pool if clarify.invites_context(r["response_text"], r["lang"]) == flag]
            for r in rng.sample(stratum, min(n, len(stratum))):
                sample.append({"id": len(sample), "system": system, "lang": r["lang"], "industry": r["industry"],
                               "query_id": r["query_id"], "repeat": r["repeat"], "detector": flag,
                               "stratum_size": len(stratum), "system_size": len(pool),
                               "tail": clarify.answer_body(r["response_text"]).strip()[-TAIL:]})
    return sample


def annotate(client, item, model):
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": PROMPT}, {"role": "user", "content": item["tail"]}],
        "temperature": 0,
        "max_tokens": 2000,
        "response_format": {"type": "json_schema", "json_schema": SCHEMA},
        "usage": {"include": True},
    }
    body = audit.post_chat(client, payload)
    return {"id": item["id"], "annotator": model, **json.loads(body["choices"][0]["message"]["content"]),
            "cost": (body.get("usage") or {}).get("cost")}


def run():
    sample = build_sample()
    SAMPLE.write_text("".join(json.dumps(s, ensure_ascii=False) + "\n" for s in sample), encoding="utf-8")
    done = {(a["id"], a["annotator"]) for a in audit.load_jsonl(OUT)}
    jobs = [(s, m) for s in sample for m in ANNOTATORS if (s["id"], m) not in done]
    print("вибірка", len(sample), "до анотування", len(jobs))
    with audit.make_client() as client, OUT.open("a", encoding="utf-8") as out, ThreadPoolExecutor(8) as pool:
        for result in pool.map(lambda job: annotate(client, *job), jobs):
            out.write(json.dumps(result, ensure_ascii=False) + "\n")


def run_full(model=ANNOTATORS[0]):
    """Класифікація кінцівок усіх відповідей (API і Google AI Overviews) основним анотатором."""
    records = audit.load_jsonl("data/full_responses.jsonl") + [
        r for r in audit.load_jsonl("data/google_responses.jsonl") if r["aio_present"]]
    done = {tuple(a["key"]) for a in audit.load_jsonl(FULL)}
    items = [{"id": list(audit.task_key(r)), "tail": clarify.answer_body(r["response_text"]).strip()[-TAIL:]}
             for r in records if r["response_text"] and audit.task_key(r) not in done]
    print("до анотування", len(items))
    with audit.make_client() as client, FULL.open("a", encoding="utf-8") as out, ThreadPoolExecutor(8) as pool:
        for item, result in zip(items, pool.map(lambda it: annotate(client, it, model), items)):
            result["key"] = result.pop("id")
            out.write(json.dumps(result, ensure_ascii=False) + "\n")


def human_sheet(n=60, seed=11):
    """Сліпа таблиця для ручної перевірки: без системи й без позначки детектора."""
    import csv
    sample = [json.loads(l) for l in SAMPLE.open(encoding="utf-8")]
    chosen = sorted(random.Random(seed).sample(sample, n), key=lambda s: s["id"])
    with HUMAN.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "lang", "answer_ending", "label (context_request / generic_offer / none)"])
        for s in chosen:
            w.writerow([s["id"], s["lang"], s["tail"][-700:], ""])


def report():
    """Згода анотаторів, точність детектора і скоригована частка запитів контексту за системами."""
    import pandas as pd
    from sklearn.metrics import cohen_kappa_score

    sample = pd.DataFrame([json.loads(l) for l in SAMPLE.open(encoding="utf-8")]).set_index("id")
    labels = pd.DataFrame(audit.load_jsonl(OUT)).pivot(index="id", columns="annotator", values="label")
    a, b = (labels[m] for m in ANNOTATORS)
    print("κ (3 класи):", round(cohen_kappa_score(a, b), 2), "збіг:", round((a == b).mean(), 2))
    print("κ (запит контексту):", round(cohen_kappa_score(a == "context_request", b == "context_request"), 2))
    df = sample.join(labels)
    df["agree"] = a == b
    df["label"] = a.where(df["agree"])
    df = df[df["agree"]]
    print("узгоджених:", len(df), "з", len(sample))
    rows = []
    for system, part in df.groupby("system"):
        pos, neg = part[part.detector], part[~part.detector]
        p_pos = pos.stratum_size.iloc[0] / pos.system_size.iloc[0]
        row = {"system": system, "detector_rate": p_pos, "n": len(part)}
        for name, target in (("ctx", {"context_request"}), ("any", {"context_request", "generic_offer"})):
            ppv = pos.label.isin(target).mean()
            miss = neg.label.isin(target).mean()
            row[f"ppv_{name}"] = ppv
            row[f"miss_{name}"] = miss
            row[f"rate_{name}"] = p_pos * ppv + (1 - p_pos) * miss
        rows.append(row)
    table = pd.DataFrame(rows).set_index("system").round(2)
    print(table.to_string())
    types = pd.DataFrame(audit.load_jsonl(OUT))
    google_ctx = types[types.id.isin(df[(df.system == GOOGLE) & (df.label == "context_request")].index)]
    print("типи контексту Google:", google_ctx.explode("context_types").groupby("annotator").context_types.value_counts(normalize=False).to_dict())
    table.to_csv("data/clarify_validation.csv")
    return table



def human_agreement():
    """κ між ручною розміткою (заповнена таблиця) і кожним LLM-анотатором."""
    import pandas as pd
    from sklearn.metrics import cohen_kappa_score

    human = pd.read_csv(HUMAN).set_index("id").iloc[:, -1].str.strip().dropna()
    labels = pd.DataFrame(audit.load_jsonl(OUT)).pivot(index="id", columns="annotator", values="label").loc[human.index]
    for model in ANNOTATORS:
        print(model, "κ:", round(cohen_kappa_score(human, labels[model]), 2), "збіг:", round((human == labels[model]).mean(), 2),
              "κ (запит контексту):", round(cohen_kappa_score(human == "context_request", labels[model] == "context_request"), 2))


def full_report():
    """Частки кінцівок за системами з 95 % кластерним бутстреп-ДІ за запитами і типи запитуваного контексту."""
    import pandas as pd
    import inference

    records = audit.load_jsonl("data/full_responses.jsonl") + [
        r for r in audit.load_jsonl("data/google_responses.jsonl") if r["aio_present"]]
    labels = {tuple(a["key"]): a for a in audit.load_jsonl(FULL)}
    df = pd.DataFrame([{"system": system_of(r), "query_id": r["query_id"], "lang": r["lang"],
                        "label": labels[audit.task_key(r)]["label"],
                        "types": labels[audit.task_key(r)]["context_types"],
                        "detector": clarify.invites_context(r["response_text"], r["lang"])}
                       for r in records if audit.task_key(r) in labels])
    for label in ("context_request", "generic_offer"):
        df[label] = df["label"].eq(label).astype(int)
    rows = {}
    for label in ("context_request", "generic_offer"):
        table, _ = inference.bootstrap_rates(df, label, ["system"])
        rows[label] = table
    out = pd.concat(rows, axis=1).round(2)
    out["detector"] = df.groupby("system").detector.mean().round(2)
    out["n"] = df.groupby("system").size()
    print(out.to_string())
    print(df.groupby(["system", "lang"]).context_request.mean().unstack().round(2).to_string())
    ctx = df[df.context_request == 1]
    types = ctx.explode("types").groupby("system").types.value_counts().unstack(fill_value=0)
    print((types.div(ctx.groupby("system").size(), axis=0)).round(2).to_string())
    out.to_csv("data/clarify_rates.csv")
    return out


if __name__ == "__main__":
    load_dotenv(find_dotenv(usecwd=True))
    if sys.argv[1:] == ["report"]:
        report()
    elif sys.argv[1:] == ["human"]:
        human_agreement()
    elif sys.argv[1:] == ["full-report"]:
        full_report()
    elif sys.argv[1:] == ["full"]:
        run_full()
    elif sys.argv[1:] == ["sheet"]:
        human_sheet()
    else:
        run()
