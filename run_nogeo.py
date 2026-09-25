"""Контрольний збір для зіставності з Google AI Overviews: англомовні запити без речення «I live in Ukraine»."""

from dotenv import find_dotenv, load_dotenv

import audit
from design import INDUSTRIES

MODEL_CONFIGS = [
    {"model": "openai/gpt-5.6-sol", "web_search": False},
    {"model": "anthropic/claude-sonnet-5", "web_search": False},
    {"model": "google/gemini-3.8-flash", "web_search": False},
    {"model": "deepseek/deepseek-v4-pro-0813", "web_search": False},
    {"model": "perplexity/sonar-pro", "web_search": True, "native_search": True},
]
REPEATS = 2
PATH = "data/nogeo_en_responses.jsonl"

if __name__ == "__main__":
    load_dotenv(find_dotenv(usecwd=True))
    tasks = [t for industry in INDUSTRIES
             for t in audit.build_tasks(MODEL_CONFIGS, audit.build_industry_queries(industry, "en"), REPEATS, lang="en", geo=False)]
    failed = audit.run_collection(tasks, PATH)
    print("помилок:", len(failed))
    for task, error in failed[:5]:
        print(task["model"], task["query_id"], error[:200])
