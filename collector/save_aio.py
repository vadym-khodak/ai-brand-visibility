"""Дописує один запис AI Overview у data/google_aio_pilot.jsonl: python save_aio.py <query_id> <intent> < json"""
import json, sys, datetime
qid, intent = sys.argv[1], sys.argv[2]
d = json.loads(sys.stdin.read())
if isinstance(d, str):
    d = json.loads(d)
rec = {"query_id": qid, "industry": qid.split("-")[0], "intent": intent, "lang": "uk", "repeat": 1,
       "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(), **d}
if rec.get("text", "").startswith("Огляд від ШІ"):
    rec["text"] = rec["text"][len("Огляд від ШІ"):].strip()
rec["sources"] = [s.replace(". Пов’язані результати.", "") for s in rec.get("sources", [])]
with open("data/google_aio_pilot.jsonl", "a", encoding="utf-8") as f:
    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
print("saved", qid, "aio" if rec.get("aio") else "no-aio", len(rec.get("text", "")), "chars")
