import audit as a


def test_mentions_order_and_inflections():
    text = "Найчастіше радять monobank, далі ПриватБанку та Ощад. Також є ПУМБ і Райффайзен Банк."
    brands = [m["brand"] for m in a.find_mentions(text, a.BANK_BRANDS)]
    assert brands == ["monobank", "ПриватБанк", "Ощадбанк", "ПУМБ", "Райффайзен Банк"], brands


def test_no_false_positives():
    text = "Це приватний, а банк надає ощадний рахунок; монополія на ринку відсутня. Отримайте оптимальний тариф."
    assert a.find_mentions(text, a.BANK_BRANDS) == []


def test_aliases():
    text = "Alfa-Bank Ukraine (now Sense Bank), A-Bank, OTP Bank, UKRSIBBANK, Ukrgasbank, Privat24"
    brands = {m["brand"] for m in a.find_mentions(text, a.BANK_BRANDS)}
    assert brands == {"Sense Bank", "А-Банк", "OTP Bank", "УкрСиббанк", "Укргазбанк", "ПриватБанк"}, brands


def brands_in(industry, text):
    return [m["brand"] for m in a.find_mentions(text, a.INDUSTRIES[industry]["brands"])]


def test_new_banks():
    assert set(brands_in("bank", "Укрексімбанку, Креді Агріколь Банк і Кредобанк; Credit Agricole")) == {"Укрексімбанк", "Креді Агріколь", "Кредобанк"}


def test_ecom():
    text = "Радять Rozetka (Розетка), Prom.ua, Епіцентр, Comfy, Фокстрот, Алло, MOYO, Kasta, MAUDAU і Цитрус."
    assert len(brands_in("ecom", text)) == 10
    noise = "Перевірте розетки вдома, цитрусові корисні, це епіцентр подій, каста воїнів, промисловий товар, алло, слухаю."
    assert brands_in("ecom", noise) == [], brands_in("ecom", noise)


def test_pharma():
    text = ("Аптека 9-1-1, Подорожник, АНЦ (Аптека Низьких Цін), Аптека Доброго Дня, мережа «Бажаємо здоров'я», "
            "Аптека оптових цін, аптека D.S., аптека Копійка, Tabletki.ua та Liki24.")
    assert len(brands_in("pharma", text)) == 10, brands_in("pharma", text)
    noise = "Доброго дня! Сік подорожника — лікарський засіб. Приймайте таблетки двічі на день. Бажаємо здоров'я! Кожна копійка важлива."
    assert brands_in("pharma", "Мережі: **Бажаємо здоров’я**, **Копійка** та АНЦ.") == ["Бажаємо здоров'я", "Копійка", "АНЦ"]
    assert brands_in("pharma", noise) == [], brands_in("pharma", noise)


def test_post_and_food():
    text = "Нової Пошти, Укрпошта, Meest, «Делівері» (Delivery-Auto) та САТ."
    assert brands_in("post", "великі вантажі — **Delivery/SAT**") == ["Delivery", "САТ"]
    assert a.match_brand("Бажаємо здоров’я", a.INDUSTRIES["pharma"]["brands"]) == "Бажаємо здоров'я"
    assert a.match_brand("Delivery", a.INDUSTRIES["post"]["brands"]) == "Delivery"
    assert len(brands_in("post", text)) == 5, brands_in("post", text)
    noise = "Fast delivery is important. Delivery time varies. Нова поштова скринька не потрібна? Сат на супутнику."
    assert brands_in("post", noise) == [], brands_in("post", noise)
    assert set(brands_in("food", "Glovo, Bolt Food, Zakaz.ua, доставка від Сільпо")) == {"Glovo", "Bolt Food", "Zakaz.ua", "Сільпо"}


def test_queries_bilingual():
    for key, industry in a.INDUSTRIES.items():
        uk, en = a.build_industry_queries(key, "uk"), a.build_industry_queries(key, "en")
        assert [q["query_id"] for q in uk] == [q["query_id"] for q in en]
        assert all(q["text"] for q in uk + en)
    assert sum(len(i["queries"]) for i in a.INDUSTRIES.values()) == 80


def test_classify_domain():
    assert a.classify_domain("https://www.monobank.ua/rates", a.BANK_BRAND_DOMAINS) == ("monobank.ua", "brand_site", "monobank")
    assert a.classify_domain("https://uk.wikipedia.org/wiki/X", a.BANK_BRAND_DOMAINS)[1] == "wikipedia"
    assert a.classify_domain("https://index.minfin.com.ua/", a.BANK_BRAND_DOMAINS)[1] == "fin_portal"
    assert a.classify_domain("https://example.com", a.BANK_BRAND_DOMAINS)[1] == "other"


def test_extract_citations_dedup():
    msg = {"annotations": [
        {"type": "url_citation", "url_citation": {"url": "https://a.ua"}},
        {"type": "url_citation", "url_citation": {"url": "https://a.ua"}},
        {"type": "file", "file": {}},
    ]}
    assert a.extract_citations(msg) == ["https://a.ua"]


def test_detect_language():
    assert a.detect_language("Найкращий банк — це той, що підходить вам.") == "uk"
    assert a.detect_language("Вопрос о лучшем банке зависит от ваших потребностей, это важно.") == "ru"
    assert a.detect_language("The best bank depends on your needs.") == "en"


def fake_records():
    queries = a.build_queries("bank", a.BANK_QUERIES[:2])
    cfgs = [{"model": "x/m1", "web_search": False}, {"model": "x/m1", "web_search": True}]
    texts = ["monobank і ПриватБанк", "monobank", "ПриватБанк і monobank"]
    records = []
    for t in a.build_tasks(cfgs, queries, repeats=3):
        records.append({**t, "response_text": texts[t["repeat"] - 1], "finish_reason": "stop",
                        "citations": ["https://monobank.ua/"] if t["web_search"] else [], "usage": {"cost": 0.01}})
    return records


def test_tables():
    records = fake_records()
    assert len(records) == 12 and records[0]["prompt"].startswith("Я живу в Україні. ")
    responses = a.responses_frame(records)
    mentions = a.mentions_frame(records, a.BANK_BRANDS)
    vis = a.visibility_table(responses, mentions).set_index(["model_label", "brand"])
    assert vis.loc[("m1", "monobank"), "mention_rate"] == 1.0
    assert vis.loc[("m1", "ПриватБанк"), "mention_rate"] == 0.667
    assert vis.loc[("m1", "monobank"), "first_place_rate"] == 0.667
    sov = a.share_of_voice(mentions)
    assert abs(sov.groupby("model_label")["share_of_voice"].sum() - 1).max() < 0.01
    stab = a.repeat_stability(responses, mentions)
    assert abs(stab["jaccard"].iloc[0] - (0.5 + 1 + 0.5) / 3) < 1e-9
    cites = a.citations_frame(records, a.BANK_BRAND_DOMAINS)
    assert len(cites) == 6 and set(cites["domain_type"]) == {"brand_site"}


def test_sentiment_frame():
    records = fake_records()
    judgements = [{"key": list(a.task_key(records[0])), "brands": [
        {"name": "Монобанк", "sentiment": 1, "recommended": True},
        {"name": "Revolut", "sentiment": 0, "recommended": False},
    ]}]
    df = a.sentiment_frame(records, judgements, a.BANK_BRANDS)
    assert dict(zip(df["brand"], df["tracked"])) == {"monobank": True, "Revolut": False}


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)


def test_transliterated_pharmacy_and_retail_names():
    text = ("Chains: Apteka Dobroho Dnya, Bazhayemo Zdorovya, Podorozhnik, Low Price Pharmacy, Kopeyka. "
            "Аптека Бажаємо Здоров'я. Stores: CTRS (ctrs.com.ua), Epicenter.")
    assert {"Аптека Доброго Дня", "Бажаємо здоров'я", "Подорожник", "АНЦ", "Копійка"} <= set(brands_in("pharma", text))
    assert {"Цитрус", "Епіцентр"} <= set(brands_in("ecom", text))


def test_no_false_positive_on_wishes_and_wholesale():
    assert brands_in("pharma", "Бажаємо здоров'я! The wholesale price is regulated.") == []
