"""Виявляє в кінці відповіді запит до користувача на уточнення контексту та тип запитуваного контексту."""

import re

SOURCE_PANEL = re.compile(r"Спільна \d+ файл\w*|Shared \d+ files?|Related links|Show less")
SECOND_PERSON = {"uk": re.compile(r"\b(ви|вам|вас|ваш\w*)\b", re.I), "en": re.compile(r"\b(you|your)\b", re.I)}
REQUEST = {
    "uk": re.compile(r"(розкажіть|скажіть|уточніть|уточнюйте|напишіть|вкажіть|назвіть|поділіться"
                     r"|якщо ви (напишете|вкажете|розкажете|уточните|поділитеся)"
                     r"|щоб я (міг|могла|зміг|змогла) (порадити|підібрати|допомогти|підказати))", re.I),
    "en": re.compile(r"(if you (can )?(tell|share|let me know|provide|give|mention)|let me know|tell me"
                     r"|could you (share|tell|let)|would you like|do you (want|need|prefer|plan|have)"
                     r"|what is your|are you (looking|planning))", re.I),
}
CONTEXT_TYPES = {
    "location": r"(міст|район|регіон|област|сел[оа]|country|city|region|zip|location|neighbou?rhood|located)",
    "budget": r"(сум[аиу]|бюджет|скільки|дохід|ліміт|amount|budget|how much|income|limit)",
    "purpose": r"(для чого|мет[аиу]|плануєте|потреб|завдан|goal|purpose|use (it|the)|looking for|need)",
    "product": r"(препарат|ліки|товар|посилк|вага|розмір|валют|medication|item|parcel|weight|currenc|product)",
}


def answer_body(text):
    match = SOURCE_PANEL.search(text)
    return text[:match.start()] if match else text


def ending(text):
    return answer_body(text).strip()[-500:]


def invites_context(text, lang):
    tail = ending(text)
    questions = [s for s in re.split(r"(?<=[?])\s+", tail) if s.strip().endswith("?")]
    return bool(REQUEST[lang].search(tail)) or any(SECOND_PERSON[lang].search(q) for q in questions)


def requested_context(text):
    tail = ending(text)
    return {name for name, pattern in CONTEXT_TYPES.items() if re.search(pattern, tail, re.I)}
