"""Другий кодувальник міток наміру: два LLM різних розробників незалежно класифікують 80 запитів."""

import json
from pathlib import Path

import pandas as pd
from dotenv import find_dotenv, load_dotenv
from sklearn.metrics import cohen_kappa_score

import audit

CODERS = ["openai/gpt-5.6-luna", "anthropic/claude-sonnet-5"]
OUT = Path("data/intent_coding.jsonl")
PROMPT = """Classify the consumer search query into exactly one intent:
- BEST: asks for the generally best or a recommended provider, without a specific task, comparison criterion, price or trust concern.
- TASK: asks where or with whom to accomplish a specific task (open an account, buy a specific item, send a parcel abroad).
- COMP: asks which provider is better on a comparison criterion or between types of providers (faster, more convenient, bigger choice, state vs private).
- PRICE: asks about price, fees, discounts, rates or free delivery.
- TRUST: asks about reliability, safety, authenticity, support quality or protection.
Answer in JSON."""
SCHEMA = {"name": "intent", "strict": True, "schema": {"type": "object", "properties": {
    "intent": {"type": "string", "enum": ["BEST", "TASK", "COMP", "PRICE", "TRUST"]}},
    "required": ["intent"], "additionalProperties": False}}


def run():
    queries = pd.read_csv("data/queries.csv")
    done = {(c["query_id"], c["coder"]) for c in audit.load_jsonl(OUT)}
    with audit.make_client() as client, OUT.open("a", encoding="utf-8") as out:
        for q in queries.itertuples():
            for coder in CODERS:
                if (q.query_id, coder) in done:
                    continue
                body = audit.post_chat(client, {
                    "model": coder, "temperature": 0, "max_tokens": 500,
                    "messages": [{"role": "system", "content": PROMPT}, {"role": "user", "content": q.query_en}],
                    "response_format": {"type": "json_schema", "json_schema": SCHEMA}, "usage": {"include": True}})
                label = json.loads(body["choices"][0]["message"]["content"])["intent"]
                out.write(json.dumps({"query_id": q.query_id, "coder": coder, "intent": label,
                                      "cost": (body.get("usage") or {}).get("cost")}) + "\n")


def report():
    queries = pd.read_csv("data/queries.csv").set_index("query_id")
    coded = pd.DataFrame(audit.load_jsonl(OUT)).pivot(index="query_id", columns="coder", values="intent")
    author = queries.intent.loc[coded.index]
    for coder in CODERS:
        print(coder, "збіг з автором:", round((coded[coder] == author).mean(), 2), "κ:", round(cohen_kappa_score(author, coded[coder]), 2))
    print("кодувальники між собою: κ", round(cohen_kappa_score(coded[CODERS[0]], coded[CODERS[1]]), 2))
    agree = coded[CODERS[0]] == coded[CODERS[1]]
    consensus_diff = coded[agree & (coded[CODERS[0]] != author)]
    print("обидва кодувальники не згодні з автором:", len(consensus_diff))
    print(pd.concat([author.rename("author"), coded, queries.query_uk], axis=1).loc[consensus_diff.index].to_string())
    print(pd.crosstab(author, coded[CODERS[0]]))


if __name__ == "__main__":
    load_dotenv(find_dotenv(usecwd=True))
    run()
    report()
