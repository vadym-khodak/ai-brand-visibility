"""Повний перелік брендів у відповіді: відстежувані (словник) плюс усі інші, яких назвав LLM-суддя.

Позиція бренду — перша поява його назви в тексті. Це дає перше місце, ранг і кількість брендів
без усічення до 42 відстежуваних, на яке вказав рецензент.
"""

import re

import pandas as pd

import audit
from design import INDUSTRIES


def normalize(name):
    return re.sub(r"[^\w]+", " ", name.lower()).strip()


def ordered_brands(text, judge_names, brand_patterns, source_names=()):
    """Список (бренд, позиція) за першою появою; відстежувані — під канонічними назвами.

    source_names — назви джерел-посилань, які Google вбудовує в текст; їх не рахуємо як бренди поза списком.
    """
    sources = {normalize(n) for n in source_names}
    positions = {}
    for hit in audit.find_mentions(text, brand_patterns):
        match = re.search(brand_patterns[hit["brand"]], text, flags=re.IGNORECASE)
        positions[hit["brand"]] = match.start()
    lowered = text.lower()
    for name in judge_names:
        tracked = audit.match_brand(name, brand_patterns)
        if tracked is None and normalize(name) in sources:
            continue
        key = tracked or "other:" + normalize(name)
        pos = lowered.find(name.lower())
        if pos < 0:
            if tracked is None:
                continue
            pos = positions.get(tracked, len(text))
        positions[key] = min(positions.get(key, pos), pos)
    return sorted(positions.items(), key=lambda kv: kv[1])


def full_frame(records, judgements):
    """Рядок на пару «відповідь × відстежуваний бренд»: перше місце і ранг серед усіх брендів."""
    by_key = {tuple(j["key"]): j for j in judgements}
    rows = []
    for r in records:
        spec = INDUSTRIES[r["industry"]]
        judge = by_key.get(audit.task_key(r))
        names = [b["name"] for b in judge["brands"]] if judge else []
        order = ordered_brands(r["response_text"], names, spec["brands"], [x["name"] for x in r.get("source_names") or []])
        rank = {brand: i + 1 for i, (brand, _) in enumerate(order)}
        first = order[0][0] if order else None
        for brand in spec["brands"]:
            rows.append({
                "industry": r["industry"], "model_label": audit.model_label(r), "query_id": r["query_id"],
                "lang": r["lang"], "repeat": r["repeat"], "brand": brand,
                "mentioned": int(brand in rank), "first_all": int(first == brand), "rank_all": rank.get(brand),
                "n_all": len(order), "n_tracked": sum(1 for b in rank if not b.startswith("other:")),
                "first_is_other": int(first is not None and first.startswith("other:")),
            })
    return pd.DataFrame(rows)
