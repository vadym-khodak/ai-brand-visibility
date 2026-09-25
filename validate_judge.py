"""Перевірка оцінок тональності: другий LLM-суддя іншого розробника на випадковій вибірці з 200 відповідей.

`python validate_judge.py run` — повторно оцінює вибірку (потрібен OPENROUTER_API_KEY, ~2 дол. США);
`python validate_judge.py` — лише порівнює наявні оцінки двох суддів.
"""

import random
import sys

import pandas as pd
from dotenv import find_dotenv, load_dotenv
from scipy.stats import spearmanr
from sklearn.metrics import cohen_kappa_score

import audit
from design import INDUSTRIES

SECOND_JUDGE = "anthropic/claude-sonnet-5"
OUT = "data/validation_judge2.jsonl"


def sample(records, n=200, seed=42):
    random.seed(seed)
    return random.sample(records, n)


def brand_scores(judgement, patterns):
    """Середня тональність і ознака рекомендації для кожного відстежуваного бренду в оцінці судді."""
    scores = {}
    for b in judgement["brands"]:
        brand = audit.match_brand(str(b["name"]), patterns)
        if brand:
            scores.setdefault(brand, []).append((b["sentiment"], b["recommended"]))
    return {brand: (sum(s for s, _ in v) / len(v), any(r for _, r in v)) for brand, v in scores.items()}


def report(records):
    chosen = sample(records)
    first = {tuple(j["key"]): j for j in audit.load_jsonl("data/full_judgements.jsonl")}
    second = {tuple(j["key"]): j for j in audit.load_jsonl(OUT)}
    rows = []
    for r in chosen:
        key, patterns = audit.task_key(r), INDUSTRIES[r["industry"]]["brands"]
        a, b = brand_scores(first[key], patterns), brand_scores(second[key], patterns)
        rows += [{"brand": t, "s1": a[t][0], "s2": b[t][0], "r1": a[t][1], "r2": b[t][1]} for t in set(a) & set(b)]
    both = pd.DataFrame(rows)
    s1, s2 = both.s1.round().astype(int), both.s2.round().astype(int)
    print("згадок, оцінених обома суддями:", len(both))
    print("точний збіг тональності:", round((s1 == s2).mean(), 3), "κ:", round(cohen_kappa_score(s1, s2), 3))
    print("збіг рекомендації:", round((both.r1 == both.r2).mean(), 3),
          "κ:", round(cohen_kappa_score(both.r1.astype(int), both.r2.astype(int)), 3))
    by_brand = both.groupby("brand").agg(s1=("s1", "mean"), s2=("s2", "mean"), n=("s1", "size"))
    by_brand = by_brand[by_brand.n >= 15]
    print("брендів з ≥15 згадками:", len(by_brand), "ρ тональності на рівні брендів:",
          round(spearmanr(by_brand.s1, by_brand.s2).statistic, 3))


if __name__ == "__main__":
    records = audit.load_jsonl("data/full_responses.jsonl")
    if sys.argv[1:] == ["run"]:
        load_dotenv(find_dotenv(usecwd=True))
        audit.run_judging(sample(records), OUT, SECOND_JUDGE)
    report(records)
