import numpy as np
import pandas as pd

import inference as inf


def toy_panel():
    rows = []
    for q, hits in [("q1", [1, 1, 1, 1]), ("q2", [0, 0, 1, 1]), ("q3", [0, 0, 0, 0])]:
        for i, h in enumerate(hits):
            rows.append({"query_id": q, "brand": "A", "lang": "uk" if i < 2 else "en", "mentioned": h})
    return pd.DataFrame(rows)


def test_bootstrap_point_is_plain_rate_and_ci_brackets_it():
    rates, samples = inf.bootstrap_rates(toy_panel(), "mentioned", ["brand"], draws=500, seed=1)
    est, lo, hi = rates.loc["A", ["est", "lo", "hi"]]
    assert est == 6 / 12
    assert lo <= est <= hi
    assert samples.shape == (500, 1)


def test_query_weights_resample_whole_queries():
    w = inf.query_weights(3, 100, seed=2)
    assert w.shape == (100, 3) and (w.sum(axis=1) == 3).all()


def test_paired_difference_uses_same_draws():
    rates, samples = inf.bootstrap_rates(toy_panel(), "mentioned", ["brand", "lang"], draws=500, seed=3)
    lo, hi = inf.difference_ci(samples, rates.index, ("A", "uk"), ("A", "en"))
    assert lo <= rates.loc[("A", "uk"), "est"] - rates.loc[("A", "en"), "est"] <= hi


def test_script_language():
    assert inf.script_language("PrivatBank (ПриватБанк) is the largest bank in Ukraine.") == "en"
    assert inf.script_language("Найбільший банк — ПриватБанк.") == "uk"


def test_invites_context():
    import clarify
    assert clarify.invites_context("Порада. Розкажіть, яку суму ви плануєте обміняти. Спільна 0 файлів Мінфін?", "uk")
    assert clarify.invites_context("Options above. If you can share your city, I can help.", "en")
    assert not clarify.invites_context("Monobank is popular. Shared 0 files Do you want a card?", "en")
    assert clarify.requested_context("Which city are you in and what is your budget?") == {"location", "budget"}
