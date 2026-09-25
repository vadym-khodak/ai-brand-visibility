# Видимість українських брендів у відповідях генеративних систем: дані й код аудиту

Дані та код до статті В. В. Ходака «Видимість українських брендів у відповідях генеративних пошукових систем: методика оцінювання та емпіричний аудит» (рукопис, 2026; Черкаський державний технологічний університет).

*English summary below.*

## Що тут є

Аудит небрендованих споживчих запитів:
- 42 українські бренди у п'яти галузях: банки, інтернет-торгівля, аптеки, поштова логістика, доставка їжі;
- 80 запитів українською та англійською;
- п'ять типів споживчого наміру.

| Набір | Файл | Записів |
|---|---|---|
| Основний збір, 18–21.09.2026: GPT-5.6, Claude Sonnet 5, Gemini 3.8 Flash, DeepSeek V4 Pro (без пошуку), Perplexity Sonar Pro (з пошуком); 5 повторів; перед запитом — речення «Я живу в Україні.» / «I live in Ukraine.» | `data/full_responses.jsonl` | 4 000 |
| Оцінки LLM-судді (openai/gpt-5.6-luna): усі бренди відповіді, тональність, рекомендація | `data/full_judgements.jsonl` | 4 000 |
| Google AI Overviews, 22–24.09.2026, 5 зрізів, веб-інтерфейс, `hl` = мова запиту, `gl=ua` | `data/google_responses.jsonl`; сирі вивантаження — `data/google_aio_*.json`, `data/google_aio_pilot.jsonl` | 800 |
| Оцінки LLM-судді для Google AI Overviews | `data/google_judgements.jsonl` | 797 |
| Контроль: англомовні запити до API-систем без речення про Україну, 2 повтори | `data/nogeo_en_responses.jsonl` | 800 |
| Контроль: Google з реченням «I live in Ukraine» | `data/google_geo_responses.jsonl` (сире — `data/google_aio_geo.json`) | 88 |
| Пілот (банки), 18.09.2026 | `data/pilot_responses.jsonl`, `data/pilot_judgements.jsonl` | 750 |
| Другий суддя тональності (anthropic/claude-sonnet-5), вибірка | `data/validation_judge2.jsonl` | 200 |
| Кінцівки відповідей (запит контексту): вибірка з двома анотаторами і повна розмітка | `data/clarify_sample.jsonl`, `data/clarify_annotations.jsonl`, `data/clarify_full.jsonl` | 280 / 560 / 4 797 |
| Ринкові показники: НБУ станом на 01.08.2026; відвідуваність сайтів за SimilarWeb у рейтингу RetailersUA, 09.2025 | `data/market/` | — |
| Обчислені таблиці й інтервали | `data/*.csv`, `data/table3.md` | — |

Кожен запис відповіді містить:
- модель, запит, мову, намір, номер повтору, час;
- текст відповіді;
- цитовані URL (для систем з пошуком);
- сиру відповідь OpenRouter (`raw`).

## Код

| Файл | Призначення |
|---|---|
| `design.py` | Галузі, бренди (регулярні вирази з транслітераціями), домени брендів, запити двома мовами, іноземні материнські групи |
| `audit.py` | Збір через OpenRouter, LLM-суддя, пошук згадок, базові показники |
| `full_run.ipynb`, `pilot_banks.ipynb` | Основний збір і пілот |
| `run_nogeo.py`, `run_judge_google.py` | Контрольний збір без геоконтексту; суддя для Google |
| `collector/` | Збір Google AI Overviews у браузері: `google_aio_collector.js`, `make_google_queue.py`, `aio_sink.py`, `save_aio.py` |
| `google_ingest.py` | Зведення сирих вивантажень Google; `python google_ingest.py --rebuild` відтворює `data/google_responses.jsonl` побайтово |
| `inference.py` | Кластерний бутстреп за запитами, мовні розриви з поправкою Бенджаміні — Гохберга, логістична GEE |
| `fullset.py` | Перше місце й ранг серед усіх брендів відповіді (словник + суддя) |
| `sources.py` | Єдина типологія джерел для Sonar (за доменом) і Google (за назвою ресурсу) |
| `clarify.py`, `validate_clarify.py` | Кінцівки відповідей: лексичний детектор, LLM-анотування, валідація |
| `revision_stats.py`, `round3_stats.py` | Усі числа, таблиці й рисунки статті |
| `test_audit.py`, `test_inference.py` | Тести |

## Відтворення

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python revision_stats.py
python round3_stats.py
python validate_clarify.py report
python validate_clarify.py full-report
```

Що рахує кожен скрипт:
- `revision_stats.py` — табл. 3–4, мовні розриви, GEE, джерела, ринкові показники, рисунки;
- `round3_stats.py` — стійкість мовної асиметрії, розбіжності між системами;
- `validate_clarify.py` — згода анотаторів і частки запитів контексту.

**Ключ API.** Для аналізу він не потрібен. Для нового збору скопіюйте `.env.example` у `.env` і вкажіть `OPENROUTER_API_KEY`. Прямі витрати на основний збір становили близько 29 дол. США.

**Збір Google AI Overviews** напівручний: скрипт із `collector/` виконується в консолі браузера на google.com, а перевірки «я не робот» дослідник проходив вручну. Автоматизований збір результатів пошуку може суперечити умовам використання Google, тож за повторення цього кроку відповідає користувач.

## Обмеження даних

- Відповіді генеративних систем стохастичні й змінюються з оновленнями моделей. Дані описують стан на вересень 2026 р.
- Основні оцінки отримано з явним реченням про проживання в Україні.
- API-системи опитано без персоналізації й історії, Google — без входу в обліковий запис.
- Тональність і кінцівки відповідей класифікували мовні моделі без людської розмітки. Для ручної перевірки є сліпа таблиця `data/clarify_human_check.csv`.
- Російськомовні запити свідомо виключено.

## Ліцензії

- Код — MIT (`LICENSE`).
- Дані, створені в межах дослідження (запити, словник, розмітка, обчислені таблиці), — CC BY 4.0.
- Тексти відповідей генеративних систем наведено для дослідницького аналізу. Права на них визначають умови відповідних сервісів.
- Ринкові дані належать їхнім джерелам: Національний банк України (bank.gov.ua), RetailersUA / SimilarWeb.

## Цитування

Див. `CITATION.cff`. Після публікації статті тут з'явиться її бібліографічний опис.

---

## English summary

Data and code for an audit of how generative AI systems mention Ukrainian brands in answers to unbranded consumer queries.

What is included:
- 42 brands in 5 industries and 80 queries in Ukrainian and English;
- 4,000 answers from five systems collected via OpenRouter;
- 800 Google AI Overviews collected in five runs;
- LLM-judge annotations;
- control collections without geographic context;
- market benchmarks from the National Bank of Ukraine and SimilarWeb.

`revision_stats.py` and `round3_stats.py` reproduce all numbers, tables and figures in the article. The analysis needs no API key.

Code is licensed under MIT and research-generated data under CC BY 4.0. Model outputs are subject to their providers' terms.
