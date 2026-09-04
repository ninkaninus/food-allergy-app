/*
 * DOM-stub, så app/static/index.html's modul kan KØRE i node.
 *
 * Hvorfor: tests/test_frontend.py og test_offentlig_flade.py siger det selv
 * — de er statisk kontrol af kildeteksten og beviser ikke, at browseren
 * opfører sig rigtigt. En vagt, der står det forkerte sted i en betinget
 * kæde, består en substring-test og fejler i Netto. Vagterne omkring
 * "hvad skal appen tjekke for" afgør, om en dagplejer får et svar, der er
 * regnet ud fra det rigtige allergensæt, så de skal efterprøves på ADFÆRD.
 *
 * Ingen afhængigheder: der er hverken node_modules eller jsdom i repoet,
 * og det skal blive ved med at være sådan (se CLAUDE.md om frontend uden
 * byggetrin). Stubben er derfor kun det, modulet faktisk rører.
 *
 * Hvad den IKKE kan: layout, CSS, rigtig hændelsesudbredelse og alt, der
 * kræver en browser. Påstandene skal derfor handle om, hvilke URL'er der
 * blev kaldt, med hvilket allergensæt, og hvad der står i en node —
 * ikke om hvordan noget ser ud.
 *
 * Kaldes af tests/test_frontend_adfaerd.py:
 *     node frontend_stub.mjs file:///sti/til/modul.mjs <scene>
 * Skriver ét JSON-objekt til stdout og exit 0, når alle påstande holder.
 */
const [, , MODUL, SCENE] = process.argv;

/* ---------- den mindste DOM, modulet kan leve i ---------- */
const noder = new Map();
const attrRe = /<button\b([^>]*)>/g;

function attrs(tag){
  const ud = {};
  for(const m of tag.matchAll(/([a-zA-Z-]+)="([^"]*)"/g)) ud[m[1]] = m[2];
  return ud;
}
function datasaet(a){
  const d = {};
  for(const [k, v] of Object.entries(a))
    if(k.startsWith('data-'))
      d[k.slice(5).replace(/-([a-z])/g, (_, c) => c.toUpperCase())] = v;
  return d;
}
function passer(sel, a){
  if(sel === '.chip') return (a.class || '').split(/\s+/).includes('chip');
  const m = sel.match(/\[([a-zA-Z-]+)\]/);
  if(m) return m[1] in a;
  return false;
}

function nyNode(sel){
  // innerHTML er en accessor, ikke et felt: sættes den, er de "børn", en
  // tidligere querySelectorAll gav, forældede. Uden det ville
  // paintPrefChips() hænge sine onclick på nogle objekter, og testen
  // læse nogle andre — og en vagt, der aldrig blev kaldt, ville se ud
  // som en vagt, der virkede.
  let html = '', boern = {};
  const n = {
    _sel: sel, textContent: '', value: '', hidden: false,
    get innerHTML(){ return html; },
    set innerHTML(v){ html = String(v); boern = {}; },
    disabled: false, checked: false, dataset: {}, style: {},
    classList: {add(){}, remove(){}, toggle(){}, contains(){ return false; }},
    scrollIntoView(){}, focus(){}, blur(){},
    click(){ this.onclick && this.onclick(); },
    setAttribute(k, v){ this['attr:' + k] = v; },
    getAttribute(k){ return this['attr:' + k]; },
    addEventListener(t, f){ (this._lyt ||= {})[t] = f; },
    removeEventListener(){},
    insertAdjacentHTML(hvor, h){ this.innerHTML = this.innerHTML + h; },
    appendChild(){}, remove(){},
    getContext(){ return {drawImage(){}, getImageData: () => ({}) }; },
    querySelector(){ return null; },
    querySelectorAll(sel2){
      if(boern[sel2]) return boern[sel2];
      const ud = boern[sel2] = [];
      for(const m of String(this.innerHTML).matchAll(attrRe)){
        const a = attrs(m[1]);
        if(!passer(sel2, a)) continue;
        const k = nyNode(sel2 + '#' + ud.length);
        k.dataset = datasaet(a);
        ud.push(k);
      }
      return ud;
    },
  };
  return n;
}
function node(sel){
  if(!noder.has(sel)) noder.set(sel, nyNode(sel));
  return noder.get(sel);
}
const faner = ['scan', 'filter', 'prefs'].map(v => {
  const n = nyNode('fane-' + v);
  n.dataset.view = v;
  return n;
});
globalThis.document = {
  visibilityState: 'hidden',       // kameraet skal ikke starte i en test
  querySelector(sel){
    const m = sel.match(/nav\.tabs button\[data-view="(\w+)"\]/);
    if(m) return faner.find(f => f.dataset.view === m[1]);
    return node(sel);
  },
  querySelectorAll(sel){
    if(sel === 'nav.tabs button') return faner;
    return node(sel).querySelectorAll(sel);
  },
  createElement(t){ return nyNode('<' + t + '>'); },
  addEventListener(){},
};

// Markuppen har `hidden` på de to visninger, der ikke er scan-skærmen.
// Uden det ville stubben påstå, at listen står åben i hver eneste scene.
node('#view-filter').hidden = true;
node('#view-prefs').hidden = true;

const lager = new Map();
globalThis.localStorage = {
  getItem: k => (lager.has(k) ? lager.get(k) : null),
  setItem: (k, v) => lager.set(k, String(v)),
  removeItem: k => lager.delete(k),
};
globalThis.window = globalThis;
globalThis.BarcodeDetector = class { async detect(){ return []; } };
globalThis.scrollTo = () => {};
globalThis.requestAnimationFrame = f => setTimeout(f, 0);
const HANDLINGER = [];
Object.defineProperty(globalThis, 'location', {
  configurable: true, value: {reload(){ HANDLINGER.push('reload'); }},
});
Object.defineProperty(globalThis, 'navigator', {
  configurable: true, value: {vibrate(){}},   // ingen permissions -> ingen autostart
});

/* ---------- serveren, som testen vil have den ---------- */
const ALLE = [
  ['gluten', 'Gluten', true], ['skaldyr', 'Krebsdyr', true], ['aeg', 'Æg', true],
  ['fisk', 'Fisk', true], ['jordnoed', 'Jordnødder', true], ['soja', 'Soja', true],
  ['maelkeprotein', 'Mælk', true], ['noedder', 'Nødder', true], ['selleri', 'Selleri', true],
  ['sennep', 'Sennep', true], ['sesam', 'Sesam', true], ['sulfit', 'Sulfit', true],
  ['lupin', 'Lupin', true], ['bloeddyr', 'Bløddyr', true],
  ['jordbaer', 'Jordbær', false], ['banan', 'Banan', false], ['tomat', 'Tomat', false],
].map(([slug, name, eu14]) => ({slug, name, eu14}));

const cfg = {
  allergensOk: true,
  me: {authenticated: false},
  meForsinkelse: 0,
  profilerStatus: 200,
  profiler: [{id: 1, allergens: ALLE.map(a => ({slug: a.slug, active: false}))}],
};
const KALD = [];
const svar = (krop, ok = true, status = 200) => ({
  ok, status,
  json: async () => krop,
  text: async () => JSON.stringify(krop),
});
const vent = ms => new Promise(r => setTimeout(r, ms));

globalThis.fetch = async (url, opt) => {
  KALD.push(String(url));
  const u = String(url);
  if(u === '/api/allergens')
    return cfg.allergensOk ? svar(ALLE) : svar({detail: 'nej'}, false, 500);
  if(u === '/api/auth/me'){
    if(cfg.meForsinkelse) await vent(cfg.meForsinkelse);
    return svar(cfg.me);
  }
  if(u === '/api/profiles')
    return svar(cfg.profiler, cfg.profilerStatus === 200, cfg.profilerStatus);
  if(u.startsWith('/api/profiles/')) return svar({ok: true});
  if(u === '/api/version') return svar({version: '0.24.0'});
  if(u === '/api/attribution') return svar({data_sources: [{records: 20}]});
  if(u === '/api/auth/logout') return svar({ok: true});
  if(u === '/api/auth/users') return svar([]);
  if(u.startsWith('/api/scan/')) return svar({
    ean: u.split('/')[3].split('?')[0], found: true, result: 'safe', gemt: true,
    product: {name: 'Prøve-Rugbrød', brand: 'Testbageren', ingredients_parsed: 'Rugmel, vand, salt'},
    allergens: [{slug: 'maelkeprotein', name: 'Mælk', state: 'free', basis: 'manual', eu14: true}],
    fotos: {},
  });
  if(u.startsWith('/api/soeg')) return svar({
    antal: 0, vist: 0, varer: [],
    facetter: {status: {alle: 0}},
  });
  return svar({});
};

/* ---------- scenerne ---------- */
const $ = s => node(s);
const paastande = [];
function tjek(navn, betingelse, detalje){
  paastande.push({navn, ok: !!betingelse, detalje: detalje === undefined ? '' : String(detalje)});
}
const scanKald = () => KALD.filter(u => u.startsWith('/api/scan/'));

const SCENER = {
  // B1: en grøn flade må ikke overleve det sæt, den blev regnet ud fra
  async b1_logud(){
    cfg.me = {authenticated: true, name: 'Forælder', role: 'admin'};
    cfg.profiler = [{id: 1, allergens: [{slug: 'maelkeprotein', active: true}, {slug: 'aeg', active: true}]}];
    const t = await start();
    await t.lookup('5701234567890');
    tjek('dommen vises efter opslag', $('#verdict').hidden === false);
    // hun logger ud: SERVER_ALLERGENS ryddes, sættet bliver tomt
    cfg.me = {authenticated: false};
    await t.refreshAuth();
    tjek('sættet er tomt efter logout', t.effektivAllergener().length === 0);
    tjek('spørgsmålet vises', $('#vaelgPanel').hidden === false);
    tjek('den grønne flade er væk', $('#verdict').hidden === true);
    tjek('bekræftelsespanelet er væk', $('#confirmPanel').hidden === true);
  },

  // B1: samme, men sættet ændres uden at blive tomt
  async b1_chip(){
    lager.set('allergiscan.prefs.v2', JSON.stringify({allergens: ['maelkeprotein', 'aeg']}));
    const t = await start();
    await t.lookup('5701234567890');
    tjek('dommen vises efter opslag', $('#verdict').hidden === false);
    const chips = $('#prefChips').querySelectorAll('.chip');
    const gluten = chips.find(c => c.dataset.slug === 'gluten');
    await gluten.onclick();
    tjek('sættet blev bredere', t.effektivAllergener().length === 3);
    tjek('spørgsmålet vises ikke', $('#vaelgPanel').hidden === true);
    tjek('den forrige dom er væk', $('#verdict').hidden === true, $('#verdict').hidden);
  },

  // B2: den gamle nøgle må ikke smugle appens eget gæt med over
  async b2_gammel_noegle(){
    lager.set('allergiscan.prefs.v1', JSON.stringify({allergens: ALLE.map(a => a.slug), name: 'Barn'}));
    const t = await start();
    tjek('sættet er tomt', t.effektivAllergener().length === 0, JSON.stringify(t.effektivAllergener()));
    tjek('spørgsmålet vises', $('#vaelgPanel').hidden === false);
    await t.lookup('5701234567890');
    tjek('ingen vare blev slået op', scanKald().length === 0, KALD.join(' '));
    tjek('vagtens besked står', $('#scanHint').textContent === t.VAELG_FOERST, $('#scanHint').textContent);
  },

  // B3: beskeden må ikke blive stående, efter den er blevet usand
  async b3_besked_tages_ned(){
    const t = await start();
    await t.lookup('5701234567890');
    tjek('vagtens besked står', $('#scanHint').textContent === t.VAELG_FOERST);
    tjek('stregkoden blev stående', $('#ean').value === '5701234567890');
    const chips = $('#prefChips').querySelectorAll('.chip');
    await chips.find(c => c.dataset.slug === 'maelkeprotein').onclick();
    tjek('beskeden er afløst', $('#scanHint').textContent === t.KLAR_TIL_OPSLAG, $('#scanHint').textContent);
    tjek('spørgsmålet er væk', $('#vaelgPanel').hidden === true);
  },

  // B4: en scanning i AUTH-vinduet må ikke besvares på et gæt
  async b4_porten(){
    cfg.me = {authenticated: true, name: 'Forælder', role: 'admin'};
    cfg.meForsinkelse = 30;
    cfg.profiler = [{id: 1, allergens: [{slug: 'maelkeprotein', active: true}, {slug: 'aeg', active: true}]}];
    const import_ = import(MODUL);      // IIFE'en er nu i gang
    await import_;
    const t = globalThis.__t;
    tjek('auth er endnu ikke afklaret', t.AUTH_AFKLARET === false);
    const opslag = t.lookup('5701234567890');    // kameraet fandt en kode FØR svaret
    tjek('intet opslag endnu', scanKald().length === 0);
    await opslag;
    tjek('varen blev slået op', scanKald().length === 1, KALD.join(' '));
    tjek('med familiens sæt', /allergens=maelkeprotein%2Caeg/.test(scanKald()[0] || ''), scanKald()[0]);
    tjek('ikke kasseret med vagtens besked', $('#scanHint').textContent !== t.VAELG_FOERST);
  },

  // Listen viser også domme, og den males kun, når fanen åbnes
  async liste_naar_sessionen_udloeber(){
    cfg.me = {authenticated: true, name: 'Forælder', role: 'admin'};
    cfg.profiler = [{id: 1, allergens: [{slug: 'maelkeprotein', active: true}]}];
    const t = await start();
    $('#view-filter').hidden = false;      // hun står i listen
    await t.soeg();
    tjek('listen blev hentet', KALD.some(u => u.startsWith('/api/soeg')));
    cfg.me = {authenticated: false};       // sessionen udløber
    await t.refreshAuth();
    tjek('listen spørger nu i stedet', /id="sVaelg"/.test($('#sHits').innerHTML),
         $('#sHits').innerHTML.slice(0, 120));
  },

  // Bidragyderen får at vide, hvem der kan åbne døren — og en rigtig knap
  async soeg_bidragyder(){
    cfg.me = {authenticated: true, name: 'Dagplejer', role: 'contributor'};
    cfg.profiler = [{id: 1, allergens: ALLE.map(a => ({slug: a.slug, active: false}))}];
    const t = await start();
    await t.soeg();
    const h = $('#sHits').innerHTML;
    tjek('familien navngives', /familien/.test(h), h);
    tjek('knappen er .btn', /class="btn"/.test(h), h);
    tjek('knappen lover ikke et valg', /Se indstillinger/.test(h), h);
    tjek('FRI FOR-boksen er skjult', $('#sFriBox').hidden === true);
    tjek('ingen søgning blev sendt', KALD.filter(u => u.startsWith('/api/soeg')).length === 0);
    tjek('overskriften er spørgsmålet', $('#sCount').textContent === t.SPOERGSMAALET);
  },

  // /api/allergens fejler: appen må hverken låse eller love et valg
  async ingen_allergenliste(){
    cfg.allergensOk = false;
    const t = await start();
    tjek('porten åbnede alligevel', t.AUTH_AFKLARET === true);
    tjek('spørgsmålet vises', $('#vaelgPanel').hidden === false);
    tjek('knappen siger genindlæs', $('#vaelgGo').textContent === 'Genindlæs siden', $('#vaelgGo').textContent);
    $('#vaelgGo').click();
    tjek('og gør det', HANDLINGER.includes('reload'), HANDLINGER.join(','));
    await t.lookup('5701234567890');     // må ikke hænge for evigt
    tjek('ingen vare blev slået op', scanKald().length === 0);
  },

  // 401 fra /api/profiles er ikke "ingen allergener slået til"
  async profiler_401(){
    cfg.me = {authenticated: true, name: 'Forælder', role: 'admin'};
    cfg.profilerStatus = 401;
    const t = await start();
    tjek('sættet er ukendt, ikke tomt', t.SERVER_ALLERGENS === null, JSON.stringify(t.SERVER_ALLERGENS));
    tjek('teksten peger på serveren', /serveren/.test($('#vaelgTekst').textContent), $('#vaelgTekst').textContent);
    tjek('knappen siger genindlæs', $('#vaelgGo').textContent === 'Genindlæs siden');
  },

  // headeren skal skrive dansk og aldrig en rå slug
  async headeren(){
    lager.set('allergiscan.prefs.v2', JSON.stringify({allergens: ['maelkeprotein', 'aeg']}));
    const t = await start();
    tjek('navne, ikke slugs', $('#whoLinje').innerHTML === 'Tjekker for <b id="who">Mælk, Æg</b>',
         $('#whoLinje').innerHTML);
    t.prefs.allergens = [];
    t.paintWho();
    tjek('tomt sæt er en hel sætning', $('#whoLinje').innerHTML === '<b id="who">Intet valgt endnu</b>',
         $('#whoLinje').innerHTML);
  },
};

async function start(){
  await import(MODUL);
  await vent(5);            // opstartens tre kald
  return globalThis.__t;
}

const scene = SCENER[SCENE];
if(!scene){ console.log(JSON.stringify({fejl: 'ukendt scene: ' + SCENE})); process.exit(2); }
try {
  await scene();
} catch (e) {
  console.log(JSON.stringify({fejl: String(e && e.stack || e)}));
  process.exit(3);
}
console.log(JSON.stringify({paastande}));
process.exit(paastande.every(p => p.ok) ? 0 : 1);
