"""Перелік запитів з design.py у data/queries.csv і data/queries.md (обидві мови, намір, галузь)."""

import csv
from pathlib import Path

import audit
from design import INDUSTRIES

INDUSTRY_NAMES = {"bank": ("Банки", "Banks"), "ecom": ("Інтернет-торгівля", "E-commerce"),
                  "pharma": ("Аптеки", "Pharmacies"), "post": ("Поштова логістика", "Postal logistics"),
                  "food": ("Доставка їжі", "Food delivery")}


def rows():
    for industry in INDUSTRIES:
        english = {q["query_id"]: q["text"] for q in audit.build_industry_queries(industry, "en")}
        for q in audit.build_industry_queries(industry, "uk"):
            yield {"query_id": q["query_id"], "industry": industry, "intent": q["intent"],
                   "query_uk": q["text"], "query_en": english[q["query_id"]]}


def write_csv(path):
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["query_id", "industry", "intent", "query_uk", "query_en"])
        writer.writeheader()
        writer.writerows(rows())


def write_markdown(path):
    lines = [
        "# Перелік запитів / Query list",
        "",
        "80 небрендованих запитів українською та англійською мовами. В основному зборі перед кожним запитом "
        f"додавалося речення «{audit.GEO_PREFIX['uk'].strip()}» / «{audit.GEO_PREFIX['en'].strip()}».",
        "",
        "80 unbranded queries in Ukrainian and English. In the main collection each query was preceded by "
        f"«{audit.GEO_PREFIX['uk'].strip()}» / «{audit.GEO_PREFIX['en'].strip()}».",
        "",
        "Наміри / intents: BEST — загальна рекомендація / general recommendation; TASK — конкретна задача / specific task; "
        "COMP — порівняння / comparison; PRICE — ціна / price; TRUST — довіра / trust.",
        "",
        "Машинозчитувана версія / machine-readable version: `queries.csv`.",
    ]
    current = None
    for row in rows():
        if row["industry"] != current:
            current = row["industry"]
            uk, en = INDUSTRY_NAMES[current]
            lines += ["", f"## {uk} / {en}", "", "| ID | Намір / Intent | Українською | English |", "|---|---|---|---|"]
        lines.append(f"| {row['query_id']} | {row['intent']} | {row['query_uk']} | {row['query_en']} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    write_csv(Path("data/queries.csv"))
    write_markdown(Path("data/queries.md"))
