"""Статистичне оцінювання: кластерний бутстреп за запитами та логістична GEE-модель мовного ефекту.

Одиниця незалежності — запит: повтори, системи й обидві мовні версії одного запиту
потрапляють у бутстреп-вибірку разом, тож інтервали враховують кластерну структуру даних.
"""

import re

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from statsmodels.stats.multitest import multipletests

import audit
from design import FOREIGN_PARENTS, INDUSTRIES, INTERNATIONAL_NETWORK

RESPONSE_KEY = ["model_label", "query_id", "lang", "repeat"]


def script_language(text):
    """Мова відповіді за переважним письмом: кирилиця (з розрізненням uk/ru) чи латиниця."""
    cyrillic = len(re.findall(r"[а-яіїєґё]", text, flags=re.IGNORECASE))
    latin = len(re.findall(r"[a-z]", text, flags=re.IGNORECASE))
    if cyrillic == latin == 0:
        return "unknown"
    if latin > cyrillic:
        return "en"
    return audit.detect_language(text)


def brand_panel(records, industry):
    """Рядок на пару «відповідь × відстежуваний бренд галузі» зі згадкою та першим місцем."""
    brands = INDUSTRIES[industry]["brands"]
    responses = pd.DataFrame([
        {**{k: r[k] for k in ("query_id", "lang", "repeat", "intent")},
         "model_label": audit.model_label(r), "web_search": r["web_search"],
         "response_lang": script_language(r["response_text"])}
        for r in records
    ])
    panel = responses.merge(pd.DataFrame({"brand": list(brands)}), how="cross")
    mentions = audit.mentions_frame(records, brands)
    if mentions.empty:
        panel["mentioned"] = 0
        panel["first"] = 0
    else:
        hits = mentions.drop_duplicates(RESPONSE_KEY + ["brand"])[RESPONSE_KEY + ["brand", "rank"]]
        panel = panel.merge(hits, on=RESPONSE_KEY + ["brand"], how="left")
        panel["mentioned"] = panel["rank"].notna().astype(int)
        panel["first"] = panel["rank"].eq(1).astype(int)
        panel = panel.drop(columns="rank")
    panel["industry"] = industry
    panel["foreign"] = panel["brand"].isin(FOREIGN_PARENTS).astype(int)
    panel["network"] = panel["brand"].isin(INTERNATIONAL_NETWORK).astype(int)
    panel["en"] = panel["lang"].eq("en").astype(int)
    return panel


def full_panel(records):
    return pd.concat(
        [brand_panel([r for r in records if r["industry"] == ind], ind) for ind in INDUSTRIES],
        ignore_index=True,
    )


def query_weights(n_queries, draws, seed):
    """Кратність кожного запиту в бутстреп-вибірках (матриця draws × n_queries)."""
    rng = np.random.default_rng(seed)
    return rng.multinomial(n_queries, np.full(n_queries, 1 / n_queries), size=draws)


def bootstrap_rates(panel, value, cells, draws=2000, seed=0):
    """Частки `value` у розрізі `cells` з бутстреп-вибірками запитів.

    Повертає (оцінки, вибірки): оцінки — DataFrame з est/lo/hi, вибірки — масив draws × cells
    у тому самому порядку, щоб різниці між клітинками рахувати на спільних вибірках.
    """
    grouped = panel.groupby(["query_id", *cells])[value].agg(["sum", "size"])
    x = grouped["sum"].unstack(cells, fill_value=0)
    n = grouped["size"].unstack(cells, fill_value=0)
    weights = query_weights(len(x), draws, seed)
    samples = (weights @ x.to_numpy()) / np.maximum(weights @ n.to_numpy(), 1)
    point = x.sum() / n.sum()
    lo, hi = np.percentile(samples, [2.5, 97.5], axis=0)
    table = pd.DataFrame({"est": point.to_numpy(), "lo": lo, "hi": hi}, index=x.columns)
    return table, samples


def difference_ci(samples, columns, first, second):
    """Бутстреп-інтервал різниці між двома клітинками однієї вибірки."""
    cols = list(columns)
    diff = samples[:, cols.index(first)] - samples[:, cols.index(second)]
    return np.percentile(diff, [2.5, 97.5])


def language_gaps(panel, draws=2000, seed=0):
    """Різниця MR (uk − en) для кожного бренду з 95 % бутстреп-інтервалом."""
    rows = []
    for industry, part in panel.groupby("industry"):
        rates, samples = bootstrap_rates(part, "mentioned", ["brand", "lang"], draws, seed)
        cols = list(rates.index)
        for brand in part["brand"].unique():
            lo, hi = difference_ci(samples, rates.index, (brand, "uk"), (brand, "en"))
            diff = samples[:, cols.index((brand, "uk"))] - samples[:, cols.index((brand, "en"))]
            p = min(1.0, 2 * min(np.mean(diff <= 0), np.mean(diff >= 0)))
            uk, en = rates.loc[(brand, "uk"), "est"], rates.loc[(brand, "en"), "est"]
            rows.append({"industry": industry, "brand": brand, "uk": uk, "en": en,
                         "gap": uk - en, "lo": lo, "hi": hi, "p": p})
    gaps = pd.DataFrame(rows)
    gaps["foreign"] = gaps["brand"].isin(FOREIGN_PARENTS)
    gaps["significant"] = (gaps["lo"] > 0) | (gaps["hi"] < 0)
    gaps["q_bh"] = multipletests(gaps["p"], method="fdr_bh")[1]
    gaps["significant_fdr"] = gaps["q_bh"] < 0.05
    return gaps


def language_model(panel, extra_terms=""):
    """Логістична GEE: згадка ~ бренд + система + мова × іноземний власник, кластери — запити."""
    formula = "mentioned ~ C(brand) + C(model_label) + en + en:foreign" + extra_terms
    model = smf.gee(formula, groups="query_id", data=panel,
                    family=sm.families.Binomial(), cov_struct=sm.cov_struct.Independence())
    return model.fit()


def odds_ratios(result, terms):
    ci = result.conf_int()
    return pd.DataFrame({
        "OR": np.exp(result.params[terms]),
        "lo": np.exp(ci.loc[terms, 0]),
        "hi": np.exp(ci.loc[terms, 1]),
        "p": result.pvalues[terms],
    })


def combined_effect(result, main, interaction):
    """OR для групи з взаємодією: exp(β_main + β_interaction) з дельта-методом."""
    cov = result.cov_params()
    beta = result.params[main] + result.params[interaction]
    se = np.sqrt(cov.loc[main, main] + cov.loc[interaction, interaction] + 2 * cov.loc[main, interaction])
    return np.exp(beta), np.exp(beta - 1.96 * se), np.exp(beta + 1.96 * se)
