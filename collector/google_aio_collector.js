// Збір блоків Google AI Overview у браузері (відкрита вкладка https://www.google.com, консоль DevTools).
// 1. Вставити чергу: localStorage.aio_queue = JSON.stringify([...]) — рядки "query_id|INTENT|lang|текст запиту"
//    (генерує make_google_queue.py), localStorage.aio_idx = "0"; localStorage.aio_records = "[]".
// 2. Вставити цей файл і викликати aioStep() стільки разів, скільки запитів у черзі (по одному, з паузою).
//    Якщо функція повертає "CAPTCHA …", пройти перевірку вручну й повторити крок.
// 3. Вивантажити результат: copy(localStorage.aio_records) і зберегти як data/google_aio_dayN.json.

async function aioStep() {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const Q = JSON.parse(localStorage.aio_queue);
  const i = +localStorage.aio_idx;
  if (i >= Q.length) return 'DONE';
  const [id, intent, lang, text] = Q[i].split('|');
  let f = document.getElementById('aio_frame');
  if (!f) {
    f = document.createElement('iframe');
    f.id = 'aio_frame';
    f.style.cssText = 'width:1000px;height:900px;position:fixed;top:0;left:0;z-index:99999;background:#fff';
    document.body.appendChild(f);
  }
  f.src = '/search?q=' + encodeURIComponent(text) + '&hl=' + lang + '&gl=ua';
  await sleep(7000);
  const d = f.contentDocument;
  let b = d.body ? d.body.innerText : '';
  if (/нетиповий трафік|unusual traffic|не робот|not a robot/.test(b)) return 'CAPTCHA ' + id + ' ' + lang;
  const H = ['Огляд від ШІ', 'AI Overview'];
  const findContainer = () => {
    const h = [...d.querySelectorAll('h1,h2,h3,div,span')].find(e => e.childElementCount === 0 && H.includes(e.textContent.trim()));
    if (!h) return null;
    let c = h;
    for (let k = 0; k < 14 && c.parentElement; k++) {
      if (c.innerText.length > 800 && c.querySelectorAll('a[aria-label]').length > 0) break;
      c = c.parentElement;
    }
    return c;
  };
  let c = findContainer();
  let waited = 0;
  while ((!c || c.innerText.length < 150 || /подумати трохи довше|think a bit longer|Триває обробка|Generating/.test(c.innerText)) && waited < 20000) {
    await sleep(5000);
    waited += 5000;
    c = findContainer();
  }
  const btn = [...d.querySelectorAll('[aria-label],[role=button]')].find(e =>
    /Показати більше|Show more/.test((e.getAttribute('aria-label') || '') + ' ' + e.innerText) &&
    e.getBoundingClientRect().top > 0 && e.getBoundingClientRect().top < 1400);
  if (btn) { btn.click(); await sleep(2500); c = findContainer(); }
  b = d.body.innerText;
  const rec = { id, intent, lang, ts: new Date().toISOString(), aio: false, expanded: !!btn, extra_wait_ms: waited };
  if (c && c.innerText.length >= 150) {
    let t = c.innerText;
    for (const cut of ['Відповіді ШІ можуть', 'AI responses may', 'Показати всі', 'Show all']) {
      const j = t.indexOf(cut);
      if (j > 0) t = t.slice(0, j);
    }
    rec.aio = true;
    rec.text = t.replace(/\s+/g, ' ');
    const labels = [...c.querySelectorAll('a[aria-label]')].map(a => a.getAttribute('aria-label')).filter(x => x && x.length > 5);
    rec.sources = [...new Set(labels.filter(x => / [–-] "/.test(x)))];
    rec.sources_all = [...new Set(labels)].slice(0, 25);
  } else {
    rec.unavailable = /недоступний для цього|not available for this/.test(b);
    rec.generating = /подумати трохи довше|Триває обробка|Generating|think a bit longer/.test(b);
    rec.text = c ? c.innerText.slice(0, 80) : '';
  }
  const R = JSON.parse(localStorage.aio_records);
  R.push(rec);
  localStorage.aio_records = JSON.stringify(R);
  localStorage.aio_idx = String(i + 1);
  return id + ' ' + lang + ' ' + (rec.aio ? rec.text.length + ' chars' : 'no-aio');
}
