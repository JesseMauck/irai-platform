/* ValueBot front end — dependency-free single-page app with hash routing. */
const $app = document.getElementById("app");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function api(path, opts = {}) {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  if (!res.ok) {
    let msg = res.statusText;
    try { msg = (await res.json()).detail || msg; } catch {}
    throw new Error(msg);
  }
  return res.json();
}

// ---------- formatting
const pct = (v, d = 1) => (v == null || isNaN(v) ? "—" : (v * 100).toFixed(d) + "%");
const num = (v, d = 2) => (v == null || isNaN(v) ? "—" : Number(v).toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d }));
const mil = (v) => (v == null ? "—" : num(v / 1e6, 0));
function fmtUnit(v, unit) {
  if (unit === "pct") return pct(v);
  if (unit === "x") return num(v, 2) + "x";
  if (unit === "money") return mil(v);
  if (unit === "years") return num(v, 0);
  return num(v);
}
const signed = (v) => (v == null ? "—" : `<span class="${v >= 0 ? "pos" : "neg"}">${v >= 0 ? "+" : ""}${pct(v)}</span>`);

// ---------- tiny markdown (paragraphs, lists, bold, italic, links)
function inline(s) {
  return esc(s)
    .replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
    .replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>")
    .replace(/(^|[^*])\*([^*]+)\*/g, "$1<i>$2</i>");
}
function md(text) {
  const blocks = String(text || "").trim().split(/\n\s*\n/);
  return blocks.map((b) => {
    const lines = b.split("\n");
    if (lines.every((l) => /^\s*[-*]\s+/.test(l))) return "<ul>" + lines.map((l) => `<li>${inline(l.replace(/^\s*[-*]\s+/, ""))}</li>`).join("") + "</ul>";
    if (lines.every((l) => /^\s*\d+\.\s+/.test(l))) return "<ol>" + lines.map((l) => `<li>${inline(l.replace(/^\s*\d+\.\s+/, ""))}</li>`).join("") + "</ol>";
    if (/^#{1,4}\s/.test(b)) return `<h4>${inline(b.replace(/^#+\s/, ""))}</h4>`;
    return `<p>${lines.map(inline).join("<br>")}</p>`;
  }).join("");
}

// ---------- router
let pollTimer = null;
async function route() {
  clearTimeout(pollTimer);
  const [, page, arg] = location.hash.split("/");
  window.scrollTo(0, 0);
  try {
    if (page === "new") return renderWizard(arg);
    if (page === "job") return renderJob(arg);
    if (page === "share") return renderShare(arg);
    if (page === "runs") return renderRuns();
    return renderHome();
  } catch (e) {
    $app.innerHTML = `<div class="card"><h2>Something went wrong</h2><p>${esc(e.message)}</p></div>`;
  }
}
window.addEventListener("hashchange", route);

// ---------- home
async function renderHome() {
  const health = await api("/api/health").catch(() => ({}));
  $app.innerHTML = `
  <section class="hero">
    <div>
      <span class="tag">Narrative + numbers</span>
      <h1>Put your investment thesis to the test.</h1>
      <p class="lede">Pick a public company, state your story, and get a full valuation report plus an editable Excel model with live formulas, built the way a valuation professor would.</p>
      <div class="row" style="margin-top:22px">
        <a class="btn" href="#/new">Start a valuation</a>
        <a class="btn btn-ghost" href="#/new/DEMO">Try the demo company</a>
      </div>
      ${health.llm ? "" : `<p class="small muted" style="margin-top:14px">Running without an AI key: theses and reports use templates, and only demo tickers work offline.</p>`}
    </div>
    <div class="steps-ill">
      <div><b>1</b>Pick a company by ticker or name</div>
      <div><b>2</b>Write a thesis, or have the AI draft a bull, bear or neutral one</div>
      <div><b>3</b>The bot pulls filings and market data, picks a framework, and turns the story into numbers</div>
      <div><b>4</b>Review the report, flex the drivers, download the Excel model, share a view-only link</div>
    </div>
  </section>
  <section class="grid3">
    <div class="card"><h3>A report you can argue with</h3><p class="muted">Every assumption comes with a reason, sources are linked, and the report says what would change the conclusion.</p></div>
    <div class="card"><h3>A model you can edit</h3><p class="muted">Blue input cells drive live formulas all the way to value per share. Bull and bear scenario workbooks included.</p></div>
    <div class="card"><h3>The right framework</h3><p class="muted">FCFF DCF for operating businesses, excess-return models for banks, dividend discount for mature payers, chosen automatically.</p></div>
  </section>
  <section style="margin-top:34px" id="recent"></section>`;
  const runs = await api("/api/jobs").catch(() => []);
  if (runs.length) document.getElementById("recent").innerHTML = `<h2>Recent valuations</h2>${runsList(runs.slice(0, 5))}`;
}

function runsList(runs) {
  return `<div class="runs">${runs.map((r) => `
    <a href="#/job/${r.id}"><span><b>${esc(r.ticker)}</b> <span class="muted">${esc(r.summary?.name || "")}</span></span>
    <span>${r.summary ? `${num(r.summary.value_per_share)} vs ${num(r.summary.price)} ${signed(r.summary.upside)}` : esc(r.status)}</span></a>`).join("")}</div>`;
}

async function renderRuns() {
  const runs = await api("/api/jobs");
  $app.innerHTML = `<h1>My valuations</h1>${runs.length ? runsList(runs) : `<p class="muted">None yet. <a href="#/new">Start one</a>.</p>`}`;
}

// ---------- new valuation wizard
const STORY_FIELDS = [
  ["growth", "Growth story", "How big can revenues get? Size of the market, its growth, and the share this company can win."],
  ["profitability", "Profitability story", "Unit economics and economies of scale: where do operating margins settle?"],
  ["efficiency", "Growth efficiency story", "How much must it reinvest (capex, R&D, acquisitions) to deliver that growth?"],
  ["risk", "Risk story", "Operating risk, leverage, where it operates, and the chance the business fails."],
  ["moat", "Competitive advantages", "How long can it earn more than its cost of capital?"],
];
const DEFAULT_Q = [
  "How big can revenues get (market size × market share), and how quickly?",
  "How profitable will the business be at scale, given its unit economics?",
  "How much must it reinvest to grow, and does that reinvestment earn more than the cost of capital?",
];
const blankW = () => ({
  step: 1, ticker: "", company: null, thesis: "", questions: [...DEFAULT_Q, ""], method: "auto", email: "",
  stories: Object.fromEntries(STORY_FIELDS.map(([k]) => [k, ""])),
  market: { tam: "", tam_growth: "", target_share: "" }, overrides: {},
  adjustments: { capitalize_rnd: "auto", rnd_life: "", lease_adjust: true, one_time_addback: "", normalize_margins: false },
  risk: { regions: [{ region: "", weight: "", crp: "" }], segments: [{ name: "", weight: "", unlevered_beta: "" }], inflation: "", riskfree_override: "" },
  extras: { nol: "", options_count: "", options_strike: "", options_maturity: "", volatility: "", non_operating_assets: "" },
  open: [true, false, false, false, false],
});
let W = blankW();
const STEPS = ["Select company", "Tell the story", "Refine inputs", "Review & run"];

function renderWizard(preset) {
  if (preset && preset !== W.ticker) { W = { ...blankW(), ticker: preset.toUpperCase() }; loadCompany(W.ticker); }
  const nav = STEPS.map((s, i) => `<span class="${W.step >= i + 1 ? "on" : ""}">${i + 1}. ${s}</span>`).join("");
  $app.innerHTML = `<h2>New valuation</h2><div class="wizard-nav">${nav}</div><div class="card" id="wz"></div>`;
  [stepCompany, stepStory, stepRefine, stepReview][W.step - 1]();
}

function stepCompany() {
  const el = document.getElementById("wz");
  el.innerHTML = `
    <label for="q">Company ticker or name</label>
    <div class="search-wrap"><input id="q" placeholder="e.g. AAPL, Microsoft, or DEMO" value="${esc(W.ticker)}" autocomplete="off"><div class="suggest" id="sg" hidden></div></div>
    <div class="preview" id="pv">${companyPreview()}</div>
    <div class="actions"><span></span><button class="btn" id="next" ${W.company ? "" : "disabled"}>Continue</button></div>`;
  const q = document.getElementById("q"), sg = document.getElementById("sg");
  let t;
  q.addEventListener("input", () => {
    clearTimeout(t);
    t = setTimeout(async () => {
      if (!q.value.trim()) return (sg.hidden = true);
      const hits = await api("/api/search?q=" + encodeURIComponent(q.value)).catch(() => []);
      sg.innerHTML = hits.map((h) => `<div data-t="${esc(h.ticker)}"><b>${esc(h.ticker)}</b> · ${esc(h.name)}</div>`).join("") || `<div class="muted">No matches. Press Enter to try “${esc(q.value.toUpperCase())}”.</div>`;
      sg.hidden = false;
    }, 220);
  });
  q.addEventListener("keydown", (e) => { if (e.key === "Enter") { sg.hidden = true; loadCompany(q.value.trim().toUpperCase()); } });
  sg.addEventListener("click", (e) => { const d = e.target.closest("[data-t]"); if (d) { sg.hidden = true; q.value = d.dataset.t; loadCompany(d.dataset.t); } });
  document.getElementById("next").onclick = () => { W.step = 2; renderWizard(); };
}

function companyPreview() {
  if (W.loading) return `<p class="muted">Loading ${esc(W.ticker)}…</p>`;
  if (W.error) return `<div class="warn">${esc(W.error)}</div>`;
  const c = W.company;
  if (!c) return "";
  const L = c.latest;
  return `<div class="card" style="background:#fcfbf8">
    <div class="row"><h3 style="margin:0">${esc(c.name)}</h3>${c.demo ? '<span class="tag demo">Demo data</span>' : ""}</div>
    <dl class="kv" style="margin-top:12px">
      <dt>Price</dt><dd>${num(c.price)} ${esc(c.currency)} · market cap ${mil(c.market_cap)}m</dd>
      <dt>Sector / industry</dt><dd>${esc(c.sector || "—")} / ${esc(c.industry || "—")}</dd>
      <dt>FY${L.fiscal_year}: growth</dt><dd>Revenue ${mil(L.revenue)}m, growing ${pct(L.revenue_growth)}</dd>
      <dt>Profitability</dt><dd>Gross margin ${pct(L.gross_margin)} · operating margin ${pct(L.operating_margin)}</dd>
      <dt>Growth efficiency</dt><dd>Sales / invested capital ${L.sales_to_capital ? num(L.sales_to_capital) + "x" : "—"} · ROIC ${pct(L.roic)}</dd>
      <dt>Suggested method</dt><dd>${esc(c.suggested_method)} — <span class="muted">${esc(c.method_reason)}</span></dd>
    </dl></div>`;
}

async function loadCompany(t) {
  Object.assign(W, { ticker: t, company: null, error: null, loading: true });
  if (W.step === 1 && document.getElementById("pv")) document.getElementById("pv").innerHTML = companyPreview();
  try { W.company = await api("/api/company/" + encodeURIComponent(t)); }
  catch (e) { W.error = `${t}: ${e.message}`; }
  W.loading = false;
  if (W.step === 1 && document.getElementById("wz")) stepCompany();
}

function stepStory() {
  const el = document.getElementById("wz");
  el.innerHTML = `
    <div class="row" style="justify-content:space-between"><h3 style="margin:0">${esc(W.company.name)}</h3>
      <div class="row"><span class="small muted">Draft with AI:</span>
        ${["bullish", "neutral", "bearish"].map((s) => `<button class="btn btn-ghost btn-small" data-stance="${s}">${s}</button>`).join("")}</div></div>
    <p class="small muted">Every number in the valuation should come from a piece of the story. Keep it simple and focused, and fill in as much or as little as you like.</p>
    <label for="th">Your thesis in a few sentences</label>
    <textarea id="th" style="min-height:90px" placeholder="What do you believe about this company that the market may be missing?">${esc(W.thesis)}</textarea>
    <div class="story-grid">${STORY_FIELDS.map(([k, t, hint]) => `
      <div><label for="st-${k}">${t}</label><textarea id="st-${k}" data-story="${k}" style="min-height:70px" placeholder="${esc(hint)}">${esc(W.stories[k])}</textarea></div>`).join("")}</div>
    <label>Framing questions the valuation should answer</label>
    ${W.questions.map((q, i) => `<input class="fq" data-i="${i}" style="margin-bottom:8px" value="${esc(q)}" placeholder="Add a question">`).join("")}
    <label for="m">Valuation method</label>
    <select id="m">
      <option value="auto">Auto (recommended: ${esc(W.company.suggested_method)})</option>
      <option value="fcff">FCFF discounted cash flow</option>
      <option value="excess_return">Excess return model (banks, insurers)</option>
      <option value="ddm">Dividend discount model</option>
    </select>
    <div class="actions"><button class="btn btn-ghost" id="back">Back</button><button class="btn" id="next">Continue</button></div>`;
  document.getElementById("m").value = W.method;
  const save = () => {
    W.thesis = document.getElementById("th").value;
    document.querySelectorAll("[data-story]").forEach((x) => (W.stories[x.dataset.story] = x.value));
    W.questions = [...document.querySelectorAll(".fq")].map((x) => x.value);
    W.method = document.getElementById("m").value;
  };
  el.querySelectorAll("[data-stance]").forEach((b) => (b.onclick = async () => {
    save();
    b.disabled = true; b.textContent = "drafting…";
    try {
      const d = await api("/api/thesis", { method: "POST", body: JSON.stringify({ ticker: W.ticker, stance: b.dataset.stance }) });
      W.thesis = d.thesis;
      if (d.stories) Object.assign(W.stories, d.stories);
      if (d.questions?.length) W.questions = [...d.questions, ""].slice(0, 6);
    } catch (e) { alert(e.message); }
    stepStory();
  }));
  document.getElementById("back").onclick = () => { save(); W.step = 1; renderWizard(); };
  document.getElementById("next").onclick = () => { save(); W.step = 3; renderWizard(); };
}

// percent fields are typed as % and sent as decimals
const PCT = new Set(["tam_growth", "target_share", "inflation", "riskfree_override", "volatility", "crp"]);
const fld = (group, key, label, hint, unit = "") => `
  <div><label for="f-${group}-${key}">${label}</label>
  <div class="unit-in"><input id="f-${group}-${key}" data-g="${group}" data-k="${key}" value="${esc(W[group][key])}" placeholder="${esc(hint)}" inputmode="decimal">${unit ? `<span>${unit}</span>` : ""}</div></div>`;

function stepRefine() {
  const el = document.getElementById("wz");
  const c = W.company, drivers = c.drivers[W.method === "auto" ? c.suggested_method : W.method];
  el.innerHTML = `
    <p class="muted">All optional. Anything you leave blank is estimated from filings, market data and the story. Numbers you enter here are locked: the AI explains them but will not change them.</p>
    <details data-sec="0" ${W.open[0] ? "open" : ""}><summary>Market size (anchors the growth story)</summary>
      <div class="fgrid">
        ${fld("market", "tam", "Total market today", "e.g. 60000", "m " + esc(c.currency))}
        ${fld("market", "tam_growth", "Market growth per year", "e.g. 8", "%")}
        ${fld("market", "target_share", "Market share in year 10", "e.g. 15", "%")}
      </div>
      <p class="small muted">If you give the market and a share, revenue growth is solved so year-10 revenue = market × share. The bot also checks that revenue never exceeds the market.</p>
    </details>
    <details data-sec="1" ${W.open[1] ? "open" : ""}><summary>Your numbers (lock any driver)</summary>
      <div class="fgrid">${drivers.map((d) => `
        <div><label for="ov-${d.key}">${esc(d.label)}</label><div class="unit-in"><input id="ov-${d.key}" data-ov="${d.key}" data-u="${d.unit}" inputmode="decimal"
          value="${W.overrides[d.key] == null ? "" : d.unit === "pct" ? +(W.overrides[d.key] * 100).toFixed(4) : W.overrides[d.key]}" placeholder="auto"><span>${d.unit === "pct" ? "%" : d.unit === "x" ? "x" : d.unit === "years" ? "yrs" : ""}</span></div></div>`).join("")}</div>
    </details>
    <details data-sec="2" ${W.open[2] ? "open" : ""}><summary>Measure earnings right</summary>
      <div class="fgrid">
        <div><label for="a-rnd">Capitalize R&D</label><select id="a-rnd">
          ${["auto", "yes", "no"].map((v) => `<option value="${v}" ${W.adjustments.capitalize_rnd === v ? "selected" : ""}>${v === "auto" ? `Auto (R&D is ${pct(c.rnd_intensity)} of revenue)` : v}</option>`).join("")}</select></div>
        ${fld("adjustments", "rnd_life", "R&D amortizable life", "3 software · 5 tech · 10 pharma", "yrs")}
        ${fld("adjustments", "one_time_addback", "One-time items to add back to EBIT", "e.g. 120 (restructuring)", "m")}
      </div>
      <label class="check"><input type="checkbox" id="a-lease" ${W.adjustments.lease_adjust ? "checked" : ""}> Treat operating leases as debt and adjust operating income ${c.has_leases ? "" : '<span class="muted">(no lease liabilities found)</span>'}</label>
      <label class="check"><input type="checkbox" id="a-norm" ${W.adjustments.normalize_margins ? "checked" : ""}> Cyclical or commodity business: normalize margins to the cycle average</label>
    </details>
    <details data-sec="3" ${W.open[3] ? "open" : ""}><summary>Risk: where it operates and what businesses it is in</summary>
      <p class="small muted">Country risk comes from where revenues are earned, not where the company is incorporated. Leave the CRP blank to look it up in Damodaran's country risk table.</p>
      <table class="t rows" id="regions"><tr><th>Country / region</th><th>% of revenue</th><th>Country risk premium (%)</th></tr>
        ${W.risk.regions.map((r, i) => `<tr><td><input data-rg="${i}" data-k="region" value="${esc(r.region)}" placeholder="e.g. Brazil"></td><td><input data-rg="${i}" data-k="weight" value="${esc(r.weight)}" placeholder="e.g. 30"></td><td><input data-rg="${i}" data-k="crp" value="${esc(r.crp)}" placeholder="lookup"></td></tr>`).join("")}</table>
      <button class="btn btn-ghost btn-small" id="add-rg">+ Add region</button>
      <p class="small muted" style="margin-top:16px">Bottom-up beta: list the businesses, their share of value or revenue and (optionally) the industry unlevered beta. Blank betas are matched to Damodaran's industry table.</p>
      <table class="t rows" id="segments"><tr><th>Business</th><th>% of value</th><th>Unlevered beta</th></tr>
        ${W.risk.segments.map((r, i) => `<tr><td><input data-sg="${i}" data-k="name" value="${esc(r.name)}" placeholder="e.g. Software (System & Application)"></td><td><input data-sg="${i}" data-k="weight" value="${esc(r.weight)}" placeholder="e.g. 80"></td><td><input data-sg="${i}" data-k="unlevered_beta" value="${esc(r.unlevered_beta)}" placeholder="lookup"></td></tr>`).join("")}</table>
      <button class="btn btn-ghost btn-small" id="add-sg">+ Add business</button>
      <div class="fgrid" style="margin-top:12px">
        ${c.currency !== "USD" ? fld("risk", "inflation", `Expected inflation in ${esc(c.currency)}`, "e.g. 4.5", "%") : ""}
        ${fld("risk", "riskfree_override", "Risk-free rate override", "default: 10y T-bond − default spread", "%")}
      </div>
    </details>
    <details data-sec="4" ${W.open[4] ? "open" : ""}><summary>Loose ends: options, NOLs, non-operating assets</summary>
      <div class="fgrid">
        ${fld("extras", "options_count", "Employee options outstanding", c.options_outstanding ? `${num(c.options_outstanding / 1e6, 1)}m from filings` : "count", "m")}
        ${fld("extras", "options_strike", "Average strike price", "per share")}
        ${fld("extras", "options_maturity", "Average remaining life", "default 5", "yrs")}
        ${fld("extras", "volatility", "Stock volatility", "default 35", "%")}
        ${fld("extras", "nol", "Net operating loss carried forward", c.nol ? `${mil(c.nol)}m from filings` : "e.g. 500", "m")}
        ${fld("extras", "non_operating_assets", "Cross holdings & other non-operating assets", "default: equity investments", "m")}
      </div>
    </details>
    <div class="actions"><button class="btn btn-ghost" id="back">Back</button><button class="btn" id="next">Continue</button></div>`;
  const save = () => {
    el.querySelectorAll("details[data-sec]").forEach((x) => (W.open[+x.dataset.sec] = x.open));
    el.querySelectorAll("[data-g]").forEach((x) => (W[x.dataset.g][x.dataset.k] = x.value));
    W.overrides = {};
    el.querySelectorAll("[data-ov]").forEach((x) => { const v = parseFloat(x.value); if (!isNaN(v)) W.overrides[x.dataset.ov] = x.dataset.u === "pct" ? v / 100 : v; });
    W.adjustments.capitalize_rnd = document.getElementById("a-rnd").value;
    W.adjustments.lease_adjust = document.getElementById("a-lease").checked;
    W.adjustments.normalize_margins = document.getElementById("a-norm").checked;
    el.querySelectorAll("[data-rg]").forEach((x) => (W.risk.regions[+x.dataset.rg][x.dataset.k] = x.value));
    el.querySelectorAll("[data-sg]").forEach((x) => (W.risk.segments[+x.dataset.sg][x.dataset.k] = x.value));
  };
  document.getElementById("add-rg").onclick = () => { save(); W.risk.regions.push({ region: "", weight: "", crp: "" }); stepRefine(); };
  document.getElementById("add-sg").onclick = () => { save(); W.risk.segments.push({ name: "", weight: "", unlevered_beta: "" }); stepRefine(); };
  document.getElementById("back").onclick = () => { save(); W.step = 2; renderWizard(); };
  document.getElementById("next").onclick = () => { save(); W.step = 4; renderWizard(); };
}

// convert the form into the API payload: blank -> null, % -> decimal, "m" fields -> full units
const MILLIONS = new Set(["tam", "one_time_addback", "nol", "options_count", "non_operating_assets"]);
function numOrNull(k, v) {
  if (v === "" || v == null) return null;
  const n = parseFloat(String(v).replace(/,/g, ""));
  if (isNaN(n)) return null;
  if (PCT.has(k)) return n / 100;
  if (MILLIONS.has(k)) return n * 1e6;
  return n;
}
function payload() {
  const obj = (o) => Object.fromEntries(Object.entries(o).map(([k, v]) => [k, typeof v === "boolean" || k === "capitalize_rnd" ? v : numOrNull(k, v)]));
  return {
    ticker: W.ticker, thesis: W.thesis, questions: W.questions.filter((q) => q.trim()), method: W.method, email: W.email || null,
    stories: W.stories, market: obj(W.market), overrides: W.overrides, adjustments: obj(W.adjustments),
    risk: {
      regions: W.risk.regions.filter((r) => r.region.trim()).map((r) => ({ region: r.region, weight: numOrNull("weight", r.weight) || 0, crp: numOrNull("crp", r.crp) })),
      segments: W.risk.segments.filter((r) => r.name.trim()).map((r) => ({ name: r.name, weight: numOrNull("weight", r.weight) || 0, unlevered_beta: numOrNull("unlevered_beta", r.unlevered_beta) })),
      inflation: numOrNull("inflation", W.risk.inflation), riskfree_override: numOrNull("riskfree_override", W.risk.riskfree_override),
    },
    extras: obj(W.extras),
  };
}

function stepReview() {
  const el = document.getElementById("wz");
  const P = payload();
  const qs = P.questions;
  const filled = Object.entries(W.stories).filter(([, v]) => v.trim());
  const extras = [
    P.market.tam ? `Market ${mil(P.market.tam)}m growing ${pct(P.market.tam_growth)}, target share ${pct(P.market.target_share)}` : null,
    Object.keys(P.overrides).length ? `${Object.keys(P.overrides).length} driver(s) locked` : null,
    P.risk.regions.length ? `${P.risk.regions.length} revenue region(s)` : null,
    P.risk.segments.length ? `${P.risk.segments.length} business segment(s) for bottom-up beta` : null,
    P.extras.nol ? `NOL ${mil(P.extras.nol)}m` : null,
    P.extras.options_count ? `${num(P.extras.options_count / 1e6, 1)}m options` : null,
    P.adjustments.normalize_margins ? "Normalized margins" : null,
  ].filter(Boolean);
  el.innerHTML = `
    <dl class="kv">
      <dt>Company</dt><dd>${esc(W.company.name)} (${esc(W.ticker)})</dd>
      <dt>Method</dt><dd>${esc(W.method === "auto" ? "Auto → " + W.company.suggested_method : W.method)}</dd>
      <dt>Thesis</dt><dd>${W.thesis.trim() ? esc(W.thesis) : filled.length ? '<span class="muted">Built from your story elements.</span>' : '<span class="muted">The bot will draft a neutral thesis.</span>'}</dd>
      <dt>Story elements</dt><dd>${filled.length ? filled.map(([k, v]) => `<b>${esc(STORY_FIELDS.find((f) => f[0] === k)[1])}:</b> ${esc(v)}`).join("<br>") : "—"}</dd>
      <dt>Your inputs</dt><dd>${extras.length ? extras.map(esc).join(" · ") : '<span class="muted">None: everything estimated.</span>'}</dd>
      <dt>Questions</dt><dd>${qs.length ? "<ul style='margin:0;padding-left:18px'>" + qs.map((q) => `<li>${esc(q)}</li>`).join("") + "</ul>" : "—"}</dd>
    </dl>
    <label for="em">Email me when it's done (optional)</label>
    <input id="em" type="email" value="${esc(W.email)}" placeholder="you@example.com">
    <div class="actions"><button class="btn btn-ghost" id="back">Back</button><button class="btn" id="run">Run valuation</button></div>`;
  document.getElementById("back").onclick = () => { W.step = 3; renderWizard(); };
  document.getElementById("run").onclick = async (e) => {
    e.target.disabled = true;
    W.email = document.getElementById("em").value;
    try {
      const { id } = await api("/api/jobs", { method: "POST", body: JSON.stringify({ ...payload(), email: W.email || null }) });
      W = blankW();
      location.hash = "#/job/" + id;
    } catch (err) { e.target.disabled = false; alert(err.message); }
  };
}

// ---------- job progress
async function renderJob(id) {
  const job = await api("/api/jobs/" + id);
  if (job.status === "done") {
    const data = await api(`/api/jobs/${id}/result`);
    return renderReport(data, { jobId: id, share: job.share_token, files: `/api/jobs/${id}/files/` });
  }
  const done = job.stages.filter((s) => s.status === "done").length;
  const plan = job.plan;
  $app.innerHTML = `
    <h2>Valuing ${esc(job.ticker)}</h2>
    <div class="job-layout">
      <div class="card">
        <div class="row" style="justify-content:space-between"><b>${job.status === "error" ? "Run failed" : `Step ${Math.min(done + 1, job.stages.length)} of ${job.stages.length}`}</b><span class="small muted">You can leave this page; the run continues.</span></div>
        <div class="bar"><i style="width:${(done / job.stages.length) * 100}%"></i></div>
        ${job.error ? `<div class="warn">${esc(job.error)}</div>` : ""}
        ${job.stages.map((s) => `<div class="stage ${s.status}"><span class="dot">${s.status === "done" ? "✓" : s.status === "error" ? "!" : ""}</span>
          <div><div class="lbl">${esc(s.label)}</div>${s.detail ? `<div class="det">${esc(s.detail)}</div>` : ""}</div></div>`).join("")}
      </div>
      <div class="card"><h3 style="margin-top:0">Valuation plan</h3>
        ${plan ? `<p><b>${esc(plan.method_title)}</b></p><p class="small muted">${esc(plan.reason)}</p>
          ${plan.key_drivers ? `<table class="t">${Object.entries(plan.key_drivers).map(([k, v]) => `<tr><td>${esc(k.replace(/_/g, " "))}</td><td>${Math.abs(v) < 2 ? pct(v) : num(v)}</td></tr>`).join("")}</table>` : ""}`
        : `<p class="muted small">The plan appears once the bot has read the filings.</p>`}
      </div>
    </div>`;
  if (job.status !== "error") pollTimer = setTimeout(() => { if (location.hash === "#/job/" + id) renderJob(id); }, 1500);
}

async function renderShare(token) {
  const data = await api("/api/share/" + token);
  renderReport(data, { readOnly: true, files: `/api/share/${token}/files/` });
}

// ---------- report
function renderReport(d, opts) {
  const r = d.result, c = d.company, s = d.sensitivity;
  const tabs = ["Report", "Sensitivity", "Probabilities", "Methodology", "Model"];
  $app.innerHTML = `
    <div class="report-head">
      <div><div class="small muted">${esc(d.date)} · ${esc(d.method_title)}</div>
        <h1 style="margin:4px 0;max-width:820px">${esc(d.sections.title || c.name)}</h1>
        ${d.sections.subtitle ? `<p class="lede" style="margin:4px 0 10px;font-style:italic">${esc(d.sections.subtitle)}</p>` : ""}
        ${c.demo ? '<span class="tag demo">Demo data — fictional company</span>' : ""} ${d.llm ? "" : '<span class="tag">Template narrative (no AI key)</span>'}</div>
      <div class="downloads">
        <a class="btn btn-small" href="${opts.files}model.xlsx">Excel model</a>
        <a class="btn btn-ghost btn-small" href="${opts.files}report.html" target="_blank">Printable report</a>
        ${d.files.pdf ? `<a class="btn btn-ghost btn-small" href="${opts.files}report.pdf">PDF</a>` : ""}
        ${d.files.market ? `<a class="btn btn-ghost btn-small" href="${opts.files}model_market.xlsx" title="Model with the market-implied drivers">Market-implied model</a>` : ""}
        ${opts.share ? `<button class="btn btn-ghost btn-small" id="share">Copy share link</button>` : ""}
      </div>
    </div>
    <div class="kpis">
      <div class="kpi"><span>Estimated value / share</span><b>${num(r.value_per_share)}</b></div>
      <div class="kpi"><span>Current price</span><b>${num(r.price)}</b></div>
      <div class="kpi"><span>Upside / (downside)</span><b>${signed(r.upside)}</b></div>
      ${d.probabilistic?.simulation?.prob_undervalued != null ? `<div class="kpi"><span>Chance undervalued (simulated)</span><b>${pct(d.probabilistic.simulation.prob_undervalued, 0)}</b></div>` : ""}
      <div class="kpi"><span>Bear → Bull</span><b>${num(s.scenarios.bear.value_per_share, 0)} → ${num(s.scenarios.bull.value_per_share, 0)}</b></div>
    </div>
    ${r.warnings.map((w) => `<div class="warn">${esc(w)}</div>`).join("")}
    <div class="tabs">${tabs.map((t, i) => `<button data-tab="${i}" class="${i ? "" : "on"}">${t}</button>`).join("")}</div>
    <div id="tab"></div>`;
  const views = [reportTab, sensitivityTab, probabilitiesTab, methodologyTab, modelTab];
  const show = (i) => {
    document.querySelectorAll(".tabs button").forEach((b) => b.classList.toggle("on", +b.dataset.tab === i));
    document.getElementById("tab").innerHTML = views[i](d, opts);
    if (i === 3 && opts.jobId) wireWhatIf(d, opts.jobId);
  };
  document.querySelectorAll(".tabs button").forEach((b) => (b.onclick = () => show(+b.dataset.tab)));
  const sh = document.getElementById("share");
  if (sh) sh.onclick = async () => {
    const url = `${location.origin}/#/share/${opts.share}`;
    try { await navigator.clipboard.writeText(url); sh.textContent = "Link copied"; } catch { prompt("View-only link:", url); }
  };
  show(0);
}

function assumptionsTable(d) {
  return `<table class="t"><tr><th>Driver</th><th>Value</th><th style="text-align:left">Why</th></tr>
    ${Object.values(d.assumptions).map((a) => `<tr><td>${esc(a.label)}</td><td>${fmtUnit(a.value, a.unit)}</td><td class="wrap">${esc(a.rationale)}</td></tr>`).join("")}</table>`;
}

const COLS = {
  fcff: [["revenue_growth", "Revenue growth", "pct"], ["revenue", "Revenue", "money"], ["operating_margin", "Operating margin", "pct"], ["ebit", "EBIT", "money"], ["tax_rate", "Tax rate", "pct"], ["nopat", "EBIT(1−t)", "money"], ["reinvestment", "− Reinvestment", "money"], ["fcff", "FCFF", "money"], ["cost_of_capital", "Cost of capital", "pct"], ["pv_fcff", "PV(FCFF)", "money"], ["roic", "ROIC", "pct"]],
  ddm: [["eps_growth", "EPS growth", "pct"], ["eps", "EPS", "num"], ["payout", "Payout", "pct"], ["dps", "DPS", "num"], ["cost_of_equity", "Cost of equity", "pct"], ["pv_dps", "PV(DPS)", "num"]],
  excess_return: [["roe", "ROE", "pct"], ["cost_of_equity", "Cost of equity", "pct"], ["beginning_book_equity", "Beginning book equity", "money"], ["net_income", "Net income", "money"], ["excess_return", "Excess return", "money"], ["pv_excess_return", "PV(excess return)", "money"]],
};

function projectionTable(d) {
  const rows = d.result.table;
  return `<div class="scroll"><table class="t"><tr><th>${esc(d.company.currency)} m</th>${rows.map((x) => `<th>Y${x.year}</th>`).join("")}</tr>
    ${COLS[d.method].map(([k, l, u]) => `<tr><td>${l}</td>${rows.map((x) => `<td>${fmtUnit(x[k], u)}</td>`).join("")}</tr>`).join("")}</table></div>`;
}

function bridgeTable(d) {
  return `<table class="t" style="max-width:520px">${d.result.bridge.map((b) => {
    const l = b.label;
    const v = /growth/i.test(l) ? pct(b.value) : /Shares/.test(l) ? mil(b.value) + "m" : /per share/.test(l) ? num(b.value) : mil(b.value);
    return `<tr><td>${esc(l)}</td><td>${v}</td></tr>`;
  }).join("")}</table>`;
}

function reportTab(d) {
  const toc = d.section_titles.map(([k, t]) => `<a href="javascript:document.getElementById('s-${k}').scrollIntoView({behavior:'smooth'})">${esc(t)}</a>`).join("");
  const body = d.section_titles.map(([k, t]) => {
    let extra = "";
    if (k === "story_to_numbers") extra = chaptersTable(d) + segmentTable(d) + assumptionsTable(d);
    if (k === "reverse_dcf") extra = reverseTable(d);
    if (k === "peers") extra = multiplesTable(d);
    if (k === "consensus") extra = consensusTable(d);
    if (k === "final_word") extra = summaryTable(d);
    if (k === "plausibility") extra = plausibilityBlock(d);
    if (k === "history" && d.earnings?.items?.length) extra = earningsTable(d);
    if (k === "valuation") extra = onePageTable(d) + projectionTable(d) + bridgeTable(d);
    if (k === "sensitivity") extra = tornadoSvg(d.sensitivity) + sensTable(d);
    if (k === "probabilistic" && d.probabilistic) extra = probabilisticBlock(d);
    return `<h3 id="s-${k}">${esc(t)}</h3>${md(d.sections[k])}${extra}`;
  }).join("");
  return `<div class="report-layout"><nav class="toc"><b>Jump to</b>${toc}<a href="javascript:document.getElementById('s-sources').scrollIntoView({behavior:'smooth'})">Sources</a></nav>
    <article class="prose"><div class="thesis">${esc(d.thesis)}</div>${body}
    <h3 id="s-sources">Sources</h3><ol class="sources">${d.sources.map((s) => `<li>${s.url ? `<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.label)}</a>` : esc(s.label)}</li>`).join("")}</ol></article></div>`;
}

function tornadoSvg(s) {
  const rows = s.drivers.slice(0, 12), base = s.base_value;
  const W = 760, L = 250, R = 60, H = 30, top = 30;
  const vals = rows.flatMap((r) => [r.low_value, r.high_value]).concat(base);
  const min = Math.min(...vals), max = Math.max(...vals), pad = (max - min) * 0.05 || 1;
  const x = (v) => L + ((v - (min - pad)) / (max - min + 2 * pad)) * (W - L - R);
  const bars = rows.map((r, i) => {
    const y = top + i * H, lo = Math.min(r.low_value, r.high_value), hi = Math.max(r.low_value, r.high_value);
    return `<text x="${L - 10}" y="${y + 19}" text-anchor="end" font-size="12">${esc(r.label)}</text>
      <rect x="${x(lo)}" y="${y + 6}" width="${Math.max(1, x(base) - x(lo))}" height="18" fill="#b4433a" rx="2"/>
      <rect x="${x(base)}" y="${y + 6}" width="${Math.max(1, x(hi) - x(base))}" height="18" fill="#2e7d5b" rx="2"/>
      <text x="${x(lo) - 4}" y="${y + 19}" text-anchor="end" font-size="10" fill="#666">${num(lo, 1)}</text>
      <text x="${x(hi) + 4}" y="${y + 19}" font-size="10" fill="#666">${num(hi, 1)}</text>`;
  }).join("");
  const h = top + rows.length * H + 10;
  return `<svg viewBox="0 0 ${W} ${h}" width="100%" style="font-family:Inter,sans-serif;max-width:${W}px">
    <text x="${x(base)}" y="16" text-anchor="middle" font-size="12" font-weight="600">Base ${num(base)}</text>
    ${bars}<line x1="${x(base)}" x2="${x(base)}" y1="22" y2="${h - 6}" stroke="#16181d"/></svg>`;
}

function sensitivityTab(d, opts) {
  const s = d.sensitivity;
  const sc = ["bear", "base", "bull"].map((k) => `<div class="kpi"><span>${k[0].toUpperCase() + k.slice(1)} case</span><b>${num(s.scenarios[k].value_per_share)}</b>
     ${k !== "base" ? `<a class="small" href="${opts.files}model_${k}.xlsx">Download ${k} model</a>` : `<a class="small" href="${opts.files}model.xlsx">Download base model</a>`}</div>`).join("");
  return `<p class="muted">Each bar moves one driver to its low and high value while holding everything else at the base case. Red: value falls; green: value rises. Bull and bear cases move every driver in the favorable or unfavorable direction at once.</p>
    ${tornadoSvg(s)}
    <div class="kpis" style="grid-template-columns:repeat(3,1fr)">${sc}</div>
    <div class="scroll"><table class="t"><tr><th>Driver</th><th>Low input</th><th>High input</th><th>Value at low</th><th>Value at high</th><th>Swing</th></tr>
    ${s.drivers.map((r) => `<tr><td>${esc(r.label)}</td><td>${fmtUnit(r.low_input, r.unit)}</td><td>${fmtUnit(r.high_input, r.unit)}</td><td>${num(r.low_value)}</td><td>${num(r.high_value)}</td><td>${num(r.range)}</td></tr>`).join("")}</table></div>`;
}

function methodologyTab(d, opts) {
  const cells = d.methodology.cells;
  const editable = !!opts.jobId;
  return `<p>${esc(d.method_reason)}</p>
    <p class="muted small">Every value driver maps to one blue input cell in the Excel model. ${editable ? "Edit values below to see how the value changes (nothing is saved)." : ""}</p>
    <div class="scroll"><table class="t whatif"><tr><th>Driver</th><th>Excel cell</th><th>Value</th><th style="text-align:left">What it represents</th></tr>
    ${Object.entries(d.assumptions).map(([k, a]) => {
      const shown = a.unit === "pct" ? (a.value * 100).toFixed(2) : a.value.toFixed(2);
      return `<tr><td>${esc(a.label)}</td><td><code>${esc(cells[k])}</code></td>
        <td>${editable ? `<input data-k="${k}" data-u="${a.unit}" value="${shown}"> ${a.unit === "pct" ? "%" : a.unit === "x" ? "x" : ""}` : fmtUnit(a.value, a.unit)}</td>
        <td class="wrap">${esc(a.story)}</td></tr>`;
    }).join("")}</table></div>
    ${editable ? `<div class="row" style="margin-top:12px"><button class="btn btn-small" id="recalc">Recalculate</button><span id="wi" class="muted"></span></div>` : ""}
    <p class="small muted" style="margin-top:18px">Output cell: <code>${esc(d.methodology.output)}</code>. Cost of capital: CAPM cost of equity (risk-free ${pct(d.cost_of_capital.riskfree, 2)} + beta ${num(d.cost_of_capital.beta)} × ERP ${pct(d.cost_of_capital.erp, 2)}), synthetic rating ${esc(d.cost_of_capital.rating)} for debt, market-value weights.</p>`;
}

function wireWhatIf(d, jobId) {
  const btn = document.getElementById("recalc");
  if (!btn) return;
  btn.onclick = async () => {
    const a = {};
    document.querySelectorAll("[data-k]").forEach((i) => { const v = parseFloat(i.value); if (!isNaN(v)) a[i.dataset.k] = i.dataset.u === "pct" ? v / 100 : v; });
    const out = await api(`/api/jobs/${jobId}/revalue`, { method: "POST", body: JSON.stringify({ assumptions: a }) });
    document.getElementById("wi").innerHTML = `What-if value: <b>${num(out.value_per_share)}</b> (${signed(out.upside)} vs price; base ${num(d.result.value_per_share)})${out.warnings.length ? " · " + esc(out.warnings.join(" ")) : ""}`;
  };
}

function modelTab(d) {
  const coc = d.cost_of_capital, m = d.metrics;
  const hcols = [["revenue", "Revenue", "money"], ["revenue_growth", "Growth", "pct"], ["operating_margin", "Op. margin", "pct"], ["effective_tax_rate", "Tax rate", "pct"], ["sales_to_capital", "Sales/capital", "x"], ["roic", "ROIC", "pct"], ["roe", "ROE", "pct"], ["payout_ratio", "Payout", "pct"]];
  return `<h3>Projections</h3>${projectionTable(d)}
    <h3>Value bridge</h3>${bridgeTable(d)}
    ${d.earnings?.items?.length ? `<h3>Earnings adjustments</h3>${earningsTable(d)}` : ""}
    ${d.risk ? `<h3>Risk inputs</h3><table class="t"><tr><th>Input</th><th>Value</th><th style="text-align:left">Source</th></tr>
      <tr><td>Risk-free rate</td><td>${pct(d.risk.riskfree, 2)}</td><td class="wrap">${esc(d.risk.riskfree_source)}</td></tr>
      <tr><td>Beta</td><td>${num(d.risk.beta)}</td><td class="wrap">${esc(d.risk.beta_source)}</td></tr>
      <tr><td>Equity risk premium</td><td>${pct(d.risk.erp, 2)}</td><td class="wrap">${esc(d.risk.erp_source)}</td></tr></table>
      ${(d.risk.notes || []).map((n) => `<div class="warn">${esc(n)}</div>`).join("")}` : ""}
    <h3>Cost of capital</h3><table class="t" style="max-width:520px">
      ${[["Risk-free rate", pct(coc.riskfree, 2)], ["Equity risk premium", pct(coc.erp, 2)], ["Beta", num(coc.beta)], ["Cost of equity", pct(coc.cost_of_equity, 2)], ["Synthetic rating", esc(coc.rating)], ["Pre-tax cost of debt", pct(coc.pretax_cost_of_debt, 2)], ["Debt weight", pct(coc.debt_weight)], ["Cost of capital", pct(coc.wacc, 2)], ["Mature cost of capital", pct(coc.terminal_wacc, 2)]].map(([a, b]) => `<tr><td>${a}</td><td>${b}</td></tr>`).join("")}</table>
    <h3>History</h3><div class="scroll"><table class="t"><tr><th></th>${m.map((x) => `<th>FY${x.fiscal_year}</th>`).join("")}</tr>
    ${hcols.map(([k, l, u]) => `<tr><td>${l}</td>${m.map((x) => `<td>${fmtUnit(x[k], u)}</td>`).join("")}</tr>`).join("")}</table></div>
    <h3>Research briefing</h3><div class="prose">${md(d.briefing)}</div>`;
}

// ---------- probabilistic views (break-even, scenarios, simulation)
function curveSvg(c) {
  const pts = c.points, W = 760, H = 260, L = 60, R = 20, T = 20, B = 40;
  const isPct = c.unit === "pct", fx = (v) => (isPct ? pct(v) : num(v));
  const xs = pts.map((p) => p.x), ys = pts.map((p) => p.value).concat(c.price);
  const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys), py = (y1 - y0) * 0.08 || 1;
  const X = (v) => L + ((v - x0) / (x1 - x0 || 1)) * (W - L - R), Y = (v) => T + (1 - (v - (y0 - py)) / (y1 - y0 + 2 * py)) * (H - T - B);
  const path = pts.map((p, i) => `${i ? "L" : "M"}${X(p.x).toFixed(1)},${Y(p.value).toFixed(1)}`).join("");
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => x0 + f * (x1 - x0));
  const be = c.break_even != null && c.break_even >= x0 && c.break_even <= x1
    ? `<line x1="${X(c.break_even)}" x2="${X(c.break_even)}" y1="${T}" y2="${H - B}" stroke="#888" stroke-dasharray="3 3"/>
       <text x="${X(c.break_even) + 6}" y="${Y(c.price) - 8}" font-size="11">break-even ${fx(c.break_even)}</text>` : "";
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" style="max-width:${W}px;font-family:Inter,sans-serif">
    <line x1="${L}" x2="${W - R}" y1="${Y(c.price)}" y2="${Y(c.price)}" stroke="#b4433a" stroke-dasharray="5 4"/>
    <text x="${W - R}" y="${Y(c.price) - 5}" text-anchor="end" font-size="11" fill="#b4433a">price ${num(c.price)}</text>
    <path d="${path}" fill="none" stroke="#1f5f4a" stroke-width="2.5"/>
    <circle cx="${X(c.base)}" cy="${Y(pts.reduce((a, p) => (Math.abs(p.x - c.base) < Math.abs(a.x - c.base) ? p : a)).value)}" r="4" fill="#1f5f4a"/>
    ${be}
    <line x1="${L}" x2="${W - R}" y1="${H - B}" y2="${H - B}" stroke="#ccc"/>
    ${ticks.map((t) => `<text x="${X(t)}" y="${H - B + 16}" text-anchor="middle" font-size="10" fill="#666">${fx(t)}</text>`).join("")}
    <text x="${(L + W - R) / 2}" y="${H - 4}" text-anchor="middle" font-size="11">${esc(c.label)}</text>
    <text x="12" y="${T + 4}" font-size="10" fill="#666">${num(y1, 0)}</text><text x="12" y="${H - B}" font-size="10" fill="#666">${num(y0, 0)}</text>
  </svg>`;
}

function histSvg(sim, price) {
  const c = sim.histogram.counts, e = sim.histogram.edges, W = 760, H = 220, L = 20, R = 20, T = 24, B = 30;
  const max = Math.max(...c), x0 = e[0], x1 = e[e.length - 1];
  const X = (v) => L + ((Math.min(Math.max(v, x0), x1) - x0) / (x1 - x0 || 1)) * (W - L - R);
  const bars = c.map((n, i) => { const h = (n / max) * (H - T - B); return `<rect x="${X(e[i]) + 0.5}" y="${H - B - h}" width="${Math.max(1, X(e[i + 1]) - X(e[i]) - 1)}" height="${h}" fill="${e[i] < price ? "#d7c4c1" : "#9db8ad"}"/>`; }).join("");
  const med = sim.percentiles["50"];
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" style="max-width:${W}px;font-family:Inter,sans-serif">${bars}
    <line x1="${X(med)}" x2="${X(med)}" y1="${T - 6}" y2="${H - B}" stroke="#1f5f4a" stroke-width="2"/><text x="${X(med) + 4}" y="${T}" font-size="11" fill="#1f5f4a">median ${num(med)}</text>
    ${price ? `<line x1="${X(price)}" x2="${X(price)}" y1="${T - 6}" y2="${H - B}" stroke="#b4433a" stroke-dasharray="5 4" stroke-width="2"/><text x="${X(price) + 4}" y="${T + 14}" font-size="11" fill="#b4433a">price ${num(price)}</text>` : ""}
    <line x1="${L}" x2="${W - R}" y1="${H - B}" y2="${H - B}" stroke="#ccc"/>
    ${[0, 0.25, 0.5, 0.75, 1].map((f) => { const v = x0 + f * (x1 - x0); return `<text x="${X(v)}" y="${H - B + 16}" text-anchor="middle" font-size="10" fill="#666">${num(v, 0)}</text>`; }).join("")}
  </svg>`;
}

function probabilisticBlock(d) {
  const p = d.probabilistic, sim = p.simulation, pc = sim.percentiles, price = d.result.price;
  return `
    <h4>What the price implies</h4>${curveSvg(p.curve)}
    <table class="t"><tr><th>Key driver</th><th>Base case</th><th>Break-even (value = price)</th></tr>
      ${p.break_even.map((b) => `<tr><td>${esc(b.label)}</td><td>${fmtUnit(b.base, b.unit)}</td><td>${b.break_even == null ? '<span class="muted">not reachable</span>' : fmtUnit(b.break_even, b.unit)}</td></tr>`).join("")}</table>
    <h4>Plausible scenarios</h4>
    <table class="t"><tr><th>Scenario</th><th>Probability</th><th>Value / share</th><th style="text-align:left">Story</th></tr>
      ${p.scenarios.scenarios.map((s) => `<tr><td>${esc(s.name)}</td><td>${pct(s.probability, 0)}</td><td>${num(s.value_per_share)}</td><td class="wrap">${esc(s.narrative)}</td></tr>`).join("")}
      <tr><td><b>Probability-weighted</b></td><td>100%</td><td><b>${num(p.scenarios.expected_value)}</b></td><td></td></tr></table>
    <h4>Simulated value (${num(sim.n, 0)} trials)</h4>${histSvg(sim, price)}
    <table class="t"><tr><th>P10</th><th>P25</th><th>Median</th><th>P75</th><th>P90</th><th>P(undervalued)</th><th>Margin of safety</th><th>Buy below</th></tr>
      <tr><td>${num(pc["10"])}</td><td>${num(pc["25"])}</td><td>${num(pc["50"])}</td><td>${num(pc["75"])}</td><td>${num(pc["90"])}</td>
      <td>${pct(sim.prob_undervalued, 0)}</td><td>${pct(sim.margin_of_safety, 0)}</td><td>${num(sim.buy_below)}</td></tr></table>
    <p class="small muted">Simulated: ${sim.drivers.map((x) => `${esc(x.label)} (mean ${fmtUnit(x.mean, x.unit)}, sd ${fmtUnit(x.sd, x.unit)})`).join("; ")}.
      ${sim.correlations.length ? "Correlated: " + sim.correlations.map((c) => `${esc(c.a)} / ${esc(c.b)} ρ=${c.rho}`).join(", ") + "." : ""}
      Margin of safety = 1 − P25 / median, so it is wider for riskier firms rather than a fixed 20%.</p>
    <h4>Stable-growth consistency tests</h4>
    <table class="t"><tr><th>Test</th><th>Result</th><th style="text-align:left">Detail</th></tr>
      ${p.checks.map((c) => `<tr><td>${esc(c.test)}</td><td class="${c.pass ? "pos" : "neg"}">${c.pass ? "Pass" : "Fail"}</td><td class="wrap">${esc(c.detail)}</td></tr>`).join("")}</table>`;
}

function probabilitiesTab(d) {
  if (!d.probabilistic) return `<p class="muted">This run predates the probabilistic analysis.</p>`;
  return `<p class="muted">Sensitivity holds everything else constant; in the real world variables move together. This view focuses on a few key drivers, asks what the price implies for each (break-even), values a handful of coherent scenarios, and simulates the key drivers jointly with correlations to get a distribution of value.</p>${probabilisticBlock(d)}`;
}

// ---------- narrative tests, earnings adjustments, insights
function storiesTable(d) {
  const st = Object.entries(d.stories || {}).filter(([, v]) => v);
  if (!st.length) return "";
  const names = Object.fromEntries(STORY_FIELDS.map(([k, t]) => [k, t]));
  return `<table class="t"><tr><th>Story element</th><th style="text-align:left">The story</th></tr>
    ${st.map(([k, v]) => `<tr><td>${esc(names[k] || k)}</td><td class="wrap">${esc(v)}</td></tr>`).join("")}</table>`;
}

function earningsTable(d) {
  const e = d.earnings;
  return `<table class="t"><tr><th>Adjustment</th><th>EBIT effect (m)</th><th>Invested capital (m)</th><th style="text-align:left">Detail</th></tr>
    <tr><td>Reported</td><td>${mil(e.ebit_reported)}</td><td>${mil(e.invested_capital_reported)}</td><td></td></tr>
    ${e.items.map((i) => `<tr><td>${esc(i.item)}</td><td>${mil(i.ebit)}</td><td>${i.invested_capital ? mil(i.invested_capital) : ""}</td><td class="wrap">${esc(i.detail)}</td></tr>`).join("")}
    <tr><td><b>Adjusted</b></td><td><b>${mil(e.ebit_adjusted)}</b></td><td><b>${mil(e.invested_capital_adjusted)}</b></td><td></td></tr></table>`;
}

function plausibilityBlock(d) {
  const tests = d.narrative_tests || [], ins = d.insights || {};
  const lvl = { impossible: "Possible?", implausible: "Plausible?", improbable: "Probable?" };
  let h = `<table class="t"><tr><th>Test</th><th>Question</th><th>Result</th><th style="text-align:left">Detail</th></tr>
    ${tests.map((t) => `<tr><td>${esc(t.test)}</td><td>${lvl[t.level] || ""}</td><td class="${t.pass ? "pos" : "neg"}">${t.pass ? "Pass" : "Flag"}</td><td class="wrap">${esc(t.detail)}</td></tr>`).join("")}</table>`;
  const vg = ins.value_of_growth;
  if (vg) h += `<table class="t" style="max-width:520px"><tr><th>Where the value comes from</th><th>m</th></tr>
      <tr><td>Existing assets (status quo, no growth)</td><td>${mil(vg.existing_assets)}</td></tr>
      <tr><td>Growth assets</td><td>${mil(vg.growth_assets)} (${pct(vg.growth_share, 0)})</td></tr></table>`;
  const k = ins.implied_cost_of_equity;
  if (k && k.ke != null) h += `<p class="small muted">Market-implied cost of equity from P/BV ${num(k.pbv)}x and ROE ${pct(k.roe)}: <b>${pct(k.ke, 2)}</b> (model: ${pct(k.model_ke, 2)}).</p>`;
  return h;
}


// ---------- report tables modeled on the classic one-page valuation
function chaptersTable(d) {
  if (!d.chapters?.length) return "";
  return `<table class="t"><tr><th>Chapter</th><th style="text-align:left">The storyline</th><th style="text-align:left">The numbers</th></tr>
    ${d.chapters.map((c) => `<tr><td><b>${esc(c.chapter)}</b></td><td class="wrap">${esc(c.story)}</td><td class="wrap">${esc(c.numbers)}</td></tr>`).join("")}</table>`;
}
function segmentTable(d) {
  const s = d.segment_economics;
  if (!s) return "";
  return `<table class="t" style="max-width:560px"><tr><th>Business</th><th>Year-10 revenue</th><th>Target margin</th></tr>
    ${s.rows.map((r) => `<tr><td>${esc(r.name)}</td><td>${mil(r.revenue_y10)}m</td><td>${pct(r.target_margin)}</td></tr>`).join("")}
    <tr><td><b>Consolidated</b></td><td><b>${mil(s.revenue)}m</b></td><td><b>${pct(s.margin, 2)}</b></td></tr></table>
    <p class="small muted">Margin reconciliation: ${esc(s.text)}</p>`;
}
function onePageTable(d) {
  if (!d.one_page) return "";
  return `<div class="scroll"><table class="t"><tr><th>The assumptions</th><th>Base year</th><th>Years 1-5</th><th>Years 6-10</th><th>After year 10</th><th style="text-align:left">Link to story</th></tr>
    ${d.one_page.map((o) => `<tr><td><b>${esc(o.item)}</b></td><td>${esc(o.base)}</td><td>${esc(o.y1_5)}</td><td>${esc(o.y6_10)}</td><td>${esc(o.after)}</td><td class="wrap">${esc(o.story.slice(0, 160))}</td></tr>`).join("")}</table></div>`;
}
function reverseTable(d) {
  const r = d.probabilistic?.reverse_dcf;
  if (!r?.rows?.length) return "";
  return `<table class="t" style="max-width:620px"><tr><th></th><th>My estimates</th><th>Market-implied</th></tr>
    ${r.rows.map((x) => `<tr><td>${x.diverges ? "<b>" : ""}${esc(x.label)}${x.diverges ? "</b>" : ""}</td><td>${fmtUnit(x.mine, x.unit)}</td><td>${fmtUnit(x.market, x.unit)}</td></tr>`).join("")}
    <tr><td><b>Value per share</b></td><td><b>${num(r.base_value)}</b></td><td><b>${num(r.implied_value)}</b></td></tr></table>
    <p class="small muted">${r.converged ? "Solved exactly: the market-implied drivers reproduce the price." : "The price could not be reached within driver bounds."} ${esc(r.note || "")}</p>`;
}
function sensTable(d) {
  const s = d.sensitivity;
  return `<table class="t"><tr><th>Driver</th><th>Low case</th><th>Base case</th><th>High case</th><th>Spread</th></tr>
    ${s.drivers.slice(0, 8).map((x) => `<tr><td>${esc(x.label)}</td><td>${num(Math.min(x.low_value, x.high_value))}</td><td>${num(s.base_value)}</td><td>${num(Math.max(x.low_value, x.high_value))}</td><td>${num(x.range)}</td></tr>`).join("")}</table>`;
}
function multiplesTable(d) {
  const ins = d.insights || {}, m = ins.multiples;
  if (!m) return "";
  const f = (x) => (x == null ? "—" : num(x, 1) + "x");
  return `<table class="t" style="max-width:620px"><tr><th></th><th>EV / sales</th><th>EV / EBIT</th><th>PE</th><th>P / book</th></tr>
    <tr><td>At my value</td><td>${f(m.at_value.ev_sales)}</td><td>${f(m.at_value.ev_ebit)}</td><td>${f(m.at_value.pe)}</td><td>${f(m.at_value.pbv)}</td></tr>
    <tr><td>At today's price</td><td>${f(m.at_price.ev_sales)}</td><td>${f(m.at_price.ev_ebit)}</td><td>${f(m.at_price.pe)}</td><td>${f(m.at_price.pbv)}</td></tr></table>
    <p class="small muted">Conventional multiple for this kind of firm: <b>${esc(ins.conventional_multiple.multiple)}</b> (${esc(ins.conventional_multiple.why)}).</p>`;
}
function consensusTable(d) {
  const c = d.company.consensus || {};
  if (!c.target_mean_price) return "";
  return `<table class="t" style="max-width:620px"><tr><th>Source</th><th>Value / target</th><th style="text-align:left">Basis</th></tr>
    <tr><td>This valuation</td><td>${num(d.result.value_per_share)}</td><td class="wrap">${esc(d.method_title)}</td></tr>
    <tr><td>Analyst mean target${c.analyst_count ? ` (${c.analyst_count})` : ""}</td><td>${num(c.target_mean_price)}</td><td class="wrap">${esc(c.recommendation || "")}</td></tr>
    <tr><td>Current price</td><td>${num(d.result.price)}</td><td class="wrap">Market</td></tr></table>`;
}
function summaryTable(d) {
  if (!d.summary) return "";
  return `<table class="t" style="max-width:620px"><tr><th colspan="2">Valuation summary</th></tr>
    ${d.summary.map(([k, v]) => `<tr><td>${esc(k)}</td><td>${esc(v)}</td></tr>`).join("")}</table>`;
}

// start the router last, once every module-level binding (e.g. the wizard state W) exists
route();
