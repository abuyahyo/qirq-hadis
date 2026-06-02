/**
 * «Қирқ ҳадис» қидирув тизими — Playwright (браузер) тести.
 * Ишга тушириш:
 *   NODE_PATH=/opt/node22/lib/node_modules node tests/search.spec.js
 *
 * Ҳар бир талаб учун ҳолат: кўп ёзувли мослик, сўз чегараси, highlight
 * тўғрилиги (позиция-харита), парча (snippet), арабча fuzzy, HTML-инъекция
 * йўқлиги, "натижа йўқ" ва бўш сўров.
 */
const { chromium } = require('playwright');
const { pathToFileURL } = require('url');
const path = require('path');

const URL = pathToFileURL(path.resolve(__dirname, '..', 'index.html')).href;
let pass = 0, fail = 0;
function ok(name, cond) {
  if (cond) { pass++; console.log('  ✓', name); }
  else { fail++; console.log('  ✗ FAIL:', name); }
}

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.goto(URL);
  await page.waitForSelector('#searchInput');

  const search = (q) => page.evaluate((q) => { App.doSearch(q); }, q);

  async function results() {
    return await page.evaluate(() => {
      const LETTER = /[A-Za-zЀ-ӿء-ي]/;
      const items = [...document.querySelectorAll('#hadisGrid .result-item')];
      return items.map(it => {
        const id = parseInt((it.querySelector('.result-label')?.textContent || '').match(/^(\d+)/)?.[1] || '0', 10);
        const marks = [...it.querySelectorAll('mark')].map(mk => {
          let prevChar = '';
          const ps = mk.previousSibling;
          if (ps && ps.nodeType === 3 && ps.textContent.length) prevChar = ps.textContent.slice(-1);
          return { text: mk.textContent, prevChar, boundary: prevChar === '' || prevChar === '…' || !LETTER.test(prevChar) };
        });
        return { id, html: it.innerHTML, text: it.textContent, marks };
      });
    });
  }

  try {
    // 1) КЎП ЁЗУВЛИ: кирилл сўров
    await search('ният'); // ният
    let r = await results();
    ok('кирилл "ният" натижа беради', r.length > 0);
    ok('кирилл "ният" highlight бор', r.some(x => x.marks.length > 0));
    const cyrIds = r.map(x => x.id).sort((a, b) => a - b);

    // 2) КЎП ЁЗУВЛИ: лотинча — бир хил натижа
    await search('niyat');
    r = await results();
    const latIds = r.map(x => x.id).sort((a, b) => a - b);
    ok('лотин "niyat" = кирилл "ният" (кросс-ёзув)', JSON.stringify(cyrIds) === JSON.stringify(latIds) && latIds.length > 0);

    // 3) HIGHLIGHT АСЛ МАТНГА: лотин сўров → кирилл асл <mark>
    await search('amallar');
    r = await results();
    const h1 = r.find(x => x.id === 1);
    ok('лотин "amallar" → 1-ҳадис', !!h1);
    ok('highlight асл кириллда (Амаллар)', !!h1 && h1.marks.some(m => /Амаллар/i.test(m.text)));

    // 4) СЎЗ ЧЕГАРАСИ: барча mark'лар сўз бошида
    await search('ҳаққ'); // ҳаққ
    r = await results();
    ok('"ҳаққ" — барча mark сўз бошида', r.length > 0 && r.every(x => x.marks.every(m => m.boundary)));

    // 4b) СЎЗ ЎРТАСИ мос келмайди: "маллар" (Амаллар ичида) 1-ҳадисни сўз ўртасидан ажратмайди
    await search('маллар'); // маллар
    r = await results();
    const h1b = r.find(x => x.id === 1);
    ok('"маллар" сўз ўртасини ажратмайди', !h1b || h1b.marks.every(m => m.boundary));

    // 5) ПАРЧА (snippet): кеч келадиган сўз atrofidan, … билан
    await search('ҳижрат'); // ҳижрат
    r = await results();
    const sn = r.find(x => x.id === 1);
    ok('"ҳижрат" 1-ҳадисда топилади', !!sn && sn.marks.length > 0);
    ok('узун матнда … парча белгиси бор', !!sn && sn.text.includes('…'));

    // 6) АРАБЧА fuzzy (ҳаракатсиз + артикл ихтиёрий)
    await search('اعمال'); // اعمال
    r = await results();
    ok('арабча "اعمال" → натижа (диакритикасиз)', r.length > 0 && r.some(x => x.marks.length > 0));
    ok('арабча натижада rtl span', r.some(x => /dir="rtl"/.test(x.html)));

    // 7) HTML-ИНЪЕКЦИЯ йўқ
    await search('<img src=x onerror=alert(1)>');
    const injected = await page.evaluate(() => !!document.querySelector('#hadisGrid img'));
    ok('HTML-инъекция бажарилмайди', injected === false);

    // 8) НАТИЖА ЙЎҚ
    await search('zzqxqzzнотопиладиган');
    const noRes = await page.evaluate(() => !!document.querySelector('#hadisGrid .no-results'));
    ok('йўқ сўров → "натижа топилмади"', noRes === true);

    // 9) БЎШ СЎРОВ → бутун рўйхат (42)
    await search('');
    const cnt = await page.evaluate(() => document.querySelectorAll('#hadisGrid .hadis-card').length);
    ok('бўш сўров → 42 карта', cnt === 42);

  } catch (e) {
    fail++;
    console.log('  ✗ EXCEPTION:', e.message);
  } finally {
    await browser.close();
  }

  console.log(`\nPASS: ${pass}  FAIL: ${fail}`);
  process.exit(fail ? 1 : 0);
})();
