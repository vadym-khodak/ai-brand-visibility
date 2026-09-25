"""Раунд 3 рецензії: стійкість мовної асиметрії до відбору брендів і альтернативного модератора, розбіжності між системами."""

import re
import warnings

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from statsmodels.stats.multitest import multipletests

import audit
import inference as inf
from design import FOREIGN_PARENTS, INDUSTRIES

warnings.filterwarnings("ignore")
POST_PILOT_BANKS = ["Укрексімбанк", "Креді Агріколь", "Кредобанк"]
ALL_PATTERNS = {b: p for spec in INDUSTRIES.values() for b, p in spec["brands"].items()}


def latin_share(records):
    """Частка латинського написання назви бренду в україномовних відповідях (усі входження шаблону)."""
    counts = {b: [0, 0] for b in ALL_PATTERNS}
    for r in records:
        if r["lang"] != "uk":
            continue
        for brand, pattern in INDUSTRIES[r["industry"]]["brands"].items():
            for m in re.finditer(pattern, r["response_text"], re.I):
                word = m.group(0)
                counts[brand][0] += bool(re.search(r"[A-Za-z]", word)) and not re.search(r"[А-Яа-яІіЇїЄєҐґ]", word)
                counts[brand][1] += 1
    return pd.Series({b: c[0] / c[1] if c[1] else np.nan for b, c in counts.items()})


def asymmetry(panel, latin):
    panel = panel.assign(latin=panel.brand.map(latin).gt(0.5).astype(int))
    print("латинське написання:", sorted(latin[latin > 0.5].index))
    variants = {
        "без трьох банків, доданих після пілоту": (panel[~panel.brand.isin(POST_PILOT_BANKS)], ["en", "en:foreign"], ""),
        "латинська назва замість власника": (panel, ["en", "en:latin"], "latin"),
        "власник і латинська назва разом": (panel, ["en", "en:foreign", "en:latin"], "both"),
    }
    for name, (data, terms, mode) in variants.items():
        if mode == "latin":
            formula = "mentioned ~ C(brand) + C(model_label) + en + en:latin"
        elif mode == "both":
            formula = "mentioned ~ C(brand) + C(model_label) + en + en:foreign + en:latin"
        else:
            formula = "mentioned ~ C(brand) + C(model_label) + en + en:foreign"
        result = smf.gee(formula, groups="query_id", data=data, family=sm.families.Binomial(),
                         cov_struct=sm.cov_struct.Independence()).fit()
        print("---", name)
        print(inf.odds_ratios(result, terms).round(3).to_string())


def system_heterogeneity(panel, draws=4000, seed=31):
    """Для кожного бренду: чи відрізняється MR між п'ятьма системами (бутстреп-Вальд за запитами) з поправкою BH."""
    rows = []
    for industry, part in panel.groupby("industry"):
        rates, samples = inf.bootstrap_rates(part, "mentioned", ["brand", "model_label"], draws=draws, seed=seed)
        cols = list(rates.index)
        for brand in part.brand.unique():
            idx = [cols.index(c) for c in cols if c[0] == brand]
            est = rates.est.to_numpy()[idx]
            sims = samples[:, idx]
            contrast = np.eye(len(idx))[1:] - np.eye(len(idx))[0]
            diff, cov = contrast @ est, np.cov((sims @ contrast.T).T)
            stat = float(diff @ np.linalg.pinv(cov) @ diff)
            from scipy.stats import chi2
            p = chi2.sf(stat, len(idx) - 1)
            hi, lo = int(np.argmax(est)), int(np.argmin(est))
            rng_samples = sims[:, hi] - sims[:, lo]
            rows.append({"industry": industry, "brand": brand, "min": est.min(), "max": est.max(),
                         "sys_max": cols[idx[hi]][1], "sys_min": cols[idx[lo]][1],
                         "diff_lo": np.percentile(rng_samples, 2.5), "diff_hi": np.percentile(rng_samples, 97.5), "p": p})
    table = pd.DataFrame(rows)
    table["q"] = multipletests(table.p, method="fdr_bh")[1]
    table["range"] = table["max"] - table["min"]
    table.round(3).to_csv("data/system_heterogeneity.csv", index=False)
    print("брендів з q < 0,05:", int((table.q < 0.05).sum()), "з", len(table))
    print("розмах > 0,44:", int((table.range > 0.44).sum()), "з них q<0,05:", int(((table.range > 0.44) & (table.q < 0.05)).sum()))
    print(table.sort_values("range", ascending=False).head(14).round(3).to_string())
    return table


DIGITAL_BANK_QUERIES = ["bank-03", "bank-09", "bank-11", "bank-16"]


def bank_rank_gaps(panel, queries_out=(), draws=2000, seed=5):
    """Ранг за кількістю вкладників проти 95 % бутстреп-інтервалу рангу за згадуваністю (без заданих запитів)."""
    from scipy.stats import spearmanr

    banks = panel[(panel.industry == "bank") & ~panel.query_id.isin(queries_out)]
    depositors = pd.read_csv("data/market/banks_nbu_2026-08-01.csv").set_index("brand").depositors
    rates, samples = inf.bootstrap_rates(banks, "mentioned", ["brand"], draws=draws, seed=seed)
    ranks = pd.DataFrame(samples, columns=list(rates.index)).rank(axis=1, ascending=False)
    out = pd.DataFrame({"mr": rates.est, "r_mr": rates.est.rank(ascending=False),
                        "r_lo": ranks.quantile(0.025), "r_hi": ranks.quantile(0.975)})
    out["r_market"] = depositors.reindex(out.index).rank(ascending=False)
    out["robust"] = (out.r_market < out.r_lo) | (out.r_market > out.r_hi)
    print(f"--- без {list(queries_out)}: ρ = {spearmanr(out.mr, depositors.reindex(out.index)).statistic:.2f}")
    print(out.sort_values("r_market").round(2).to_string())
    return out


def oschadbank_layers(panel):
    """Згадуваність банків за шарами: моделі без пошуку, Sonar, Google AI Overviews (україномовні запити)."""
    banks = panel[panel.industry == "bank"]
    google = [r for r in audit.load_jsonl("data/google_responses.jsonl") if r["aio_present"] and r["industry"] == "bank"]
    aio = inf.brand_panel(google, "bank")
    table = pd.concat([banks.groupby(["web_search", "brand"]).mentioned.mean().unstack(0).set_axis(["LLM без пошуку", "Sonar"], axis=1),
                       aio[aio.lang == "uk"].groupby("brand").mentioned.mean().rename("AIO uk")], axis=1)
    print(pd.concat([table.round(2), table.rank(ascending=False).add_suffix(" ранг")], axis=1).to_string())
    by_query = banks[banks.brand == "Ощадбанк"].groupby(["query_id", "intent"]).mentioned.mean().sort_values()
    print(by_query.round(2).to_string())


def variance_components(panel):
    """Для кожного бренду: дисперсія відповіді всередині клітинки «запит × система» (між повторами й мовними версіями)
    і дисперсія справжньої частки між запитами — окремо для однієї системи і для середнього за п'ятьма системами."""
    cells = panel.groupby(["industry", "brand", "model_label", "query_id"]).mentioned.agg(["sum", "size"]).reset_index()
    n = cells["size"]
    cells["p"] = cells["sum"] / n
    cells["w"] = cells["sum"] * (n - cells["sum"]) / (n * (n - 1))
    rows = []
    for (industry, brand), g in cells.groupby(["industry", "brand"]):
        per_system = [(sg.w.mean(), max(sg.p.var(ddof=1) - (sg.w / n[sg.index]).mean(), 0)) for _, sg in g.groupby("model_label")]
        pooled = g.groupby("query_id").agg(p=("p", "mean"), noise=("w", lambda w: (w / n[w.index]).mean() / g.model_label.nunique()))
        rows.append({"industry": industry, "brand": brand,
                     "within": np.mean([w for w, _ in per_system]), "between_1": np.mean([b for _, b in per_system]),
                     "between_all": max(pooled.p.var(ddof=1) - pooled.noise.mean(), 0)})
    return pd.DataFrame(rows)


def mde_table(panel, z=1.96 + 0.84):
    """Мінімальний виявний ефект (α = 0,05, потужність 80 %) зміни MR бренду між двома хвилями.

    Фіксований набір запитів: різниця містить лише шум між повторами. Новий набір запитів у кожній хвилі:
    додається дисперсія між запитами. Q — кількість запитів (обидві мовні версії запиту — одна одиниця), R — відповідей
    на запит у кожній системі (повтори × мовні версії), S — систем.
    """
    comp = variance_components(panel)
    out = []
    for quantile in (0.5, 0.75):
        within, b1, ball = comp[["within", "between_1", "between_all"]].quantile(quantile)
        for q in (10, 20, 40):
            for r in (2, 6, 10):
                for systems, between in ((1, b1), (5, ball)):
                    fixed = z * np.sqrt(2 * within / (q * r * systems))
                    fresh = z * np.sqrt(2 * (between / q + within / (q * r * systems)))
                    half = 1.96 * np.sqrt(between / q + within / (q * r * systems))
                    out.append({"brand_quantile": quantile, "queries": q, "repeats": r, "systems": systems,
                                "mde_fixed": fixed, "mde_new_queries": fresh, "ci_half_width": half})
    table = pd.DataFrame(out)
    table.round(3).to_csv("data/mde_table.csv", index=False)
    print(comp[["within", "between_1", "between_all"]].describe().round(3).to_string())
    print(table[table.brand_quantile == 0.5].round(3).to_string(index=False))
    return comp, table


def measurement_checks(records, judgements):
    """Повнота словника відносно LLM-судді за мовами, частка не знайдених у тексті назв поза словником
    і мовний ефект лише для прямих рекомендацій (за суддею)."""
    by_key = {tuple(j["key"]): j for j in judgements}
    rows, unlocated, other = [], {"uk": 0, "en": 0}, {"uk": 0, "en": 0}
    for r in records:
        judge = by_key.get(audit.task_key(r))
        if not judge:
            continue
        patterns = INDUSTRIES[r["industry"]]["brands"]
        found = {h["brand"] for h in audit.find_mentions(r["response_text"], patterns)}
        named = {}
        for b in judge["brands"]:
            tracked = audit.match_brand(b["name"], patterns)
            if tracked:
                named[tracked] = named.get(tracked, False) or bool(b.get("recommended"))
            else:
                other[r["lang"]] += 1
                unlocated[r["lang"]] += r["response_text"].lower().find(b["name"].lower()) < 0
        for brand in patterns:
            rows.append({"lang": r["lang"], "brand": brand, "query_id": r["query_id"], "model_label": audit.model_label(r),
                         "dictionary": brand in found, "judge": brand in named, "recommended": int(named.get(brand, False))})
    d = pd.DataFrame(rows)
    for lang, g in d.groupby("lang"):
        both = (g.dictionary & g.judge).sum()
        print(lang, "повнота словника:", round(both / g.judge.sum(), 3), "повнота судді:", round(both / g.dictionary.sum(), 3),
              "назви поза словником, не знайдені в тексті:", round(unlocated[lang] / other[lang], 3),
              "частка рекомендацій серед згадок:", round(g[g.dictionary].recommended.mean(), 3))
    d["en"] = d.lang.eq("en").astype(int)
    d["foreign"] = d.brand.isin(FOREIGN_PARENTS).astype(int)
    result = smf.gee("recommended ~ C(brand) + C(model_label) + en + en:foreign", groups="query_id", data=d,
                     family=sm.families.Binomial(), cov_struct=sm.cov_struct.Independence()).fit()
    print("--- лише прямі рекомендації\n", inf.odds_ratios(result, ["en", "en:foreign"]).round(3).to_string())


def main():
    records = audit.load_jsonl("data/full_responses.jsonl")
    panel = inf.full_panel(records)
    latin = latin_share(records)
    print(latin.round(2).sort_values().to_string())
    asymmetry(panel, latin)
    system_heterogeneity(panel)
    bank_rank_gaps(panel)
    bank_rank_gaps(panel, DIGITAL_BANK_QUERIES)
    oschadbank_layers(panel)
    mde_table(panel)
    measurement_checks(records, audit.load_jsonl("data/full_judgements.jsonl"))


if __name__ == "__main__":
    main()
