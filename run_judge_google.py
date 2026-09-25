"""LLM-суддя для відповідей Google AI Overviews: повний перелік брендів для підрахунку першого місця й кількості брендів."""

from dotenv import find_dotenv, load_dotenv

import audit

JUDGE_MODEL = "openai/gpt-5.6-luna"

if __name__ == "__main__":
    load_dotenv(find_dotenv(usecwd=True))
    records = [r for r in audit.load_jsonl("data/google_responses.jsonl") if r["aio_present"]]
    failed = audit.run_judging(records, "data/google_judgements.jsonl", JUDGE_MODEL)
    print("помилок:", len(failed))
