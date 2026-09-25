"""Відтворює статистику для доопрацювання статті: ДІ табл. 3–4, мовний розрив (рис. 3) і GEE-модель."""

import warnings

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import itertools
import re
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from statsmodels.stats.multitest import multipletests

import audit
import clarify
import inference as inf
import sources
import fullset
from design import INDUSTRIES

warnings.filterwarnings("ignore")
INTENTS = ["BEST", "TASK", "COMP", "PRICE", "TRUST"]


def fmt(x):
    return f"{x:.2f}".replace(".", ",")


def table3(panel, full, records, judgements):
    """Табл. 3: MR і FP з 95 % ДІ, ранг серед усіх брендів, MR за мовами, розкид за системами, тональність.

    FP і ранг рахуються серед усіх брендів відповіді (відстежуваних і названих LLM-суддею), а не лише 42.
    """
    rows = []
    for industry, part in panel.groupby("industry"):
        mr, _ = inf.bootstrap_rates(part, "mentioned", ["brand"], seed=11)
        fp, _ = inf.bootstrap_rates(full[full.industry == industry], "first_all", ["brand"], seed=11)
        by_lang = part.groupby(["brand", "lang"]).mentioned.mean().unstack()
        by_system = part.groupby(["brand", "model_label"]).mentioned.mean().unstack()
        ranks = full[(full.industry == industry) & full.rank_all.notna()].groupby("brand").rank_all.mean()
        spec = INDUSTRIES[industry]
        tone = audit.sentiment_frame([r for r in records if r["industry"] == industry], judgements, spec["brands"])
        tone = tone.groupby("brand").sentiment.mean()
        for brand in spec["brands"]:
            rows.append({"industry": industry, "brand": brand,
                         "mr_est": mr.loc[brand, "est"], "mr_lo": mr.loc[brand, "lo"], "mr_hi": mr.loc[brand, "hi"],
                         "fp_est": fp.loc[brand, "est"], "fp_lo": fp.loc[brand, "lo"], "fp_hi": fp.loc[brand, "hi"],
                         "rank": ranks.get(brand, np.nan), "mr_uk": by_lang.loc[brand, "uk"], "mr_en": by_lang.loc[brand, "en"],
                         "sys_min": by_system.loc[brand].min(), "sys_max": by_system.loc[brand].max(), "tone": tone.get(brand, np.nan)})
    table = pd.DataFrame(rows).set_index("brand")
    table.round(3).to_csv("data/table3_ci.csv")
    return table


TABLE3_INDUSTRIES = {"bank": "Банки", "ecom": "Інтернет-торгівля", "pharma": "Аптеки", "post": "Пошта і логістика", "food": "Доставка їжі"}


def table3_markdown(table):
    lines = ["| Галузь | Бренд | MR (95 % ДІ) | FP (95 % ДІ) | Ранг | MR uk | MR en | MR min–max за системами | Тональність |",
             "|---|---|---|---|---|---|---|---|---|"]
    for industry, label in TABLE3_INDUSTRIES.items():
        part = table[table.industry == industry].sort_values("mr_est", ascending=False)
        for i, (brand, r) in enumerate(part.iterrows()):
            lines.append(f"| {label if i == 0 else ''} | {brand} | {fmt(r.mr_est)} ({fmt(r.mr_lo)}–{fmt(r.mr_hi)}) | "
                         f"{fmt(r.fp_est)} ({fmt(r.fp_lo)}–{fmt(r.fp_hi)}) | {f'{r['rank']:.1f}'.replace('.', ',')} | "
                         f"{fmt(r.mr_uk)} | {fmt(r.mr_en)} | {fmt(r.sys_min)}–{fmt(r.sys_max)} | {fmt(r.tone)} |")
    return "\n".join(lines)


def table4(panel):
    banks = panel[panel.industry == "bank"]
    parts, draws = [], {}
    for i, intent in enumerate(INTENTS):
        subset = banks[banks.intent == intent]
        rates, samples = inf.bootstrap_rates(subset, "mentioned", ["brand"], seed=30 + i)
        spread = subset.groupby(["brand", "query_id"]).mentioned.mean().groupby("brand").agg(["min", "max"])
        parts.append(rates.join(spread).assign(intent=intent))
        draws[intent] = (rates, samples)
    return pd.concat(parts).round(2), draws


def intent_difference(draws, brand, first, second):
    (r1, s1), (r2, s2) = draws[first], draws[second]
    diff = s1[:, list(r1.index).index(brand)] - s2[:, list(r2.index).index(brand)]
    return r1.loc[brand, "est"] - r2.loc[brand, "est"], np.percentile(diff, [2.5, 97.5])


def plot_gaps(gaps, path):
    matplotlib.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9})
    g = gaps.sort_values("gap").reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(6.5, 8.6))
    y = np.arange(len(g))
    ax.hlines(y, g.lo, g.hi, color="#555555", lw=1)
    for foreign, marker, face, label in [(False, "o", "white", "Український власник"),
                                         (True, "s", "black", "Іноземна материнська група")]:
        s = g[g.foreign == foreign]
        ax.plot(s.gap, s.index, marker, ms=5, mfc=face, mec="black", mew=.8, ls="none", label=label)
    ax.axvline(0, color="black", lw=.8)
    ax.set_yticks(y)
    ax.set_yticklabels([f"{b}{' *' if sig else ''}" for b, sig in zip(g.brand, g.significant_fdr)])
    ax.set_xlabel("Різниця згадуваності uk − en, 95 % ДІ\n← вища в англомовних запитах     вища в україномовних запитах →")
    ax.set_ylim(-1, len(g))
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    ax.grid(axis="x", color="#dddddd", lw=.5)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    plt.tight_layout()
    plt.savefig(path, dpi=300)


def main():
    records = audit.load_jsonl("data/full_responses.jsonl")
    judgements = audit.load_jsonl("data/full_judgements.jsonl")
    panel = inf.full_panel(records)
    full = fullset.full_frame(records, judgements)
    full.to_pickle("data/full_frame.pkl")
    Path("data/table3.md").write_text(table3_markdown(table3(panel, full, records, judgements)), encoding="utf-8")
    t4, draws = table4(panel)
    t4.to_csv("data/table4_ci.csv")
    for brand in ["Райффайзен Банк", "Креді Агріколь", "OTP Bank", "УкрСиббанк"]:
        print(brand, "TRUST − PRICE", intent_difference(draws, brand, "TRUST", "PRICE"))
    for brand in ["monobank", "А-Банк"]:
        print(brand, "BEST − TRUST", intent_difference(draws, brand, "BEST", "TRUST"))

    gaps = inf.language_gaps(panel, draws=10000, seed=21)
    gaps.round(3).to_csv("data/language_gaps_ci.csv", index=False)
    plot_gaps(gaps, "figures/fig3_language_gap.png")
    print("significant gaps (CI):", int(gaps.significant.sum()), "after BH-FDR:", int(gaps.significant_fdr.sum()), "of", len(gaps))

    rates, samples = inf.bootstrap_rates(panel, "mentioned", ["foreign", "lang"], seed=22)
    for foreign in (0, 1):
        gap = rates.loc[(foreign, "uk"), "est"] - rates.loc[(foreign, "en"), "est"]
        print("foreign" if foreign else "local", "uk − en", round(gap, 3),
              inf.difference_ci(samples, rates.index, (foreign, "uk"), (foreign, "en")).round(3))

    variants = {
        "усі системи": panel,
        "мова відповіді = мова запиту": panel[panel.response_lang == panel.lang],
        "моделі без пошуку": panel[~panel.web_search],
        "Sonar": panel[panel.web_search],
    }
    for name, data in variants.items():
        result = inf.language_model(data)
        print(f"--- {name}")
        print(inf.odds_ratios(result, ["en", "en:foreign"]).round(3).to_string())
        print("OR en, іноземні власники:", np.round(inf.combined_effect(result, "en", "en:foreign"), 3))
    meest = inf.language_model(panel, " + en:network")
    print("--- Meest окремо\n", inf.odds_ratios(meest, ["en", "en:foreign", "en:network"]).round(3).to_string())


def context_requests():
    """Частка відповідей, що завершуються запитом уточнити контекст, і типи запитуваного контексту."""
    google = [r for r in audit.load_jsonl("data/google_responses.jsonl") if r["aio_present"]]
    asks = [r for r in google if clarify.invites_context(r["response_text"], r["lang"])]
    print("AIO: запит контексту", len(asks), "з", len(google))
    types = pd.Series([t for r in asks for t in clarify.requested_context(r["response_text"])]).value_counts() / len(asks)
    print(types.round(2).to_dict())
    api = pd.DataFrame([{"system": audit.model_label(r), "ask": clarify.invites_context(r["response_text"], r["lang"])}
                        for r in audit.load_jsonl("data/full_responses.jsonl")])
    print(api.groupby("system").ask.mean().round(2).to_dict())

CLOSED_SERVICES = {"Justin": (r"\bjustin\b|джастін", "post"), "Raketa": (r"\braketa\b|ракет[аиу]\b|\brocket\b", "food")}
CLOSURE_NOTE = (r"(закрил|закрит|припинил|припинен|не працює|більше не працю|банкрут|зупинил|ліквідов|ceased|closed down"
                r"|has closed|shut down|no longer (operat|work|availab|activ)|defunct|bankrupt|discontinued|stopped operat|suspended)")


def stale_knowledge():
    """Згадування закритих сервісів, пояснення їхнього закриття, рекомендації за LLM-суддею і стара назва Sense Bank."""
    responses = audit.load_jsonl("data/full_responses.jsonl")
    judgements = {tuple(j["key"]): j for j in audit.load_jsonl("data/full_judgements.jsonl")}
    for name, (pattern, industry) in CLOSED_SERVICES.items():
        rows = []
        for r in responses:
            hits = list(re.finditer(pattern, r["response_text"], re.I)) if r["industry"] == industry else []
            if not hits:
                continue
            note = any(re.search(CLOSURE_NOTE, r["response_text"][max(0, m.start() - 300):m.end() + 300], re.I) for m in hits)
            named = [b for b in judgements.get(audit.task_key(r), {}).get("brands", []) if re.search(pattern, b["name"], re.I)]
            rows.append({"system": audit.model_label(r), "closure_note": note, "recommended": any(b.get("recommended") for b in named)})
        df = pd.DataFrame(rows)
        print(name, len(df), "з поясненням закриття:", int(df.closure_note.sum()), "рекомендовано:", int(df.recommended.sum()),
              df.system.value_counts().to_dict())
    banks = [r["response_text"] for r in responses if r["industry"] == "bank"]
    new = [bool(re.search(r"sense\s?bank|sense\s?superapp|сенс\s?банк", t, re.I)) for t in banks]
    old = [bool(re.search(r"альфа[-\s]?банк|alfa[-\s]?bank", t, re.I)) for t in banks]
    print("Sense Bank: відповідей", sum(n or o for n, o in zip(new, old)), "зі старою назвою", sum(old), "лише стара", sum(o and not n for n, o in zip(new, old)))


def own_site_citations():
    """Кореляція цитувань власного сайту бренду в Sonar зі згадуваністю бренду в Sonar."""
    responses = [r for r in audit.load_jsonl("data/full_responses.jsonl") if r["web_search"]]
    rows = []
    for industry, spec in INDUSTRIES.items():
        part = [r for r in responses if r["industry"] == industry]
        cites = audit.citations_frame(part, spec["domains"])
        counts = cites[cites.domain_type == "brand_site"].groupby("brand").size()
        panel = inf.brand_panel(part, industry)
        rates = panel.groupby("brand").mentioned.mean()
        rows += [{"industry": industry, "brand": b, "citations": int(counts.get(b, 0)), "mr": rates[b]} for b in spec["brands"]]
    df = pd.DataFrame(rows)
    print("ρ(цитування сайту, MR у Sonar) =", spearmanr(df.citations, df.mr))
    for industry, g in df.groupby("industry"):
        print("  ", industry, round(spearmanr(g.citations, g.mr).statistic, 2))

SOURCE_LABELS = {"brand_site": "Сайт бренду", "portal": "Фінансовий чи галузевий портал", "media": "Медіа",
                 "regulator_gov": "Регулятор, державний ресурс", "social_forum": "Соцмережі й форуми",
                 "app_store": "Магазин застосунків", "wikipedia": "Вікіпедія", "other": "Інше"}
INDUSTRY_LABELS = {"bank": "Банки", "ecom": "Торгівля", "pharma": "Аптеки", "post": "Логістика", "food": "Доставка їжі"}


def unified_sources():
    """Єдина типологія джерел: Sonar за доменом, Google AI Overviews за назвою ресурсу; рис. 2 — Sonar за галузями."""
    rows = [{"system": "Sonar", "industry": r["industry"], "lang": r["lang"], "type": sources.type_of_url(u)}
            for r in audit.load_jsonl("data/full_responses.jsonl") if r["web_search"] for u in r.get("citations") or []]
    rows += [{"system": "AIO", "industry": r["industry"], "lang": r["lang"], "type": sources.type_of_name(s["name"])}
             for r in audit.load_jsonl("data/google_responses.jsonl") if r["aio_present"] for s in r["source_names"]]
    df = pd.DataFrame(rows)
    table = df.groupby(["system", "lang"]).type.value_counts(normalize=True).unstack().fillna(0)[list(SOURCE_LABELS)]
    table.round(3).to_csv("data/source_types_unified.csv")
    print(table.round(3).to_string(), df.groupby("system").size().to_dict())

    sonar = df[df.system == "Sonar"]
    shares = sonar.groupby("industry").type.value_counts(normalize=True).unstack().fillna(0)[list(SOURCE_LABELS)]
    shares = shares.loc[list(INDUSTRY_LABELS)]
    matplotlib.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9})
    greys = ["#111111", "#444444", "#777777", "#999999", "#bbbbbb", "#d4d4d4", "#e8e8e8", "#ffffff"]
    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    left = np.zeros(len(shares))
    for (key, label), color in zip(SOURCE_LABELS.items(), greys):
        ax.barh([INDUSTRY_LABELS[i] for i in shares.index], shares[key], left=left, color=color, edgecolor="black",
                lw=.4, hatch="//" if key == "other" else None, label=label)
        left += shares[key].to_numpy()
    ax.invert_yaxis()
    ax.set_xlim(0, 1)
    ax.set_xlabel("Частка цитувань")
    ax.legend(frameon=False, fontsize=7.5, ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.18))
    plt.tight_layout()
    plt.savefig("figures/fig2_sonar_sources.png", dpi=300)
    plt.close()
    print("Sonar citations:", len(sonar))


def brands_per_answer(records):
    rows = []
    for industry, spec in INDUSTRIES.items():
        for r in records:
            if r["industry"] == industry:
                rows.append({"industry": industry, "lang": r["lang"], "system": audit.model_label(r) if "model" in r else "AIO",
                             "n": len(audit.find_mentions(r["response_text"], spec["brands"]))})
    return pd.DataFrame(rows)


def geo_control():
    """Відношення кількості українських брендів en ÷ uk з реченням про геолокацію і без нього (рис. 4)."""
    full = brands_per_answer(audit.load_jsonl("data/full_responses.jsonl"))
    nogeo = brands_per_answer(audit.load_jsonl("data/nogeo_en_responses.jsonl"))
    google = brands_per_answer([r for r in audit.load_jsonl("data/google_responses.jsonl") if r["aio_present"]])
    kind = lambda s: "Sonar" if "sonar" in s else "LLM"
    full["kind"], nogeo["kind"], google["kind"] = full.system.map(kind), nogeo.system.map(kind), "Google"
    uk = full[full.lang == "uk"].groupby(["industry", "kind"]).n.mean()
    uk_google = google[google.lang == "uk"].groupby("industry").n.mean()
    ratios = pd.DataFrame({
        "LLM, з реченням": full[full.lang == "en"].query("kind == 'LLM'").groupby("industry").n.mean() / uk.xs("LLM", level="kind"),
        "LLM, без речення": nogeo.query("kind == 'LLM'").groupby("industry").n.mean() / uk.xs("LLM", level="kind"),
        "Sonar, з реченням": full[full.lang == "en"].query("kind == 'Sonar'").groupby("industry").n.mean() / uk.xs("Sonar", level="kind"),
        "Sonar, без речення": nogeo.query("kind == 'Sonar'").groupby("industry").n.mean() / uk.xs("Sonar", level="kind"),
        "Google, без речення (gl=ua)": google[google.lang == "en"].groupby("industry").n.mean() / uk_google,
    })
    ratios = ratios.loc[list(INDUSTRY_LABELS)]
    print(ratios.round(2).to_string())
    ratios.round(3).to_csv("data/geo_control_ratios.csv")

    matplotlib.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9})
    styles = {"LLM, з реченням": ("#d9d9d9", None), "LLM, без речення": ("#d9d9d9", "///"),
              "Sonar, з реченням": ("#8c8c8c", None), "Sonar, без речення": ("#8c8c8c", "///"),
              "Google, з реченням": ("#111111", None), "Google, без речення (gl=ua)": ("#111111", "///")}
    order = [c for c in styles if c in ratios.columns]
    x = np.arange(len(ratios)); w = 0.8 / len(order)
    fig, ax = plt.subplots(figsize=(8, 4.3))
    for i, col in enumerate(order):
        color, hatch = styles[col]
        ax.bar(x - 0.4 + w * (i + 0.5), ratios[col], w, color=color, edgecolor="white" if color == "#111111" and hatch else "black",
               hatch=hatch, lw=.5, label=col)
    ax.axhline(1, color="black", lw=.8, ls="--")
    ax.set_xticks(x); ax.set_xticklabels([INDUSTRY_LABELS[i] for i in ratios.index]); ax.set_ylim(0, 1.2)
    ax.set_ylabel("Бренди/відповідь: en ÷ uk")
    ax.legend(frameon=False, fontsize=7.5, loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=3)
    plt.tight_layout()
    plt.savefig("figures/fig4_language_by_system.png", dpi=300)
    plt.close()

    per = pd.concat([full.assign(cond="з реченням"), nogeo.assign(cond="без речення")])
    print(per.groupby(["industry", "lang", "cond", "system"]).n.mean().unstack("system").round(2).to_string())
    print("Google uk brands/answer:", google[google.lang == "uk"].groupby("industry").n.mean().round(2).to_dict())

GLOBAL_BRANDS = {"Amazon": r"\bamazon\b", "Walmart": r"walmart", "DHL": r"\bdhl\b", "UPS": r"\bups\b", "Chase": r"\bchase\b",
                 "FedEx": r"fedex", "Uber Eats": r"uber\s?eats", "DoorDash": r"doordash", "Best Buy": r"best buy"}


def google_geo_check():
    """Google з реченням «I live in Ukraine»: заміщення глобальними брендами, лідери, чесне відношення на спільних запитах."""
    geo = audit.load_jsonl("data/google_geo_responses.jsonl")
    base = [r for r in audit.load_jsonl("data/google_responses.jsonl") if r["aio_present"]]
    en_geo, en_base = [r for r in geo if r["lang"] == "en"], [r for r in base if r["lang"] == "en"]
    has_global = lambda r: any(re.search(p, r["response_text"], re.I) for p in GLOBAL_BRANDS.values())
    print("частка en-відповідей з глобальними брендами: з реченням", round(np.mean([has_global(r) for r in en_geo]), 2),
          "без", round(np.mean([has_global(r) for r in en_base]), 2))
    amazon = lambda rs: round(np.mean([bool(re.search(GLOBAL_BRANDS["Amazon"], r["response_text"], re.I)) for r in rs]), 3)
    print("Amazon: з реченням", amazon(en_geo), "без", amazon(en_base))

    def rate(records, industry, brand):
        part = [r for r in records if r["industry"] == industry]
        return round(np.mean([any(m["brand"] == brand for m in audit.find_mentions(r["response_text"], INDUSTRIES[industry]["brands"]))
                              for r in part]), 2)
    for industry, brand in [("ecom", "Rozetka"), ("bank", "ПриватБанк"), ("post", "Нова Пошта"), ("food", "Glovo")]:
        print(brand, "en з реченням", rate(en_geo, industry, brand), "en без", rate(en_base, industry, brand),
              "uk без", rate([r for r in base if r["lang"] == "uk"], industry, brand))
    ids = {r["query_id"] for r in geo if r["lang"] == "uk"}
    count = lambda rs: np.mean([len(audit.find_mentions(r["response_text"], INDUSTRIES["bank"]["brands"])) for r in rs])
    pick = lambda rs, lang: [r for r in rs if r["lang"] == lang and r["query_id"] in ids]
    print("банки, спільні", len(ids), "запитів: з реченням en/uk", round(count(pick(geo, "en")), 2), round(count(pick(geo, "uk")), 2),
          "; без", round(count(pick(base, "en")), 2), round(count(pick(base, "uk")), 2))

BANK_NAMES = {"ПриватБанк": r"приватбанк", "monobank": r"універсал", "Ощадбанк": r"ощадбанк", "Райффайзен Банк": r"райффайзен",
              "ПУМБ": r"пумб", "УкрСиббанк": r"укрсиббанк", "А-Банк": r'"А - БАНК"', "Sense Bank": r"сенс",
              "Укргазбанк": r"укргазбанк", "OTP Bank": r"отп", "Укрексімбанк": r"укрексімбанк", "Креді Агріколь": r"креді\s*агріколь",
              "Кредобанк": r"кредобанк"}


def market_comparison():
    """Ранговий зв'язок видимості з ринковими показниками (табл. 4): НБУ для банків, SimilarWeb/RetailersUA для торгівлі й аптек."""
    assets = pd.read_excel("data/market/aggregation_2026-08-01.xlsx", "Активи", header=None)
    deposits = pd.read_excel("data/market/FG_2026-08-01.xlsx", "01.08.2026", header=None)
    banks = []
    for brand, pattern in BANK_NAMES.items():
        a = assets[assets[2].astype(str).str.contains(pattern, case=False, regex=True)].iloc[0]
        d = deposits[deposits[1].astype(str).str.contains(pattern, case=False, regex=True)].iloc[0]
        banks.append({"industry": "bank", "brand": brand, "net_assets": float(a[32]), "depositors": int(d[2]), "deposits": float(d[4])})
    banks = pd.DataFrame(banks)
    traffic = pd.read_csv("data/market/traffic_retailersua_2025-09.csv")
    table3 = pd.read_csv("data/table3_ci.csv", index_col=0)
    google = [r for r in audit.load_jsonl("data/google_responses.jsonl") if r["aio_present"] and r["lang"] == "uk"]

    def aio_rate(industry, brand):
        part = [r for r in google if r["industry"] == industry]
        return np.mean([any(m["brand"] == brand for m in audit.find_mentions(r["response_text"], INDUSTRIES[industry]["brands"]))
                        for r in part])
    frames = []
    for df, measures in [(banks, ["depositors", "deposits", "net_assets"]), (traffic, ["visits_mln"])]:
        df = df.assign(mr=df.brand.map(table3.mr_est), fp=df.brand.map(table3.fp_est),
                       aio=[aio_rate(i, b) for i, b in zip(df.industry, df.brand)])
        for industry, g in df.groupby("industry"):
            for m in measures:
                cells = [f"{v} {spearmanr(g[m], g[v]).statistic:.2f} (p={spearmanr(g[m], g[v]).pvalue:.4f})" for v in ["mr", "fp", "aio"]]
                print(industry, m, len(g), " | ".join(cells))
        frames.append(df.assign(market=df[measures[0]]))
    pooled = pd.concat(frames)
    for c in ["market", "mr", "fp", "aio"]:
        pooled["r_" + c] = pooled.groupby("industry")[c].rank(pct=True)
    for v in ["mr", "fp", "aio"]:
        print("усі", len(pooled), v, round(spearmanr(pooled.r_market, pooled["r_" + v]).statistic, 2))
    pooled.to_csv("data/market/market_vs_visibility_all.csv", index=False)

ELECTRONICS_QUERIES = {"ecom-02", "ecom-05", "ecom-06", "ecom-07", "ecom-09", "ecom-12", "ecom-13", "ecom-15", "ecom-18"}


def rank_gaps(draws=2000, seed=5):
    """Розрив «ранг за ринком − ранг за MR» з 95 % бутстреп-інтервалом рангу MR; чутливість до запитів про техніку."""
    panel = inf.full_panel(audit.load_jsonl("data/full_responses.jsonl"))
    market = pd.read_csv("data/market/market_vs_visibility_all.csv")
    sets = {"банки (вкладники)": panel[panel.industry == "bank"],
            "торгівля, усі запити": panel[panel.industry == "ecom"],
            "торгівля без запитів про техніку": panel[(panel.industry == "ecom") & ~panel.query_id.isin(ELECTRONICS_QUERIES)],
            "аптеки": panel[panel.industry == "pharma"]}
    results = {}
    for label, part in sets.items():
        industry = part.industry.iloc[0]
        values = market[market.industry == industry].set_index("brand").market
        part = part[part.brand.isin(values.index)]
        rates, samples = inf.bootstrap_rates(part, "mentioned", ["brand"], draws=draws, seed=seed)
        ranks = pd.DataFrame(samples, columns=list(rates.index)).rank(axis=1, ascending=False)
        out = pd.DataFrame({"mr": rates.est, "r_mr": rates.est.rank(ascending=False),
                            "r_lo": ranks.quantile(0.025), "r_hi": ranks.quantile(0.975)})
        out["market"] = values.reindex(out.index)
        out["r_mkt"] = out.market.rank(ascending=False)
        out["gap"] = out.r_mkt - out.r_mr
        out["robust"] = (out.r_mkt < out.r_lo) | (out.r_mkt > out.r_hi)
        results[label] = out
        print("====", label, "ρ", round(spearmanr(out.market, out.mr).statistic, 2), f"p={spearmanr(out.market, out.mr).pvalue:.4f}")
        print(out.sort_values("gap")[["mr", "r_mkt", "r_mr", "r_lo", "r_hi", "gap", "robust"]].round(2).to_string())
    pd.concat(results, names=["set"]).to_csv("data/market/rank_gaps_ci.csv")

def brand_counts_all():
    """Кількість брендів у відповіді: усі (словник + LLM-суддя) і лише відстежувані; україномовні запити."""
    frames = [fullset.full_frame(audit.load_jsonl("data/full_responses.jsonl"), audit.load_jsonl("data/full_judgements.jsonl")),
              fullset.full_frame([r for r in audit.load_jsonl("data/google_responses.jsonl") if r["aio_present"]],
                                 audit.load_jsonl("data/google_judgements.jsonl")).assign(model_label="Google AIO")]
    full = pd.concat(frames)
    answers = full.drop_duplicates(["model_label", "industry", "query_id", "lang", "repeat"])
    uk = answers[answers.lang == "uk"]
    for column in ["n_all", "n_tracked"]:
        print(column)
        print(uk.groupby(["industry", "model_label"])[column].mean().unstack().round(1).to_string())
    google = full[full.model_label == "Google AIO"]
    print("Google: перше місце за брендом поза списком", google.drop_duplicates(["industry", "query_id", "lang", "repeat"])
          .groupby("industry").first_is_other.mean().round(2).to_dict())

def intent_permutation_tests():
    """Точний перестановочний тест міток наміру між запитами (одиниця — запит) з поправкою Холма."""
    panel = inf.full_panel(audit.load_jsonl("data/full_responses.jsonl"))

    def query_rates(part, brand):
        return part.groupby(["query_id", "intent"]).apply(lambda g: g[g.brand == brand].mentioned.mean()).reset_index(name="mr")

    def exact_p(rates, in_group):
        ids, values = rates.query_id.tolist(), dict(zip(rates.query_id, rates.mr))
        chosen = rates[in_group].query_id.tolist()
        observed = np.mean([values[q] for q in chosen]) - np.mean([values[q] for q in ids if q not in chosen])
        diffs = np.array([np.mean([values[q] for q in c]) - np.mean([values[q] for q in ids if q not in c])
                          for c in itertools.combinations(ids, len(chosen))])
        return observed, float(np.mean(np.abs(diffs) >= abs(observed) - 1e-12)), len(diffs)

    rows = []
    for industry, brand, a, b in [("bank", "Райффайзен Банк", "TRUST", "PRICE"), ("bank", "Креді Агріколь", "TRUST", "PRICE"),
                                  ("bank", "OTP Bank", "TRUST", "PRICE"), ("bank", "УкрСиббанк", "TRUST", "PRICE"),
                                  ("bank", "monobank", "BEST", "TRUST"), ("bank", "А-Банк", "BEST", "TRUST"),
                                  ("ecom", "Comfy", "PRICE", "BEST"), ("ecom", "Фокстрот", "PRICE", "BEST"), ("ecom", "Prom.ua", "BEST", "TASK")]:
        rates = query_rates(panel[(panel.industry == industry) & panel.intent.isin([a, b])], brand)
        d, p, n = exact_p(rates, rates.intent == a)
        rows.append({"brand": brand, "contrast": f"{a}−{b}", "diff": d, "p": p, "splits": n})
    for industry, brand in [("food", "Zakaz.ua"), ("ecom", "Kasta")]:
        rates = query_rates(panel[panel.industry == industry], brand)
        d, p, n = exact_p(rates, rates.intent == "COMP")
        rows.append({"brand": brand, "contrast": "COMP−інші", "diff": d, "p": p, "splits": n})
    table = pd.DataFrame(rows)
    table["p_holm"] = multipletests(table.p, method="holm")[1]
    table.round(4).to_csv("data/intent_permutation_tests.csv", index=False)
    print(table.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
    context_requests()
    stale_knowledge()
    own_site_citations()
    unified_sources()
    geo_control()
    google_geo_check()
    market_comparison()
    rank_gaps()
    brand_counts_all()
    intent_permutation_tests()
