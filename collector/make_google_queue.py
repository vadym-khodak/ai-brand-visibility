"""Черга запитів для google_aio_collector.js: python collector/make_google_queue.py [--geo] > queue.json"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import audit
from design import INDUSTRIES

geo = "--geo" in sys.argv
queue = [f"{q['query_id']}|{q['intent']}|{lang}|{audit.GEO_PREFIX[lang] if geo else ''}{q['text']}"
         for lang in ("uk", "en") for industry in INDUSTRIES for q in audit.build_industry_queries(industry, lang)]
print(json.dumps(queue, ensure_ascii=False))
