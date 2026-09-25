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
from design import INDUSTRIES

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


def main():
    records = audit.load_jsonl("data/full_responses.jsonl")
    panel = inf.full_panel(records)
    latin = latin_share(records)
    print(latin.round(2).sort_values().to_string())
    asymmetry(panel, latin)
    system_heterogeneity(panel)


if __name__ == "__main__":
    main()
