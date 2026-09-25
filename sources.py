"""Єдина типологія джерел для Sonar (за доменом) і Google AI Overviews (за назвою ресурсу).

Кожен тип задано парою «домени — шаблон назви», тож ті самі ресурси потрапляють в один тип
незалежно від того, як система їх показує. Сайти відстежуваних брендів визначаються за доменами
і шаблонами брендів із design.py.
"""

import re
from urllib.parse import urlparse

from design import INDUSTRIES

SOURCE_TYPES = {
    "social_forum": (
        ["reddit.com", "facebook.com", "youtube.com", "t.me", "instagram.com", "x.com", "tiktok.com",
         "linkedin.com", "quora.com", "trustpilot.com"],
        r"reddit|youtube|facebook|instagram|tiktok|quora|linkedin|telegram|trustpilot"
        r"|відео, дивитися на сайті|video, watch on|·\s*r/",
    ),
    "wikipedia": (["wikipedia.org"], r"wikipedia|вікіпеді"),
    "regulator_gov": (
        ["gov.ua", "gov", "gov.uk", "europa.eu"],
        r"\bМОЗ\b|Держлікслужб|Національна служба здоров|Кабінет Міністрів|Національний банк|\bНБУ\b"
        r"|Держпродспоживслужб|Мінцифр|Фонд гарантування|єОселя|\(\.gov\)|Consumer Financial Protection"
        r"|Bundesamt|Federal Deposit|\bFDIC\b|National Institutes of Health|\bNHS\b",
    ),
    "app_store": (["play.google.com", "apps.apple.com"], r"Google Play|App Store"),
    "portal": (
        ["minfin.com.ua", "finance.ua", "uba.top", "forinsurer.com", "banker.ua", "bankchart.com.ua",
         "prostobank.ua", "financer.com.ua", "banksrating.com.ua", "inventure.com.ua", "kosht.media",
         "tabfinance.com.ua", "bank.com.ua", "napensii.ua", "apteki.ua", "liki.ua", "hotline.ua", "retailers.ua",
         "ipost.ua", "marketer.ua", "vseceni.ua", "nerdwallet.com", "bankrate.com", "moneysupermarket.com",
         "comparethemarket.com", "monito.com", "pharmacychecker.com", "investnews.com.ua"],
        r"Мінфін|Minfin|Finance\.ua|uba\.top|Forinsurer|Банкер|Banker\.ua|Financer|КОШТ|tabfinance|bank\.com\.ua"
        r"|Apteki\.ua|Liki\.ua|Hotline|Retailers|ipost|Всі ціни|FinAwards|NerdWallet|Bankrate|MoneySuperMarket"
        r"|Compare the Market|Monito|PharmacyChecker|investnews|Marketer",
    ),
    "media": (
        ["rbc.ua", "thepage.ua", "ua.news", "unn.ua", "24tv.ua", "focus.ua", "delo.ua", "informator.ua",
         "obozrevatel.com", "zaxid.net", "unian.ua", "mind.ua", "kyivpost.com", "interfax.com.ua", "forbes.ua",
         "forbes.com", "liga.net", "nv.ua", "ukrinform.ua", "bbc.com", "apostrophe.ua", "fakty.com.ua",
         "epravda.com.ua", "pravda.com.ua", "komersant.ua", "intellinews.com", "itc.ua", "village.com.ua",
         "mezha.net", "psm7.com", "rau.ua", "ukr.net", "20minut.ua", "telegraf.com.ua", "cnet.com", "yahoo.com",
         "nbcnews.com", "newsweek.com", "dou.ua", "ain.ua", "suspilne.media", "zn.ua", "consumerreports.org",
         "interfax.com", "reuters.com"],
        r"РБК|The Page|UA\.News|\bУНН\b|24 Канал|Фокус|Delo\.ua|Informator|Обозреватель|Zaxid|УНІАН|\bMind\b"
        r"|Kyiv Post|Інтерфакс|Interfax|Forbes|LIGA|New Voice|Укрінформ|\bBBC\b|Апостроф|Факти|Економічна правда"
        r"|Українська правда|Комерсант|ITC\.ua|The Village|Mezha|Ukr\.net|Дзеркало тижня|Харків Тудей|Радіо ТРЕК"
        r"|Моя Київщина|CNET|Yahoo|NBC News|Newsweek|Consumer Reports|Телеграф|Суспільне|\bDOU\b|\bAIN\b|Reuters",
    ),
}
NAME_ORDER = ["social_forum", "wikipedia", "regulator_gov", "app_store", "portal", "media"]
ALL_BRANDS = {b: p for spec in INDUSTRIES.values() for b, p in spec["brands"].items()}
ALL_DOMAINS = {b: d for spec in INDUSTRIES.values() for b, d in spec["domains"].items()}
BRAND_DOMAIN_STEMS = {d.split(".")[0] for ds in ALL_DOMAINS.values() for d in ds if len(d.split(".")[0]) >= 5}


def _host_matches(host, domains):
    return any(host == d or host.endswith("." + d) for d in domains)


def type_of_url(url):
    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    if any(_host_matches(host, d) for d in ALL_DOMAINS.values()):
        return "brand_site"
    for kind in NAME_ORDER:
        if _host_matches(host, SOURCE_TYPES[kind][0]):
            return kind
    return "other"


def type_of_name(name):
    for kind in NAME_ORDER:
        if re.search(SOURCE_TYPES[kind][1], name, re.I):
            return kind
    if any(re.search(p, name, re.I) for p in ALL_BRANDS.values()):
        return "brand_site"
    if any(stem in name.lower() for stem in BRAND_DOMAIN_STEMS):
        return "brand_site"
    return "other"
