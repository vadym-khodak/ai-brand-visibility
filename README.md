# Видимість українських брендів у відповідях генеративних систем: дані й код аудиту

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22957279.svg)](https://doi.org/10.5281/zenodo.22957279)

Дані та код до статті В. В. Ходака «Видимість українських брендів у відповідях генеративних пошукових систем: методика оцінювання та емпіричний аудит» (рукопис, 2026; Черкаський державний технологічний університет).

*English summary below.*

## Що тут є

Аудит небрендованих споживчих запитів:
- 42 українські бренди у п'яти галузях: банки, інтернет-торгівля, аптеки, поштова логістика, доставка їжі;
- 80 запитів українською та англійською;
- п'ять типів споживчого наміру.

Кожен запис відповіді містить модель, запит, мову, намір, номер повтору, час, текст відповіді, цитовані URL (для систем з пошуком) і сиру відповідь OpenRouter (`raw`). Ключ запису — `model`, `web_search`, `query_id`, `lang`, `geo`, `repeat`.

### Зібрані дані

| Набір | Файл | Записів | Як отримано |
|---|---|---|---|
| Основний збір, 18–21.09.2026: GPT-5.6, Claude Sonnet 5, Gemini 3.8 Flash, DeepSeek V4 Pro (без пошуку), Perplexity Sonar Pro (з пошуком); 5 повторів; перед запитом — «Я живу в Україні.» / «I live in Ukraine.» | `data/full_responses.jsonl` | 4 000 | `full_run.ipynb` |
| Пілот (банки), 18.09.2026; частину відповідей перенесено в основний збір | `data/pilot_responses.jsonl`, `data/pilot_judgements.jsonl` | 750 | `pilot_banks.ipynb` |
| Google AI Overviews, 22–24.09.2026, 5 зрізів, `hl` = мова запиту, `gl=ua` | `data/google_responses.jsonl` | 800 | `google_ingest.py --rebuild` із сирих вивантажень нижче |
| Сирі вивантаження Google: пілот (зріз 1, частина), зрізи 1–5; зріз 3 зібрано двома частинами (`day3_partial` + `day3_part2`) | `data/google_aio_pilot.jsonl`, `data/google_aio_day1.json` … `day5.json` | — | `collector/` |
| Контроль: англомовні запити до API-систем без речення про Україну, 2 повтори | `data/nogeo_en_responses.jsonl` | 800 | `run_nogeo.py` |
| Контроль: Google з реченням «I live in Ukraine» (80 англомовних і 8 україномовних банківських запитів) | `data/google_geo_responses.jsonl`; сире — `data/google_aio_geo.json` | 88 | `google_ingest.py --geo google_aio_geo.json` |
| Перелік запитів обома мовами з галуззю й наміром | `data/queries.csv`, `data/queries.md` | 80 | `export_queries.py` з `design.py` |

### Розмітка

| Що | Файл | Записів | Як отримано |
|---|---|---|---|
| LLM-суддя (openai/gpt-5.6-luna): усі бренди відповіді, тональність, рекомендація | `data/full_judgements.jsonl`, `data/google_judgements.jsonl` | 4 000 / 797 | `full_run.ipynb`, `run_judge_google.py` |
| Другий суддя тональності (anthropic/claude-sonnet-5) на випадковій вибірці | `data/validation_judge2.jsonl` | 200 | `validate_judge.py run` |
| Кінцівки відповідей (запит контексту): вибірка, два анотатори, повна розмітка | `data/clarify_sample.jsonl`, `data/clarify_annotations.jsonl`, `data/clarify_full.jsonl` | 280 / 560 / 4 797 | `validate_clarify.py` |
| Сліпа таблиця для ручної перевірки кінцівок (не заповнена) | `data/clarify_human_check.csv` | 60 | `validate_clarify.py sheet` |
| Мітки наміру від двох LLM-кодувальників | `data/intent_coding.jsonl` | 160 | `code_intents.py` |

### Ринкові показники (`data/market/`)

| Файл | Зміст |
|---|---|
| `aggregation_2026-08-01.xlsx` | НБУ: агреговані показники банків станом на 01.08.2026 (аркуш «Активи» — чисті активи) |
| `FG_2026-08-01.xlsx` | НБУ: вклади фізичних осіб за банками станом на 01.08.2026 (кількість вкладників, сума вкладів) |
| `traffic_retailersua_2025-09.csv` | Відвідуваність сайтів інтернет-магазинів і аптек за SimilarWeb у рейтингу RetailersUA, 09.2025 |
| `market_vs_visibility_all.csv` | Ринкові показники разом зі згадуваністю, першим місцем і рангами (генерує `article_stats.py`) |
| `rank_gaps_ci.csv` | Розриви «ранг за ринком − ранг за згадуваністю» з бутстреп-інтервалами (генерує `article_stats.py`) |

### Обчислені результати (генерують скрипти)

| Файл | Що містить | Скрипт |
|---|---|---|
| `data/brand_visibility_ci.csv`, `data/brand_visibility_table.md` | Згадуваність і перше місце кожного бренду з 95 % ДІ, ранг, розкид за системами, тональність (табл. 3 статті) | `article_stats.py` |
| `data/bank_intent_ci.csv` | Згадуваність банків за типом наміру з 95 % ДІ | `article_stats.py` |
| `data/intent_permutation_tests.csv` | Точні перестановочні тести наміру з поправкою Холма | `article_stats.py` |
| `data/language_gaps_ci.csv` | Мовні розриви за брендами з ДІ і поправкою Бенджаміні — Гохберга | `article_stats.py` |
| `data/source_types_unified.csv` | Структура джерел цитування Sonar і Google за єдиною типологією | `article_stats.py` |
| `data/geo_control_ratios.csv` | Кількість українських брендів в англомовних відповідях відносно україномовних, з реченням і без | `article_stats.py` |
| `data/system_heterogeneity.csv` | Розбіжності згадуваності між системами для кожного бренду (критерій Вальда, BH) | `robustness_stats.py` |
| `data/mde_table.csv` | Мінімальний виявний ефект для протоколу аудиту | `robustness_stats.py` |
| `data/clarify_validation.csv`, `data/clarify_rates.csv` | Точність лексичного детектора; частки запитів контексту за системами з ДІ | `validate_clarify.py` |
| `figures/fig1_banks_heatmap.png` … `fig4_language_by_system.png` | Рисунки статті | `article_stats.py` |

## Код

| Файл | Призначення |
|---|---|
| `design.py` | Галузі, бренди (регулярні вирази з транслітераціями), домени брендів, запити двома мовами, іноземні материнські групи |
| `audit.py` | Збір через OpenRouter, LLM-суддя, пошук згадок, базові показники |
| `full_run.ipynb`, `pilot_banks.ipynb` | Основний збір і пілот; для запуску потрібен ключ API, уже зібрані відповіді пропускаються |
| `run_nogeo.py`, `run_judge_google.py` | Контрольний збір без геоконтексту; суддя для Google |
| `collector/` | Збір Google AI Overviews у браузері: `google_aio_collector.js`, `make_google_queue.py`; `save_aio.py` — запис пілотних відповідей |
| `google_ingest.py` | Зведення сирих вивантажень Google |
| `export_queries.py` | Перелік запитів у `data/queries.csv` і `data/queries.md` |
| `inference.py` | Кластерний бутстреп за запитами, мовні розриви, логістична GEE |
| `fullset.py` | Перше місце й ранг серед усіх брендів відповіді (словник + суддя) |
| `sources.py` | Єдина типологія джерел для Sonar (за доменом) і Google (за назвою ресурсу) |
| `clarify.py`, `validate_clarify.py` | Кінцівки відповідей: лексичний детектор, LLM-анотування, валідація |
| `validate_judge.py` | Згода двох LLM-суддів щодо тональності й рекомендацій |
| `code_intents.py` | Перевірка міток наміру двома LLM-кодувальниками |
| `article_stats.py` | Основні результати статті: таблиці, мовні розриви, GEE, джерела, ринок, контрольні збори, рисунки |
| `robustness_stats.py` | Перевірки стійкості: відбір брендів, латинське написання, лише рекомендації, розбіжності між системами, чутливість банківських розривів, мінімальний виявний ефект, повнота словника |
| `test_audit.py`, `test_inference.py` | Тести |

## Відтворення

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python article_stats.py
python robustness_stats.py
python validate_clarify.py report
python validate_clarify.py full-report
python validate_judge.py
python code_intents.py
```

Для аналізу ключ API не потрібен: скрипти працюють з наявними файлами. `code_intents.py` і `validate_judge.py run` звертаються до API лише для записів, яких ще немає у відповідних файлах.

**Ключ API.** Для нового збору скопіюйте `.env.example` у `.env` і вкажіть `OPENROUTER_API_KEY`. Прямі витрати на основний збір становили близько 29 дол. США.

**Збір Google AI Overviews** напівручний: скрипт із `collector/` виконується в консолі браузера на google.com, а перевірки «я не робот» дослідник проходив вручну. Автоматизований збір результатів пошуку може суперечити умовам використання Google, тож за повторення цього кроку відповідає користувач.

## Обмеження даних

- Відповіді генеративних систем стохастичні й змінюються з оновленнями моделей. Дані описують стан на вересень 2026 р.
- Основні оцінки отримано з явним реченням про проживання в Україні.
- API-системи опитано без персоналізації й історії. Google опитано у вбудованому браузері (Chromium) без входу в обліковий запис, але з профілем, що не очищувався між запитами, і з IP-адреси в Україні.
- Тональність і кінцівки відповідей класифікували мовні моделі без людської розмітки. Для ручної перевірки є сліпа таблиця `data/clarify_human_check.csv`.
- Російськомовні запити свідомо виключено.

## Ліцензії

| Що | Ліцензія | Файл |
|---|---|---|
| Код | MIT | `LICENSE` — англійський оригінал; `LICENSE.uk` — український переклад |
| Дані, створені в межах дослідження (запити, словник, розмітка, зведені набори, обчислені таблиці) | CC BY 4.0 | `data/LICENSE` — сфера дії двома мовами, офіційний український переклад і англійський оригінал юридичного тексту |

- Тексти відповідей генеративних систем ліцензуються лише в межах прав автора; їх використання регулюють також умови відповідних сервісів.
- Ринкові дані належать їхнім джерелам — Національному банку України (bank.gov.ua) і RetailersUA / SimilarWeb — і ліцензією не охоплюються.

## Цитування

Набір даних: Ходак В. В. Visibility of Ukrainian brands in generative AI answers: audit data and code : набір даних. Zenodo, 2026. DOI: [10.5281/zenodo.22957279](https://doi.org/10.5281/zenodo.22957279) (DOI усіх версій; окремі версії мають власні DOI, наприклад v1.1.0 — 10.5281/zenodo.22957280). Див. також `CITATION.cff`. Після публікації статті тут з'явиться її бібліографічний опис.

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

`article_stats.py` and `robustness_stats.py` reproduce all numbers, tables and figures in the article. The analysis needs no API key.

Licenses: code under MIT (`LICENSE`; Ukrainian translation in `LICENSE.uk`); research-generated data under CC BY 4.0 (`data/LICENSE`, scope in both languages, the official Ukrainian translation and the English legal code). Model outputs are subject to their providers' terms; market data belong to their sources.
