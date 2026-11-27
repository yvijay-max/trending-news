(() => {
const LABELS = {maintenance:"Planned maintenance",incident:"Downtime / incident",market:"Market / BTC price",delisting:"Delisting / risk notice",listing:"New listing",campaign:"Trading campaign",promo:"Earn / yield promo",community:"Community engagement",network:"Network / deposit update",product:"Product update"};
const PROMO = ["promo","campaign","community"];
const ALERT = ["incident","maintenance","market"];
const FILES = ["posts","events","scorecard","voices","lessons","incidents","x_posts","x_incidents","status_incidents","manual_incidents","discord_posts"];
const OBJ_FILES = ["voice"];
const S = {infl:[], inflPosts:[], inflInfo:{}, inflSel:null, msel:{}, stsel:{}, vlabel:{}, chat:{}, chatGroup:{}, chatFilter:"all", pb:null, pbLang:"en", xsel:null, regions:[], region:null, exchanges:[], data:{}, btc:[], groups:{}, current:null, evt:null, inc:null};
const $ = (id) => document.getElementById(id) || document.createElement("div");
const safe = (name, fn) => { try { fn(); } catch (e) { console.error("Section failed:", name, e); } };
const el = (tag, props = {}, ...kids) => { const n = document.createElement(tag); Object.assign(n, props); kids.forEach(k => n.append(k)); return n; };
const fmt = (n) => (n == null || isNaN(n)) ? "—" : Number(n).toLocaleString("en-US");
const short = (n) => n >= 1e6 ? (n/1e6).toFixed(2).replace(/\.?0+$/,"")+"M" : n >= 1e3 ? (n/1e3).toFixed(1).replace(/\.0$/,"")+"K" : String(Math.round(n));
const day = (iso) => (iso || "").slice(0, 10);
const getJSON = (p) => fetch(p, {cache: "no-cache"}).then(r => r.ok ? r.json() : null).catch(() => null);

async function load() {
  S.exchanges = ((await getJSON("data/exchanges.json")) || []).map(e => ({region: "global", ...e}));
  S.regions = (await getJSON("data/regions.json")) || [{id: "global", name: "Worldwide"}];
  S.region = S.regions[0].id;
  S.btc = (await getJSON("data/btc.json")) || [];
  S.pb = await getJSON("data/playbook.json");
  S.infl = (await getJSON("data/influencers.json")) || [];
  S.inflPosts = (await getJSON("data/influencers/posts.json")) || [];
  S.inflInfo = (await getJSON("data/influencers/info.json")) || {};
  S.groups = (await getJSON("data/groups.json")) || {};
  const last = await getJSON("data/last_run.json");
  await Promise.all(S.exchanges.map(async ex => {
    const d = {};
    await Promise.all(FILES.map(async f => { d[f] = (await getJSON(`data/${ex.id}/${f}.json`)) || []; }));
    await Promise.all(OBJ_FILES.map(async f => { d[f] = await getJSON(`data/${ex.id}/${f}.json`); }));
    S.data[ex.id] = d;
  }));
  if (!S.exchanges.length) { $("updated").textContent = "Could not load data/exchanges.json. Check that the data folder is in the repo."; return; }
  $("updated").textContent = last ? `Channels last scraped ${new Date(last.at).toLocaleString()}` : "Not scraped yet. Showing seed data.";
  route(); addEventListener("hashchange", route);
  let t; addEventListener("resize", () => { clearTimeout(t); t = setTimeout(() => S.current && S.inflPosts && S.current.startsWith("influencers") ? safe("influencers", influencersView) : S.current && !S.current.startsWith("compare") && S.current !== "playbook" && charts(), 150); });
}

const inRegion = () => S.exchanges.filter(e => e.region === S.region);
function tabs() {
  const rn = $("regions");
  rn.replaceChildren(...S.regions.map(r => {
    const b = el("button", {textContent: r.name, type: "button"});
    b.setAttribute("aria-current", String(r.id === S.region && S.current !== "playbook"));
    b.onclick = () => { const first = S.exchanges.find(e => e.region === r.id); location.hash = first ? first.id : "compare-" + r.id; };
    return b;
  }));
  if (S.pb) { const b = el("button", {textContent: "Playbook", type: "button"}); b.setAttribute("aria-current", String(S.current === "playbook")); b.onclick = () => { location.hash = "playbook"; }; rn.append(b); }
  const nav = $("tabs");
  const items = [...inRegion().map(e => [e.id, e.name]), ...(S.infl.some(f => (f.region || "global") === S.region) ? [["influencers-" + S.region, "Influencers"]] : []), ["compare-" + S.region, "Compare"]];
  nav.replaceChildren(...items.map(([id, name]) => {
    const b = el("button", {textContent: name, type: "button"});
    b.dataset.id = id; b.onclick = () => { location.hash = id; };
    return b;
  }));
}

function route() {
  let id = location.hash.slice(1) || (S.exchanges[0] && S.exchanges[0].id);
  if (id === "compare") id = "compare-" + S.region;
  if (id === "playbook") {
    S.current = id; tabs();
    $("view-exchange").hidden = true; $("view-compare").hidden = true; $("view-influencers").hidden = true; $("view-playbook").hidden = false;
    safe("playbook", playbook); return;
  }
  $("view-playbook").hidden = true;
  if (id.startsWith("influencers")) {
    const r = id.split("-")[1]; if (S.regions.some(x => x.id === r)) S.region = r;
    S.current = id; tabs();
    document.querySelectorAll("#tabs button").forEach(b => b.setAttribute("aria-current", String(b.dataset.id === id)));
    $("view-exchange").hidden = true; $("view-compare").hidden = true; $("view-influencers").hidden = false;
    safe("influencers", influencersView); return;
  }
  $("view-influencers").hidden = true;
  const cmp = id.startsWith("compare");
  if (cmp) { const r = id.split("-")[1]; if (S.regions.some(x => x.id === r)) S.region = r; }
  else { const ex = S.exchanges.find(e => e.id === id); if (ex) S.region = ex.region; }
  S.current = id;
  tabs();
  document.querySelectorAll("#tabs button").forEach(b => b.setAttribute("aria-current", String(b.dataset.id === id)));
  $("view-exchange").hidden = cmp; $("view-compare").hidden = !cmp;
  safe("view", () => cmp ? compare() : exchange(id));
}

function stats(posts) {
  const n = posts.length;
  if (!n) return {n:0};
  const views = posts.map(p => +p.views || 0);
  return {
    n, avg: Math.round(views.reduce((a,b)=>a+b,0)/n), top: Math.max(...views),
    promo: Math.round(posts.filter(p => PROMO.includes(p.category)).length / n * 100),
    alerts: posts.filter(p => p.category === "incident" || p.category === "maintenance").length,
    btc: posts.filter(p => p.btc || p.category === "market").length,
    first: day(posts[0].date), lastd: day(posts[posts.length-1].date),
    seed: posts.every(p => p.seed),
  };
}

function exchange(id) {
  const ex = S.exchanges.find(e => e.id === id); if (!ex) return;
  const d = S.data[id] || {};
  const st = stats(d.posts || []);
  $("ex-title").textContent = ex.name;
  $("ex-summary").textContent = st.n
    ? `${fmt(st.n)} announcement posts tracked from ${st.first} to ${st.lastd}. ${st.promo}% were promos, campaigns or games, ${st.alerts} were about downtime or maintenance, and ${st.btc} mentioned BTC or the market.${st.seed ? " These are seed rows typed in by hand; the first scheduled run replaces them with scraped posts." : ""}`
    : "No posts collected yet. Run the GitHub Action or add channels in data/exchanges.json.";
  const note = $("ex-note"); note.hidden = !ex.note; note.textContent = ex.note || "";
  const LN = {en: "English", "en-IN": "English (India)", hinglish: "Hinglish", hi: "Hindi", ta: "Tamil", te: "Telugu", bn: "Bengali", kn: "Kannada", ml: "Malayalam", gu: "Gujarati", pa: "Punjabi", ur: "Urdu"};
  const ch = (ex.channels || []).map(c => `@${c.handle} (${c.type}${c.lang ? ", " + (LN[c.lang] || c.lang) : ""})`);
  const langs = {}; (d.posts || []).forEach(p => { if (p.lang) langs[p.lang] = (langs[p.lang] || 0) + 1; });
  const mixTxt = Object.keys(langs).length > 1 ? " Post languages: " + Object.entries(langs).sort((a, b) => b[1] - a[1]).map(([k, v]) => `${LN[k] || k} ${Math.round(v / (d.posts || []).length * 100)}%`).join(", ") + "." : "";
  $("ex-channels").textContent = (ch.length ? "Tracked channels: " + ch.join(", ") + "." : "No Telegram channels configured yet.") + mixTxt;
  $("kpis").replaceChildren(...[
    [fmt(st.n), "posts tracked"], [st.n ? short(st.avg) : "—", "average views per post"],
    [st.n ? short(st.top) : "—", "best post views"], [st.n ? st.promo + "%" : "—", "promos, campaigns, games"],
    [st.n ? String(st.alerts) : "—", "downtime or maintenance posts"],
  ].map(([v, l]) => el("div", {className: "kpi"}, el("b", {textContent: v}), el("span", {textContent: l}))));
  safe("charts", charts); safe("feed", () => feed(d.posts || [])); safe("discord", () => discordSec(ex, d.discord_posts || [])); safe("status", () => statusSec(ex, d.status_incidents || [])); safe("x", () => xsection(d.x_posts || [], d.x_incidents || [], ex)); safe("xmanual", () => xManual(ex, d.manual_incidents || []));
  safe("incidents", () => incidents(d.incidents || [])); safe("groups", () => groups(id)); safe("chat", () => chat(ex)); safe("voice", () => voiceSec(ex, d.voice)); safe("events", () => events(d.events || []));
  safe("score", () => score(d.scorecard || [])); safe("voices", () => voices(d.voices || [])); safe("lessons", () => lessons(d.lessons || []));
}

function charts() { const d = S.data[S.current] || {}; pulse(d.posts || []); mix(d.posts || []); incChart(); }

/* ---------- tooltip ---------- */
const tip = $("tip");
function showTip(ev, text) { tip.hidden = false; tip.textContent = text; const w = tip.offsetWidth; tip.style.left = Math.min(ev.clientX + 12, innerWidth - w - 8) + "px"; tip.style.top = (ev.clientY - 40) + "px"; }
function hideTip() { tip.hidden = true; }
const NS = "http://www.w3.org/2000/svg";
const svgEl = (tag, attrs) => { const n = document.createElementNS(NS, tag); for (const k in attrs) n.setAttribute(k, attrs[k]); return n; };

/* ---------- pulse chart: posts per day vs BTC ---------- */
function pulse(posts) {
  const box = $("pulse"); box.replaceChildren();
  if (!posts.length) { box.append(el("p", {className: "empty", textContent: "No posts yet."})); return; }
  const byDay = {};
  posts.forEach(p => { const k = day(p.date); (byDay[k] = byDay[k] || {n:0, alert:0}).n++; if (p.category === "incident" || p.category === "maintenance") byDay[k].alert++; });
  const start = new Date(day(posts[0].date) + "T00:00:00Z"), end = new Date(day(posts[posts.length-1].date) + "T00:00:00Z");
  const days = []; for (let t = +start; t <= +end; t += 864e5) days.push(new Date(t).toISOString().slice(0,10));
  const btc = Object.fromEntries(S.btc.map(r => [r.date, r.price]));
  const W = box.clientWidth || 800, H = 240, L = 34, R = 58, T = 10, B = 26;
  const iw = W - L - R, ih = H - T - B, bw = Math.max(1, iw / days.length);
  const maxN = Math.max(...days.map(k => (byDay[k] || {n:0}).n), 1);
  const prices = days.map(k => btc[k]).filter(v => v != null);
  const pMin = prices.length ? Math.min(...prices) * 0.98 : 0, pMax = prices.length ? Math.max(...prices) * 1.02 : 1;
  const svg = svgEl("svg", {viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Posts per day with downtime posts marked and the BTC price"});
  const y = v => T + ih - v / maxN * ih, yp = v => T + ih - (v - pMin) / (pMax - pMin) * ih;
  [0, Math.ceil(maxN/2), maxN].forEach(v => { svg.append(svgEl("line", {x1: L, x2: L+iw, y1: y(v), y2: y(v), stroke: "var(--line)"})); const t = svgEl("text", {x: L-6, y: y(v)+4, "text-anchor": "end"}); t.textContent = v; svg.append(t); });
  days.forEach((k, i) => {
    const v = byDay[k] || {n:0, alert:0}; const x = L + i * bw;
    if (v.n) svg.append(svgEl("rect", {x: x + bw*0.12, y: y(v.n), width: Math.max(1, bw*0.76), height: ih - (y(v.n) - T), fill: "var(--bar)", rx: 2}));
    if (v.alert) svg.append(svgEl("rect", {x: x + bw*0.12, y: T + ih + 4, width: Math.max(2, bw*0.76), height: 6, fill: "var(--down)"}));
    const hit = svgEl("rect", {x, y: T, width: bw, height: ih + 12, fill: "transparent"});
    hit.addEventListener("pointermove", ev => showTip(ev, `${k}: ${v.n} posts${v.alert ? `, ${v.alert} downtime/maintenance` : ""}${btc[k] ? `, BTC $${fmt(Math.round(btc[k]))}` : ""}`));
    hit.addEventListener("pointerleave", hideTip);
    svg.append(hit);
  });
  if (prices.length > 1) {
    let dpath = ""; days.forEach((k, i) => { if (btc[k] != null) dpath += (dpath ? "L" : "M") + (L + i*bw + bw/2).toFixed(1) + "," + yp(btc[k]).toFixed(1); });
    svg.append(svgEl("path", {d: dpath, fill: "none", stroke: "var(--btc)", "stroke-width": 2, "pointer-events": "none"}));
    [pMin, pMax].forEach(v => { const t = svgEl("text", {x: L+iw+6, y: yp(v)+4}); t.textContent = "$" + short(v); svg.append(t); });
  }
  const step = Math.max(1, Math.ceil(days.length / Math.max(2, Math.floor(iw / 80))));
  days.forEach((k, i) => { if (i % step) return; const t = svgEl("text", {x: L + i*bw + bw/2, y: H - 2, "text-anchor": "middle"}); t.textContent = k.slice(5); svg.append(t); });
  box.append(svg);
  if (!prices.length) box.append(el("p", {className: "muted", textContent: "BTC price appears after the first scheduled run."}));
}

/* ---------- content mix ---------- */
function mix(posts) {
  const box = $("mix"); box.replaceChildren();
  if (!posts.length) { box.append(el("p", {className: "empty", textContent: "No posts yet."})); return; }
  const g = {}; posts.forEach(p => { (g[p.category] = g[p.category] || []).push(+p.views || 0); });
  const rows = Object.entries(g).map(([c, v]) => ({c, n: v.length, avg: v.reduce((a,b)=>a+b,0)/v.length})).sort((a,b) => b.avg - a.avg);
  const W = box.clientWidth || 500, bh = 22, gap = 9, H = rows.length * (bh + gap);
  const svg = svgEl("svg", {viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Average views by post type"});
  const labels = rows.map(r => `${LABELS[r.c] || r.c} (${r.n})`);
  const probe = svgEl("text", {}); svg.append(probe); box.append(svg);
  let lw = 0; labels.forEach(s => { probe.textContent = s; lw = Math.max(lw, probe.getComputedTextLength()); }); probe.remove();
  const L = Math.min(lw + 10, W * 0.55), R = 48, max = rows[0].avg;
  rows.forEach((r, i) => {
    const yy = i * (bh + gap), w = Math.max(2, r.avg / max * (W - L - R));
    const t = svgEl("text", {x: 0, y: yy + bh/2 + 4}); t.textContent = labels[i]; svg.append(t);
    const bar = svgEl("rect", {x: L, y: yy, width: w, height: bh, rx: 3, fill: i === 0 ? "var(--bar-hi)" : "var(--bar)"});
    bar.addEventListener("pointermove", ev => showTip(ev, `${LABELS[r.c] || r.c}: ${r.n} posts, ${fmt(Math.round(r.avg))} average views`));
    bar.addEventListener("pointerleave", hideTip); svg.append(bar);
    const v = svgEl("text", {x: L + w + 6, y: yy + bh/2 + 4}); v.textContent = short(r.avg); svg.append(v);
  });
}

function feed(posts) {
  const ul = $("feed"); ul.replaceChildren();
  const items = posts.filter(p => ALERT.includes(p.category)).slice(-15).reverse();
  if (!items.length) { ul.append(el("li", {className: "empty", textContent: "No downtime, maintenance or BTC posts in the tracked period."})); return; }
  items.forEach(p => {
    const text = (p.text || "").slice(0, 140) + ((p.text || "").length > 140 ? "…" : "");
    const a = p.link ? el("a", {href: p.link, target: "_blank", rel: "noopener", textContent: text}) : el("span", {textContent: text});
    ul.append(el("li", {}, el("span", {className: "pill " + p.category, textContent: LABELS[p.category]}), a, el("small", {textContent: `${day(p.date)}, ${fmt(p.views)} views`})));
  });
}

function groups(id) {
  const box = $("groups"); box.replaceChildren();
  const g = S.groups[id];
  if (!g || !Object.keys(g).length) {
    box.append(el("p", {className: "empty", textContent: "Not connected yet. Add TG_API_ID, TG_API_HASH and TG_SESSION as GitHub secrets (see README) to count messages and complaints in the community groups."}));
    return;
  }
  const t = el("table", {className: "table"});
  t.append(el("thead", {}, el("tr", {}, ...["Group", "Days", "Messages", "Complaint mentions", "Complaint share", "Withdrawal mentions", "Busiest day"].map(h => el("th", {textContent: h})))));
  const tb = el("tbody");
  Object.entries(g).forEach(([handle, rows]) => {
    const sum = k => rows.reduce((a, r) => a + (r[k] || 0), 0);
    const msgs = sum("messages"), comp = sum("complaint");
    const busy = rows.reduce((a, r) => (r.messages || 0) > (a.messages || 0) ? r : a, {});
    tb.append(el("tr", {}, ...[ "@" + handle, rows.length, fmt(msgs), fmt(comp), msgs ? Math.round(comp / msgs * 100) + "%" : "—", fmt(sum("withdrawal")), busy.date ? `${busy.date} (${fmt(busy.messages)})` : "—"]
      .map((v, i) => el("td", {className: i ? "num" : "", textContent: String(v)}))));
  });
  t.append(tb); box.append(el("div", {className: "scroll"}, t));
}

function events(rows) {
  const sel = $("evt"), ol = $("timeline");
  const names = [...new Set(rows.map(r => r.event))];
  sel.replaceChildren(...names.map(n => new Option(n, n)));
  if (!names.includes(S.evt)) S.evt = names[0] || null;
  sel.value = S.evt || ""; sel.disabled = !names.length;
  sel.onchange = () => { S.evt = sel.value; events(rows); };
  ol.replaceChildren();
  if (!names.length) { ol.append(el("li", {className: "empty", textContent: "No downtime timelines researched yet. Add rows to events.json."})); return; }
  rows.filter(r => r.event === S.evt).sort((a, b) => a.step - b.step).forEach(r => {
    const li = el("li", {className: "k-" + String(r.kind).toLowerCase().split(" ")[0]});
    li.append(el("div", {className: "when", textContent: `${r.date}, ${r.time_utc} UTC, ${r.kind}`}), el("div", {className: "what", textContent: r.what}));
    if (r.binance_message && r.binance_message !== "—") li.append(el("p", {className: "said", textContent: "They said: " + r.binance_message}));
    ol.append(li);
  });
}

function dots(s, status) {
  if (status === "To verify" || !+s) return el("td", {className: "pend", textContent: "Pending"});
  const td = el("td", {className: "dots", textContent: "●".repeat(s) + "○".repeat(5 - s)}); td.setAttribute("aria-label", `${s} out of 5`); return td;
}
function score(rows) {
  const tb = $("score").tBodies[0]; tb.replaceChildren();
  if (!rows.length) { tb.append(el("tr", {}, el("td", {colSpan: 3, className: "empty", textContent: "Not rated yet."}))); return; }
  rows.forEach(r => tb.append(el("tr", {}, el("td", {textContent: r.dimension}), dots(r.score, r.status), el("td", {textContent: r.evidence}))));
}
function voices(rows) {
  const box = $("voices"); box.replaceChildren();
  if (!rows.length) { box.append(el("p", {className: "empty", textContent: "No customer reactions collected yet."})); return; }
  rows.forEach(r => box.append(el("div", {className: "voice"},
    el("div", {className: "tone " + (/neg|angry/i.test(r.tone) ? "neg" : "mid"), textContent: `${r.theme}: ${r.tone}`}),
    el("p", {textContent: r.what_customers_said}), el("small", {textContent: r.source}))));
}
function lessons(rows) {
  [["copy", "Copy"], ["avoid", "Avoid"]].forEach(([id, kind]) => {
    const ul = $(id); ul.replaceChildren();
    const list = rows.filter(r => r.type === kind);
    if (!list.length) ul.append(el("li", {className: "muted", textContent: "Nothing yet."}));
    list.forEach(r => ul.append(el("li", {}, el("b", {textContent: r.practice}), document.createTextNode(". " + r.detail))));
  });
}


/* ---------- incidents ---------- */
const hm = (m) => m == null ? "—" : m < 0 ? "before customers" : m < 90 ? `${m} min` : `${(m/60).toFixed(m < 600 ? 1 : 0)} h`;
const t = (iso) => iso ? iso.replace("T", " ").replace("Z", "") : "—";
function incidents(rows) {
  const sel = $("inc-sel"), body = $("inc-body");
  sel.replaceChildren(...rows.map(r => new Option(`${t(r.customers_noticed_at).slice(0,10)}  ${r.title}`.slice(0, 90), r.id)));
  if (!rows.some(r => r.id === S.inc)) S.inc = rows[0] ? rows[0].id : null;
  sel.value = S.inc || ""; sel.disabled = !rows.length;
  sel.onchange = () => { S.inc = sel.value; incidents(rows); };
  body.replaceChildren();
  if (!rows.length) {
    body.append(el("p", {className: "empty", textContent: "No incidents captured yet. They appear automatically when the announcement channel posts about downtime or complaints spike in a group (needs the Telegram secrets). For a past incident, export the group chat from Telegram Desktop and run scraper/import_export.py (see README)."}));
    return;
  }
  const r = rows.find(x => x.id === S.inc);
  const cls = (m, lim) => m == null ? "" : m > lim ? "late" : "ok";
  body.append(el("div", {className: "inc-stats"},
    ...[[t(r.customers_noticed_at), "Customers started complaining", ""],
        [hm(r.minutes_customers_before_official), "until first official post", cls(r.minutes_customers_before_official, 30)],
        [hm(r.minutes_to_first_admin_reply), "until first admin reply in group", cls(r.minutes_to_first_admin_reply, 15)],
        [r.minutes_to_solved != null ? hm(r.minutes_to_solved) : (r.status === "ongoing" ? "Ongoing" : "Not confirmed"), "until solved", ""],
        [fmt(r.peak_complaints_per_hour), "complaints in the worst hour", ""]]
    .map(([v, l, c]) => el("div", {className: c}, el("b", {textContent: v}), el("span", {textContent: l})))));
  const lg = Object.entries(r.languages || {});
  if (lg.length) { const tot = lg.reduce((a, x) => a + x[1], 0); body.append(el("p", {className: "muted", style: "margin:0 0 8px;font-size:13px", textContent: "Customer languages: " + lg.map(([k, v]) => `${k} ${Math.round(v / tot * 100)}%`).join(", ")})); }
  if (S.pb) body.append(el("h4", {textContent: "Checked against the playbook", style: "margin:4px 0 0"}), checkList(playbookCheck(r)));
  body.append(el("div", {className: "chart", id: "inc-chart"}));
  body.append(el("div", {className: "legend"},
    ...[["var(--bar)", "customer messages per hour"], ["var(--down)", "complaints"], ["var(--signal)", "admin replies"], ["var(--btc)", "official post"], ["var(--up)", "solved"]]
    .map(([c, l]) => el("span", {}, el("i", {style: `background:${c}`}), l))));

  const left = el("div"), right = el("div");
  left.append(el("h4", {textContent: "What customers talked about"}));
  const th = Object.entries(r.themes || {}); const max = Math.max(1, ...th.map(x => x[1]));
  const tl = el("div");
  th.forEach(([k, v]) => tl.append(el("div", {style: "display:grid;grid-template-columns:minmax(120px,40%) 1fr auto;gap:8px;align-items:center;margin:4px 0;font-size:14px"},
    el("span", {textContent: k}), el("span", {style: `height:12px;border-radius:3px;width:${Math.max(3, v / max * 100)}%;background:${/Thanks/.test(k) ? "var(--up)" : "var(--down)"}`}), el("span", {className: "muted", textContent: fmt(v)}))));
  if (!th.length) tl.append(el("p", {className: "muted", textContent: "No themed messages in this window."}));
  left.append(tl, el("h4", {textContent: "What customers said (anonymised)", style: "margin-top:14px"}));
  Object.entries(r.samples || {}).forEach(([k, arr]) => arr.slice(0, 2).forEach(s => left.append(el("div", {className: "quote" + (/Thanks/.test(k) ? " good" : "")}, el("div", {textContent: s.text}), el("small", {textContent: `${k}, ${t(s.at)} UTC`})))));

  right.append(el("h4", {textContent: "How admins handled it"}));
  const ul = el("ul", {className: "adm"});
  (r.admin_messages || []).forEach(a => ul.append(el("li", {}, el("span", {className: "ph " + a.phase.split(" ")[0], textContent: a.phase}), el("small", {textContent: t(a.at) + " UTC"}), el("div", {textContent: a.text}))));
  if (!(r.admin_messages || []).length) ul.append(el("li", {className: "muted", textContent: "No admin replies found in the group during this window."}));
  right.append(ul);
  body.append(el("div", {className: "inc-cols"}, left, right));

  const sv = el("div", {className: "solved"}, el("h4", {textContent: "How it was solved"}));
  if (r.first_official_post) sv.append(el("p", {}, el("b", {textContent: "First official post: "}), document.createTextNode(`${t(r.first_official_post.at)} UTC. ${r.first_official_post.text}`)));
  if (r.resolution_post) sv.append(el("p", {}, el("b", {textContent: "Resolution post: "}), document.createTextNode(`${t(r.resolution_post.at)} UTC. ${r.resolution_post.text}`)));
  if (r.complaints_settled_at) sv.append(el("p", {}, el("b", {textContent: "Complaints back to normal: "}), document.createTextNode(t(r.complaints_settled_at) + " UTC")));
  if (sv.childNodes.length === 1) sv.append(el("p", {className: "muted", textContent: "No resolution post or calm-down found yet in this window."}));
  body.append(sv);
  incChart();
}
function incChart() {
  const box = $("inc-chart"); if (!box) return;
  const rows = (S.data[S.current] || {}).incidents || []; const r = rows.find(x => x.id === S.inc); box.replaceChildren();
  if (!r || !(r.hours || []).length) { box.append(el("p", {className: "empty", textContent: "No hourly data."})); return; }
  const H = r.hours, W = box.clientWidth || 700, h = 200, L = 34, R = 10, T = 14, B = 24, iw = W - L - R, ih = h - T - B, bw = iw / H.length;
  const max = Math.max(1, ...H.map(x => x.messages));
  const y = v => T + ih - v / max * ih;
  const svg = svgEl("svg", {viewBox: `0 0 ${W} ${h}`, role: "img", "aria-label": "Customer messages, complaints and admin replies per hour during the incident"});
  [0, max].forEach(v => { const tx = svgEl("text", {x: L - 6, y: y(v) + 4, "text-anchor": "end"}); tx.textContent = short(v); svg.append(tx); });
  const x0 = new Date(H[0].hour).getTime();
  const xAt = (iso) => L + (new Date(iso).getTime() - x0) / 36e5 * bw;
  H.forEach((d, i) => {
    const x = L + i * bw;
    svg.append(svgEl("rect", {x: x + bw * .1, y: y(d.messages), width: Math.max(1, bw * .8), height: T + ih - y(d.messages), fill: "var(--bar)"}));
    svg.append(svgEl("rect", {x: x + bw * .1, y: y(d.complaints), width: Math.max(1, bw * .8), height: T + ih - y(d.complaints), fill: "var(--down)"}));
    if (d.admin) svg.append(svgEl("circle", {cx: x + bw / 2, cy: T - 6, r: Math.min(6, 2 + d.admin), fill: "var(--signal)"}));
    const hit = svgEl("rect", {x, y: 0, width: bw, height: h, fill: "transparent"});
    hit.addEventListener("pointermove", ev => showTip(ev, `${t(d.hour)} UTC: ${fmt(d.messages)} customer messages, ${fmt(d.complaints)} complaints, ${d.admin} admin replies`));
    hit.addEventListener("pointerleave", hideTip); svg.append(hit);
  });
  [[r.first_official_post && r.first_official_post.at, "var(--btc)"], [r.solved_at, "var(--up)"]].forEach(([iso, c]) => {
    if (!iso) return; const x = xAt(iso); if (x < L || x > L + iw) return;
    svg.append(svgEl("line", {x1: x, x2: x, y1: T, y2: T + ih, stroke: c, "stroke-width": 2, "stroke-dasharray": "4 3", "pointer-events": "none"}));
  });
  const step = Math.max(1, Math.ceil(H.length / Math.max(2, Math.floor(iw / 70))));
  H.forEach((d, i) => { if (i % step) return; const tx = svgEl("text", {x: L + i * bw + bw / 2, y: h - 4, "text-anchor": "middle"}); tx.textContent = d.hour.slice(5, 13).replace("T", " ") + "h"; svg.append(tx); });
  box.append(svg);
}




/* ---------- X posts added by hand ---------- */
function xManual(ex, rows) {
  const box = $("x-manual"); box.replaceChildren();
  box.append(el("h4", {textContent: "Added by hand from X", style: "margin:18px 0 4px"}));
  if (!rows.length) {
    box.append(el("p", {className: "muted", style: "font-size:13px;margin:0", textContent: `Free option: during an outage, copy replies from ${ex.name}'s X posts into a Google Sheet (exchange, date, who, text, link, incident), download it as CSV and upload it to data/manual/ in GitHub. See data/manual/TEMPLATE_x_posts.csv.`}));
    return;
  }
  if (!rows.some(r => r.incident === S.msel[ex.id])) S.msel[ex.id] = rows[0].incident;
  const sel = el("select", {"aria-label": "Manually added incident"}, ...rows.map(r => new Option(`${day(r.from)} ${r.incident}`, r.incident)));
  sel.value = S.msel[ex.id]; sel.onchange = () => { S.msel[ex.id] = sel.value; xManual(ex, rows); };
  box.append(el("label", {className: "select-wrap", style: "margin-bottom:8px"}, "Incident ", sel));
  const r = rows.find(x => x.incident === S.msel[ex.id]);
  const m = r.minutes_to_first_exchange_reply;
  box.append(el("div", {className: "inc-stats"}, ...[[fmt(r.customer_posts), "customer posts copied"], [fmt(r.exchange_posts), "posts from the exchange"],
    [r.exchange_posted_first ? "Exchange" : m != null ? hm(m) : "No reply", r.exchange_posted_first ? "posted before customers complained" : "until the exchange replied"]]
    .map(([a, b]) => el("div", {}, el("b", {textContent: a}), el("span", {textContent: b})))));
  const phases = new Set((r.exchange_posts_text || []).flatMap(p => p.phases || [p.phase]));
  box.append(checkList([
    {label: "Exchange responded on X", value: r.exchange_posted_first ? "Before complaints" : m != null ? hm(m) : "No", st: r.exchange_posted_first ? "pass" : m == null ? "fail" : m <= 30 ? "pass" : m <= 60 ? "warn" : "fail"},
    {label: "Reassured on fund safety", value: phases.has("Reassurance") ? "Yes" : "No", st: phases.has("Reassurance") ? "pass" : "fail"},
    {label: "Gave an ETA or next-update time", value: phases.has("ETA / next update") ? "Yes" : "No", st: phases.has("ETA / next update") ? "pass" : "fail"},
    {label: "Posted that it was resolved", value: phases.has("Resolved") ? "Yes" : "No", st: phases.has("Resolved") ? "pass" : "warn"},
  ]));
  const lg = Object.entries(r.languages || {}); const tot = lg.reduce((a, x) => a + x[1], 0);
  if (lg.length) box.append(el("p", {className: "muted", style: "margin:8px 0;font-size:13px", textContent: "Languages: " + lg.map(([k, v]) => `${k} ${Math.round(v / tot * 100)}%`).join(", ")}));
  const cols = el("div", {className: "inc-cols"}); const left = el("div"), right = el("div");
  left.append(el("h4", {textContent: "What customers said"}));
  const th = Object.entries(r.themes || {}); const mx = Math.max(1, ...th.map(x => x[1]));
  th.forEach(([k, v]) => left.append(el("div", {style: "display:grid;grid-template-columns:minmax(120px,45%) 1fr auto;gap:8px;align-items:center;margin:4px 0;font-size:14px"},
    el("span", {textContent: k}), el("span", {style: `height:12px;border-radius:3px;width:${Math.max(3, v / mx * 100)}%;background:${/Thanks/.test(k) ? "var(--up)" : "var(--down)"}`}), el("span", {className: "muted", textContent: fmt(v)}))));
  const shownTxt = new Set();
  Object.entries(r.samples || {}).forEach(([k, arr]) => arr.filter(x => !shownTxt.has(x.text)).slice(0, 1).forEach(x => { shownTxt.add(x.text); left.append(el("div", {className: "quote" + (/Thanks/.test(k) ? " good" : "")}, el("div", {textContent: x.text}), el("small", {textContent: `${k}, ${t(x.at)} UTC`}))); }));
  right.append(el("h4", {textContent: "What the exchange posted"}));
  const ul = el("ul", {className: "adm"});
  (r.exchange_posts_text || []).forEach(a => ul.append(el("li", {}, el("span", {className: "ph " + a.phase.split(" ")[0], textContent: a.phase}), el("small", {textContent: t(a.at) + " UTC"}),
    el("div", {}, document.createTextNode(a.text + " "), ...(a.link ? [el("a", {href: a.link, target: "_blank", rel: "noopener", textContent: "Open"})] : [])))));
  if (!(r.exchange_posts_text || []).length) ul.append(el("li", {className: "muted", textContent: "No exchange posts were copied for this incident."}));
  right.append(ul); cols.append(left, right); box.append(cols);
}


/* ---------- discord announcements ---------- */
function discordSec(ex, rows) {
  const sec = $("discordsec");
  const connected = (ex.discord || []).some(c => /^\d+$/.test(String(c.channel_id || "")));
  sec.hidden = !connected && !rows.length;
  if (sec.hidden) return;
  const kp = $("dc-kpis"), ul = $("dc-feed");
  if (!rows.length) {
    kp.replaceChildren(); $("dc-note").textContent = ex.discord_note || "Posts from the exchange's Discord announcement channel.";
    ul.replaceChildren(el("li", {className: "empty", textContent: (ex.discord || []).length ? "No messages yet. They arrive with the next 'Update Telegram data' run (needs the DISCORD_BOT_TOKEN secret)." : "Not connected yet. Follow the exchange's Discord announcement channel into your own server, then add that channel id under \"discord\" in data/exchanges.json (see README)."}));
    return;
  }
  const down = rows.filter(p => p.category === "incident" || p.category === "maintenance");
  kp.replaceChildren(...[[fmt(rows.length), `posts since ${day(rows[0].date)}`], [String(down.length), "downtime or maintenance posts"],
    [Math.round(rows.filter(p => PROMO.includes(p.category)).length / rows.length * 100) + "%", "promos, campaigns, games"],
    [fmt(rows.filter(p => p.btc || p.category === "market").length), "BTC or market posts"]]
    .map(([a, b]) => el("div", {className: "kpi"}, el("b", {textContent: a}), el("span", {textContent: b}))));
  const items = [...rows].reverse().filter(p => ALERT.includes(p.category)).slice(0, 10);
  const latest = [...rows].reverse().slice(0, 5);
  const show = items.length ? items : latest;
  ul.replaceChildren(...show.map(p => el("li", {}, el("span", {className: "pill " + p.category, textContent: LABELS[p.category] || p.category}),
    el("a", {href: p.link, target: "_blank", rel: "noopener", textContent: (p.text || "").slice(0, 160)}),
    el("small", {textContent: `${day(p.date)}, ${p.channel}${p.reactions ? `, ${fmt(p.reactions)} reactions` : ""}`}))));
}

/* ---------- status pages ---------- */
function statusSec(ex, rows) {
  const sec = $("statussec");
  sec.hidden = !ex.status_page;
  if (!ex.status_page) return;
  $("st-note").textContent = `From ${ex.status_page.replace("https://", "")}, the exchange's public status page. Each incident shows its updates from Investigating to Resolved.`;
  const sel = $("st-sel"), kp = $("st-kpis"), body = $("st-body");
  if (!rows.length) { sel.replaceChildren(); kp.replaceChildren(); body.replaceChildren(el("p", {className: "empty", textContent: "No status page data yet. It arrives with the next 'Update Telegram data' run."})); return; }
  const med = a => { a = a.filter(v => v != null).sort((p, q) => p - q); return a.length ? a[Math.floor(a.length / 2)] : null; };
  const pct = f => Math.round(rows.filter(f).length / rows.length * 100) + "%";
  kp.replaceChildren(...[
    [fmt(rows.length), `incidents since ${day(rows[rows.length - 1].started_at)}`], [hm(med(rows.map(r => r.minutes_to_resolve))), "median time to resolve"],
    [hm(med(rows.map(r => r.longest_gap_min))), "median longest silence between updates"], [pct(r => r.gave_eta), "gave an ETA or next-update time"],
    [pct(r => r.minutes_to_identified != null && r.minutes_to_identified <= 60), "identified the cause within an hour"],
  ].map(([a, b]) => el("div", {className: "kpi"}, el("b", {textContent: a}), el("span", {textContent: b}))));
  if (!rows.some(r => r.id === S.stsel[ex.id])) S.stsel[ex.id] = rows[0].id;
  sel.replaceChildren(...rows.map(r => new Option(`${day(r.started_at)} ${r.title}`.slice(0, 80), r.id))); sel.value = S.stsel[ex.id];
  sel.onchange = () => { S.stsel[ex.id] = sel.value; statusSec(ex, rows); };
  const r = rows.find(x => x.id === S.stsel[ex.id]);
  body.replaceChildren(
    el("p", {style: "margin:0"}, el("b", {textContent: r.title}), document.createTextNode(`. Impact: ${r.impact || "none"}. ${r.components.length ? "Affected: " + r.components.join(", ") + "." : ""} `),
      ...(r.link ? [el("a", {href: r.link, target: "_blank", rel: "noopener", textContent: "Open on status page"})] : [])),
    checkList([
      {label: "Resolved in", value: r.minutes_to_resolve != null ? hm(r.minutes_to_resolve) : "Not yet", st: r.minutes_to_resolve != null ? "pass" : "warn"},
      {label: "Cause identified after", value: r.minutes_to_identified != null ? hm(r.minutes_to_identified) : "Never stated", st: r.minutes_to_identified == null ? "fail" : r.minutes_to_identified <= 60 ? "pass" : "warn"},
      {label: "Longest silence between updates", value: r.longest_gap_min != null ? hm(r.longest_gap_min) : "Only one update", st: r.longest_gap_min == null ? "warn" : r.longest_gap_min <= 30 ? "pass" : r.longest_gap_min <= 60 ? "warn" : "fail"},
      {label: "Gave an ETA or next-update time", value: r.gave_eta ? "Yes" : "No", st: r.gave_eta ? "pass" : "fail"},
      {label: "Said funds are safe", value: r.said_funds_safe ? "Yes" : "No", st: r.said_funds_safe ? "pass" : "na"},
      {label: "Number of updates", value: String(r.updates), st: r.updates >= 3 ? "pass" : "warn"},
    ]),
    el("ol", {className: "stl"}, ...r.timeline.map(u => el("li", {className: u.status}, el("div", {className: "when"}, el("b", {textContent: u.status}), document.createTextNode(`, ${t(u.at)} UTC`)), el("div", {textContent: u.text})))));
}

/* ---------- X (Twitter) ---------- */
function xsection(xp, xi, ex) {
  const n = xp.length, avg = k => n ? xp.reduce((a, p) => a + (+p[k] || 0), 0) / n : 0;
  const down = xp.filter(p => p.category === "incident" || p.category === "maintenance").length;
  const accts = (ex.x || []).map(a => "@" + a.handle).join(", ");
  $("x-kpis").replaceChildren(...[
    [n ? fmt(n) : "—", "X posts tracked" + (accts ? ` (${accts})` : "")], [n ? short(avg("views")) : "—", "average views"],
    [n ? short(avg("likes")) : "—", "average likes"], [n ? short(avg("replies")) : "—", "average replies"], [n ? String(down) : "—", "downtime or maintenance posts"],
  ].map(([v, l]) => el("div", {className: "kpi"}, el("b", {textContent: v}), el("span", {textContent: l}))));
  const ul = $("x-feed"); ul.replaceChildren();
  const items = xp.filter(p => ALERT.includes(p.category)).slice(-12).reverse();
  if (!items.length) ul.append(el("li", {className: "empty", textContent: n ? "No downtime, maintenance or BTC posts yet." : (ex.x && ex.x.length ? "No X data yet. Add the X_BEARER_TOKEN secret and run the 'Update X data' workflow." : "No X accounts configured for this exchange.")}));
  items.forEach(p => ul.append(el("li", {}, el("span", {className: "pill " + p.category, textContent: LABELS[p.category]}),
    el("a", {href: p.link, target: "_blank", rel: "noopener", textContent: (p.text || "").slice(0, 140)}),
    el("small", {textContent: `${day(p.date)}, @${p.account}, ${short(p.views || 0)} views, ${fmt(p.likes)} likes, ${fmt(p.replies)} replies`}))));

  const sel = $("x-sel"), body = $("x-body");
  sel.replaceChildren(...xi.map(r => new Option(`${day(r.date)} ${r.text}`.slice(0, 60), r.post_id)));
  if (!xi.some(r => r.post_id === S.xsel)) S.xsel = xi[0] ? xi[0].post_id : null;
  sel.value = S.xsel || ""; sel.hidden = !xi.length;
  sel.onchange = () => { S.xsel = sel.value; xsection(xp, xi, ex); };
  body.replaceChildren();
  if (!xi.length) { body.append(el("p", {className: "empty", textContent: "No downtime posts with replies in the last 7 days. X only allows searching replies from the past week, so these build up from now on."})); return; }
  const r = xi.find(x => x.post_id === S.xsel);
  body.append(el("div", {className: "inc-stats"}, ...[
    [fmt(r.customer_replies), "customer replies read"], [fmt(r.exchange_replies), "replies from the exchange"],
    [r.minutes_to_first_exchange_reply != null ? hm(r.minutes_to_first_exchange_reply) : "None", "until the exchange first replied"],
  ].map(([v, l]) => el("div", {}, el("b", {textContent: v}), el("span", {textContent: l})))));
  if (S.pb) body.append(checkList([{label: "Exchange replied under its post", value: r.minutes_to_first_exchange_reply != null ? hm(r.minutes_to_first_exchange_reply) : "No reply", st: r.minutes_to_first_exchange_reply == null ? "fail" : grade("minutes_to_first_exchange_reply", r.minutes_to_first_exchange_reply)}]));
  const lg = Object.entries(r.languages || {}); const tot = lg.reduce((a, x) => a + x[1], 0);
  if (lg.length) body.append(el("p", {className: "muted", style: "margin:0 0 8px;font-size:13px", textContent: "Reply languages: " + lg.map(([k, v]) => `${k} ${Math.round(v / tot * 100)}%`).join(", ")}));
  const th = Object.entries(r.themes || {}); const mx = Math.max(1, ...th.map(x => x[1]));
  th.forEach(([k, v]) => body.append(el("div", {style: "display:grid;grid-template-columns:minmax(120px,45%) 1fr auto;gap:8px;align-items:center;margin:4px 0;font-size:14px"},
    el("span", {textContent: k}), el("span", {style: `height:12px;border-radius:3px;width:${Math.max(3, v / mx * 100)}%;background:${/Thanks/.test(k) ? "var(--up)" : "var(--down)"}`}), el("span", {className: "muted", textContent: fmt(v)}))));
  Object.entries(r.samples || {}).forEach(([k, arr]) => arr.slice(0, 1).forEach(s => body.append(el("div", {className: "quote" + (/Thanks/.test(k) ? " good" : "")}, el("div", {textContent: s.text}), el("small", {textContent: `${k}, ${t(s.at)} UTC`})))));
  (r.exchange_reply_samples || []).slice(0, 2).forEach(s => body.append(el("div", {className: "quote good"}, el("div", {textContent: s.text}), el("small", {textContent: `Exchange reply, ${t(s.at)} UTC`}))));
  body.append(el("p", {style: "font-size:13px"}, el("a", {href: r.link, target: "_blank", rel: "noopener", textContent: "Open the post on X"})));
}




/* ---------- what customers say (reviews + telegram, KNN + k-means) ---------- */
function voiceSec(ex, v) {
  const kp = $("v-kpis"), ch = $("v-chart"), lb = $("v-labels"), sm = $("v-samples"), tp = $("v-topics"), me = $("v-method");
  if (!v) {
    [kp, ch, lb, sm, tp].forEach(x => x.replaceChildren());
    lb.append(el("p", {className: "empty", textContent: ex.apps ? "Not analysed yet. Run the 'Update app reviews and grouping' workflow." : "No app ids configured for this exchange (add \"apps\" in data/exchanges.json)."}));
    me.textContent = ""; return;
  }
  const top = (v.labels || []).filter(l => !["Praise", "Other"].includes(l.label))[0];
  kp.replaceChildren(...[
    [fmt(v.counts.reviews), "app reviews"], [v.avg_rating != null ? v.avg_rating.toFixed(1) + " ★" : "—", "average rating"],
    [v.low_rating_share != null ? Math.round(v.low_rating_share * 100) + "%" : "—", "1–2 star reviews"],
    [fmt(v.counts.telegram + (v.counts.x || 0)), v.counts.x ? "Telegram + X messages analysed" : "Telegram messages analysed"], [top ? top.label : "—", "top complaint"],
  ].map(([a, b]) => el("div", {className: "kpi"}, el("b", {textContent: a}), el("span", {textContent: b}))));
  // daily chart: 1-2 star reviews and telegram complaints
  ch.replaceChildren();
  const D = v.by_day || [];
  if (D.length) {
    const W = ch.clientWidth || 700, H = 150, L = 30, R = 8, T = 8, B = 22, iw = W - L - R, ih = H - T - B, bw = iw / D.length;
    const mx = Math.max(1, ...D.map(d => Math.max(d.low, d.tg_complaints)));
    const y = val => T + ih - val / mx * ih;
    const svg = svgEl("svg", {viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Daily 1-2 star reviews and Telegram complaints"});
    [0, mx].forEach(val => { const tx = svgEl("text", {x: L - 6, y: y(val) + 4, "text-anchor": "end"}); tx.textContent = val; svg.append(tx); });
    D.forEach((d, i) => {
      const x = L + i * bw, w = Math.max(1, bw * 0.38);
      svg.append(svgEl("rect", {x: x + bw * 0.1, y: y(d.low), width: w, height: T + ih - y(d.low), fill: "var(--down)", rx: 1}));
      svg.append(svgEl("rect", {x: x + bw * 0.1 + w + 1, y: y(d.tg_complaints), width: w, height: T + ih - y(d.tg_complaints), fill: "var(--btc)", rx: 1}));
      const hit = svgEl("rect", {x, y: 0, width: bw, height: H, fill: "transparent"});
      hit.addEventListener("pointermove", ev => showTip(ev, `${d.date}: ${d.low} of ${d.reviews} reviews were 1–2 stars, ${d.tg_complaints} Telegram complaints`));
      hit.addEventListener("pointerleave", hideTip); svg.append(hit);
    });
    const step = Math.max(1, Math.ceil(D.length / Math.max(2, Math.floor(iw / 70))));
    D.forEach((d, i) => { if (i % step) return; const tx = svgEl("text", {x: L + i * bw + bw / 2, y: H - 4, "text-anchor": "middle"}); tx.textContent = d.date.slice(5); svg.append(tx); });
    ch.append(svg, el("div", {className: "legend"}, ...[["var(--down)", "1–2 star reviews per day"], ["var(--btc)", "Telegram complaints per day"]].map(([c, l]) => el("span", {}, el("i", {style: `background:${c}`}), l))));
  }
  // label bars, click to see samples
  const labels = v.labels || []; const mxl = Math.max(1, ...labels.map(l => l.count));
  if (!labels.some(l => l.label === S.vlabel[ex.id])) S.vlabel[ex.id] = (top || labels[0] || {}).label;
  lb.replaceChildren(...labels.map(l => {
    const row = el("div", {className: "vbar", role: "button", tabIndex: 0},
      el("span", {textContent: l.label}), el("span", {className: "b", style: `width:${Math.max(3, l.count / mxl * 100)}%;background:${l.label === "Praise" ? "var(--up)" : l.label === "Other" ? "var(--bar)" : "var(--down)"}`}),
      el("span", {className: "muted", textContent: `${fmt(l.count)}`}));
    row.setAttribute("aria-pressed", String(S.vlabel[ex.id] === l.label));
    row.onclick = row.onkeydown = (e) => { if (e.type === "keydown" && e.key !== "Enter") return; S.vlabel[ex.id] = l.label; voiceSec(ex, v); };
    return row;
  }));
  const cur = labels.find(l => l.label === S.vlabel[ex.id]);
  sm.replaceChildren(...(cur ? [el("h4", {textContent: `Examples: ${cur.label}`, style: "margin-top:14px"}),
    ...cur.samples.map(x => el("div", {className: "quote" + (cur.label === "Praise" ? " good" : "")}, el("div", {textContent: x.text}),
      el("small", {textContent: `${x.src === "review" ? `App review${x.rating ? `, ${x.rating}★` : ""}` : "Telegram"}, ${day(x.at)}`})))] : []));
  // topics
  const T2 = v.topics || [];
  tp.replaceChildren(...(T2.length ? T2.map(x => el("div", {className: "topic"},
    el("h5", {textContent: x.name}),
    el("small", {textContent: `${fmt(x.size)} messages, ${Math.round(x.negative_share * 100)}% negative, mostly ${x.main_label}, from ${Object.entries(x.sources).map(([k, n]) => `${n} ${k === "review" ? "reviews" : "Telegram"}`).join(" + ")}`}),
    ...x.samples.slice(0, 2).map(s2 => el("p", {textContent: "“" + s2 + "”"})))) : [el("p", {className: "empty", textContent: "Needs at least 60 messages in the last 30 days to find topics."})]));
  const m = v.method || {};
  me.textContent = `Tagged by keyword rules: ${fmt(m.keywords || 0)}, by the KNN model: ${fmt(m.knn || 0)}, unsure: ${fmt(m.unsure || 0)}. To teach it, add examples to data/labels.json as {"text": "...", "label": "Withdrawals"}. Updated ${t(v.updated)} UTC.`;
}

/* ---------- community chat ---------- */
const COMPLAINT_T = ["Withdrawals", "Deposits", "Login / account access", "Orders / liquidations", "Fear for funds / trust", "Compensation / refund", "Support complaints"];
async function chat(ex) {
  const groupsList = (ex.channels || []).filter(c => c.type === "group").map(c => c.handle);
  const sel = $("chat-group"), list = $("chat-list"), kp = $("chat-kpis"), fl = $("chat-filter");
  if (!groupsList.length) { sel.replaceChildren(); kp.replaceChildren(); fl.replaceChildren(); list.replaceChildren(el("li", {className: "empty", textContent: "No community groups configured for this exchange."})); return; }
  const g = groupsList.includes(S.chatGroup[ex.id]) ? S.chatGroup[ex.id] : groupsList[0];
  S.chatGroup[ex.id] = g;
  sel.replaceChildren(...groupsList.map(h => new Option("@" + h, h))); sel.value = g;
  sel.onchange = () => { S.chatGroup[ex.id] = sel.value; chat(ex); };
  const key = ex.id + "/" + g;
  if (!(key in S.chat)) { list.replaceChildren(el("li", {className: "empty", textContent: "Loading messages…"})); S.chat[key] = (await getJSON(`data/${ex.id}/chat/${g}.json`)) || []; if (S.current !== ex.id) return; }
  const rows = S.chat[key];
  if (!rows.length) { kp.replaceChildren(); fl.replaceChildren(); list.replaceChildren(el("li", {className: "empty", textContent: "No messages saved yet. They arrive with the next 'Update Telegram data' run (needs the Telegram secrets)."})); return; }
  const cust = rows.filter(r => !r.admin), adm = rows.filter(r => r.admin);
  const comp = cust.filter(r => (r.themes || []).some(t2 => COMPLAINT_T.includes(t2)));
  const byId = Object.fromEntries(rows.map(r => [r.id, r]));
  const waits = adm.map(a => { const q = byId[a.reply_to]; return q && !q.admin ? (new Date(a.at) - new Date(q.at)) / 6e4 : null; }).filter(v => v != null && v >= 0).sort((a, b) => a - b);
  const medWait = waits.length ? Math.round(waits[Math.floor(waits.length / 2)]) : null;
  const answered = new Set(adm.map(a => a.reply_to));
  const compAnswered = comp.filter(c => answered.has(c.id)).length;
  kp.replaceChildren(...[
    [fmt(rows.length), `messages since ${day(rows[0].at)}`], [cust.length ? Math.round(comp.length / cust.length * 100) + "%" : "—", "of customer messages are complaints"],
    [fmt(adm.length), "admin messages"], [comp.length ? Math.round(compAnswered / comp.length * 100) + "%" : "—", "of complaints got a direct admin reply"],
    [medWait != null ? hm(medWait) : "—", "median admin reply time"],
  ].map(([v, l]) => el("div", {className: "kpi"}, el("b", {textContent: v}), el("span", {textContent: l}))));
  const F = {all: ["All", () => true], comp: ["Complaints", r => comp.includes(r)], q: ["Questions", r => !r.admin && /\?|kab|kaise|when|how/i.test(r.text)], adm: ["Admin replies", r => r.admin], local: ["Hindi / Hinglish", r => r.lang === "hi" || r.lang === "hinglish"]};
  fl.replaceChildren(...Object.entries(F).map(([k, [n]]) => { const b = el("button", {type: "button", textContent: n}); b.setAttribute("aria-pressed", String(S.chatFilter === k)); b.onclick = () => { S.chatFilter = k; chat(ex); }; return b; }));
  const shown = rows.filter((F[S.chatFilter] || F.all)[1]).slice(-200).reverse();
  list.replaceChildren(...(shown.length ? shown.map(r => {
    const li = el("li", {className: r.admin ? "adm" : ""}, el("time", {textContent: t(r.at).slice(5, 16) + " UTC"}),
      el("div", {}, ...(r.admin ? [el("div", {className: "who", textContent: "Admin"})] : []), document.createTextNode(r.text)));
    const tags = [...(r.themes || []).map(x => el("span", {className: "tag" + (COMPLAINT_T.includes(x) ? " c" : ""), textContent: x})), ...(r.phase && r.phase !== "Other" ? [el("span", {className: "tag a", textContent: r.phase})] : []),
      ...(r.lang && r.lang !== "en" ? [el("span", {className: "tag", textContent: r.lang === "hinglish" ? "Hinglish" : r.lang})] : []),
      ...(r.reply_to && byId[r.reply_to] ? [el("span", {className: "tag", textContent: "reply"})] : [])];
    if (tags.length) li.append(el("div", {className: "tags"}, ...tags));
    return li;
  }) : [el("li", {className: "empty", textContent: "No messages match this filter."})]));
}


/* ---------- influencers ---------- */
const NEG_EMO = ["👎", "😡", "🤬", "😢", "😱", "💩", "🤮"];
function negShare(posts) {
  let neg = 0, tot = 0;
  posts.forEach(p => Object.entries(p.reaction_detail || {}).forEach(([e, n]) => { tot += n; if (NEG_EMO.some(x => e.includes(x))) neg += n; }));
  return tot ? neg / tot : null;
}
function outageEvents(exs) {
  const ev = [];
  exs.forEach(ex => {
    const d = S.data[ex.id] || {};
    (d.posts || []).filter(p => p.category === "incident").forEach(p => ev.push({ex, at: p.date, title: p.text}));
    (d.status_incidents || []).forEach(r => ev.push({ex, at: r.started_at, title: r.title}));
    (d.incidents || []).forEach(r => ev.push({ex, at: r.customers_noticed_at, title: r.title}));
    (d.manual_incidents || []).forEach(r => ev.push({ex, at: r.from, title: r.incident}));
  });
  return ev.filter(e => e.at).sort((a, b) => b.at.localeCompare(a.at));
}
function influencersView() {
  const rg = S.regions.find(r => r.id === S.region);
  const infl = S.infl.filter(f => (f.region || "global") === S.region);
  const handles = new Set(infl.map(f => f.handle));
  const posts = S.inflPosts.filter(p => handles.has(p.channel));
  $("inf-title").textContent = `Influencers: ${rg ? rg.name : ""}`;
  $("inf-lead").textContent = posts.length
    ? `${fmt(posts.length)} posts from ${infl.length} influencer channels since ${day(posts[0].date)}. ${posts.filter(p => p.referral).length} posts carried a referral link and ${posts.filter(p => (p.mentions || []).length).length} named an exchange.`
    : `${infl.length} influencer channels configured. Posts appear after the next 'Update Telegram data' run.`;
  const ns = negShare(posts);
  $("inf-kpis").replaceChildren(...[[fmt(infl.length), "influencer channels"], [fmt(posts.length), "posts tracked"],
    [posts.length ? short(posts.reduce((a, p) => a + (+p.views || 0), 0) / posts.length) : "—", "average views"],
    [fmt(posts.filter(p => p.referral).length), "posts with a referral link"], [ns != null ? Math.round(ns * 100) + "%" : "—", "negative reactions"]]
    .map(([a, b]) => el("div", {className: "kpi"}, el("b", {textContent: a}), el("span", {textContent: b}))));
  // table
  const exName = id => (S.exchanges.find(e => e.id === id) || {name: id}).name;
  const t = $("inf-table");
  t.replaceChildren(el("thead", {}, el("tr", {}, ...["Influencer", "Linked to", "Subscribers", "Posts", "Avg views", "Avg reactions", "Talks most about", "Referral posts", "Negative reactions"].map(x => el("th", {textContent: x})))));
  const tb = el("tbody");
  infl.forEach(f => {
    const ps = posts.filter(p => p.channel === f.handle), info = S.inflInfo[f.handle] || {};
    const cnt = {}; ps.forEach(p => (p.mentions || []).forEach(m => cnt[m] = (cnt[m] || 0) + 1));
    const top = Object.entries(cnt).sort((a, b) => b[1] - a[1]).slice(0, 3).map(([k, n]) => `${exName(k)} (${n})`).join(", ");
    const n2 = negShare(ps);
    tb.append(el("tr", {}, el("td", {}, el("a", {href: `https://t.me/${f.handle}`, target: "_blank", rel: "noopener", textContent: info.title || f.name || "@" + f.handle})),
      el("td", {textContent: [].concat(f.exchange || []).map(exName).join(", ")}), ...[info.subscribers != null ? fmt(info.subscribers) : "", ps.length ? fmt(ps.length) : "",
      ps.length ? short(ps.reduce((a, p) => a + (+p.views || 0), 0) / ps.length) : "", ps.length ? (ps.reduce((a, p) => a + (+p.reactions || 0), 0) / ps.length).toFixed(1) : ""].map(v => el("td", {className: "num", textContent: v})),
      el("td", {textContent: top || (ps.length ? "No exchange named" : "")}), el("td", {className: "num", textContent: ps.length ? String(ps.filter(p => p.referral).length) : ""}),
      el("td", {className: "num", textContent: n2 != null ? Math.round(n2 * 100) + "%" : ""})));
  });
  if (!infl.length) tb.append(el("tr", {}, el("td", {colSpan: 9, className: "empty", textContent: "No influencers in this region. Add them to data/influencers.json."})));
  t.append(tb);
  // mentions chart
  const box = $("inf-mentions"); box.replaceChildren();
  const cnt = {}, refc = {};
  posts.forEach(p => { (p.mentions || []).forEach(m => cnt[m] = (cnt[m] || 0) + 1); (p.referral_exchanges || []).forEach(m => refc[m] = (refc[m] || 0) + 1); });
  const rows = Object.entries(cnt).sort((a, b) => b[1] - a[1]);
  if (!rows.length) box.append(el("p", {className: "empty", textContent: "No exchange mentions yet."}));
  else { const mx = rows[0][1]; rows.forEach(([k, n]) => box.append(el("div", {className: "vbar", style: "cursor:default"}, el("span", {textContent: exName(k)}),
    el("span", {style: "display:flex;height:12px"}, el("span", {className: "b", style: `width:${(refc[k] || 0) / mx * 100}%;background:var(--btc);border-radius:3px 0 0 3px`}), el("span", {className: "b", style: `width:${(n - (refc[k] || 0)) / mx * 100}%;background:var(--bar);border-radius:0 3px 3px 0`})),
    el("span", {className: "muted", textContent: `${n}${refc[k] ? `, ${refc[k]} referral` : ""}`})))); }
  // outages
  const ul = $("inf-outages"); ul.replaceChildren();
  const ev = outageEvents(inRegion()).slice(0, 30); let shown = 0;
  ev.forEach(e => {
    const t0 = new Date(e.at).getTime();
    const hits = posts.filter(p => { const tp = new Date(p.date).getTime(); return tp >= t0 && tp <= t0 + 48 * 36e5 && ((p.mentions || []).includes(e.ex.id) || /down|outage|withdraw|stuck|issue|problem|hack|band|nahi/i.test(p.text)); });
    if (!hits.length) return; shown++;
    ul.append(el("li", {}, el("span", {className: "pill incident", textContent: e.ex.name}), el("span", {textContent: `${day(e.at)}: ${(e.title || "").slice(0, 90)}`}),
      el("small", {textContent: hits.map(h => `@${h.channel}: “${(h.text || "").slice(0, 80)}” (${fmt(h.views)} views, ${fmt(h.reactions)} reactions)`).join(" · ")})));
  });
  if (!shown) ul.append(el("li", {className: "empty", textContent: ev.length ? "No influencer posted about these outages within 48 hours." : "No outages recorded yet for exchanges in this region."}));
  // latest posts by influencer
  const sel = $("inf-sel");
  sel.replaceChildren(new Option("All influencers", ""), ...infl.map(f => new Option((S.inflInfo[f.handle] || {}).title || f.name || "@" + f.handle, f.handle)));
  sel.value = S.inflSel || ""; sel.onchange = () => { S.inflSel = sel.value; influencersView(); };
  const fe = $("inf-feed");
  const list = posts.filter(p => !S.inflSel || p.channel === S.inflSel).slice(-60).reverse();
  fe.replaceChildren(...(list.length ? list.map(p => {
    const tags = [...(p.mentions || []).map(m => el("span", {className: "ex", textContent: exName(m)})), ...(p.referral ? [el("span", {className: "ref", textContent: "referral link"})] : []),
      ...(ALERT.includes(p.category) ? [el("span", {className: "neg", textContent: LABELS[p.category]})] : []),
      ...Object.entries(p.reaction_detail || {}).sort((a, b) => b[1] - a[1]).slice(0, 4).map(([e2, n]) => el("span", {className: NEG_EMO.some(x => e2.includes(x)) ? "neg" : "", textContent: `${e2} ${n}`}))];
    return el("li", {}, el("span", {className: "pill", textContent: "@" + p.channel}), el("a", {href: p.link, target: "_blank", rel: "noopener", textContent: (p.text || "(media post)").slice(0, 200)}),
      el("small", {textContent: `${day(p.date)}, ${fmt(p.views)} views, ${fmt(p.reactions)} reactions`}), el("div", {className: "tags2"}, ...tags));
  }) : [el("li", {className: "empty", textContent: "No posts yet."})]));
  // discussion groups
  const g = (S.groups || {}).influencers || {}; const gb = $("inf-groups"); gb.replaceChildren();
  const discs = infl.filter(f => f.discussion);
  if (!discs.length) gb.append(el("p", {className: "empty", textContent: "None added yet. Open an influencer's channel in Telegram, tap Comments or Discussion, and add that group's @name as \"discussion\" in data/influencers.json. Your Telegram account must join it."}));
  else discs.forEach(f => { const rows2 = g[f.discussion] || []; const sum = k => rows2.reduce((a, r) => a + (r[k] || 0), 0);
    gb.append(el("p", {}, el("b", {textContent: `@${f.discussion}`}), document.createTextNode(rows2.length ? `: ${fmt(sum("messages"))} messages, ${fmt(sum("complaint"))} complaint mentions, ${fmt(sum("withdrawal"))} withdrawal mentions over ${rows2.length} days.` : ": no data yet."))); });
}

/* ---------- playbook ---------- */
const PB_TARGET = (field) => (S.pb && S.pb.targets || []).find(x => x.field === field);
function grade(field, minutes) {
  const tg = PB_TARGET(field);
  if (minutes == null || !tg) return "na";
  if (minutes <= tg.s1) return "pass";
  if (minutes <= tg.s2) return "warn";
  return "fail";
}
function playbookCheck(r) {
  const adm = (r.admin_messages || []).map(a => ({...a, ms: new Date(a.at).getTime()}));
  const end = new Date(r.solved_at || r.complaints_settled_at || r.window_end).getTime();
  let gap = null;
  if (adm.length) { const pts = [new Date(r.customers_noticed_at).getTime(), ...adm.map(a => a.ms).filter(m => m <= end), end].sort((a, b) => a - b);
    gap = Math.round(Math.max(...pts.slice(1).map((m, i) => m - pts[i])) / 6e4); }
  const has = ph => adm.some(a => a.phase === ph);
  return [
    {label: "First official post", value: hm(r.minutes_customers_before_official), st: grade("minutes_customers_before_official", r.minutes_customers_before_official), rule: "Speak first"},
    {label: "First admin reply in group", value: hm(r.minutes_to_first_admin_reply), st: grade("minutes_to_first_admin_reply", r.minutes_to_first_admin_reply), rule: "Answer complaints"},
    {label: "Longest silence before the fix", value: gap == null ? "no admin posts" : hm(gap), st: gap == null ? "fail" : gap <= 30 ? "pass" : gap <= 60 ? "warn" : "fail", rule: "Keep the update promise"},
    {label: "Reassured on fund safety", value: has("Reassurance") ? "Yes" : "No", st: has("Reassurance") ? "pass" : "fail", rule: "Lead with fund safety"},
    {label: "Warned about scam DMs", value: has("Scam warning") ? "Yes" : "No", st: has("Scam warning") ? "pass" : "warn", rule: "Protect users"},
    {label: "Posted that it was resolved", value: (r.resolution_post || has("Resolved")) ? "Yes" : "No", st: (r.resolution_post || has("Resolved")) ? "pass" : "fail", rule: "Close the loop"},
  ];
}
function checkList(items) {
  const ic = {pass: "✓", warn: "!", fail: "✕", na: "–"};
  return el("ul", {className: "chk"}, ...items.map(c => el("li", {}, el("span", {className: c.st, textContent: ic[c.st]}), el("span", {textContent: `${c.label}: ${c.value}`}))));
}
function copyBtn(text) {
  const b = el("button", {type: "button", textContent: "Copy"});
  b.onclick = () => { (navigator.clipboard ? navigator.clipboard.writeText(text) : Promise.reject()).then(() => { b.textContent = "Copied"; setTimeout(() => b.textContent = "Copy", 1500); }).catch(() => { b.textContent = "Select and copy"; }); };
  return b;
}
function playbook() {
  const P = S.pb; if (!P) return;
  $("pb-timeline").replaceChildren(...P.timeline.map(x => el("div", {className: "step"}, el("div", {className: "when", textContent: x.when}), el("h4", {textContent: x.phase}), el("div", {className: "who", textContent: x.who}), el("p", {textContent: x.do}))));
  const mins = v => v == null ? "—" : v >= 60 ? `${v / 60} h` : `${v} min`;
  $("pb-levels").replaceChildren(el("thead", {}, el("tr", {}, ...["Level", "What it means", "Examples", "First post within", "Update every", "Admin reply within"].map(x => el("th", {textContent: x})))),
    el("tbody", {}, ...P.levels.map(l => el("tr", {}, el("td", {innerHTML: ""}, el("b", {textContent: l.level})), el("td", {textContent: l.means}), el("td", {textContent: l.examples}),
      el("td", {className: "num", textContent: l.note && l.first_post_min == null ? "24 h before" : mins(l.first_post_min)}), el("td", {className: "num", textContent: l.note && l.update_every_min == null ? "Start and end" : (l.update_every_min ? mins(l.update_every_min) : "When fixed")}), el("td", {className: "num", textContent: mins(l.admin_reply_min)})))));
  $("pb-rules").replaceChildren(...P.rules.map(r => el("li", {}, el("b", {textContent: r.rule}), document.createTextNode(r.detail))));
  const seg = $("pb-lang");
  seg.replaceChildren(...[["en", "English"], ["hinglish", "Hinglish"]].map(([k, n]) => { const b = el("button", {type: "button", textContent: n}); b.setAttribute("aria-pressed", String(S.pbLang === k)); b.onclick = () => { S.pbLang = k; playbook(); }; return b; }));
  const L = S.pbLang;
  $("pb-templates").replaceChildren(...P.templates.map(x => el("div", {className: "card"}, el("h4", {textContent: x.phase}), el("p", {textContent: x[L]}), copyBtn(x[L]))));
  $("pb-scripts").replaceChildren(...P.scripts.map(x => el("div", {className: "card"}, el("h4", {textContent: x.q}), el("p", {textContent: x[L]}), ...(x.note ? [el("small", {textContent: x.note})] : []), copyBtn(x[L]))));
  $("pb-donts").replaceChildren(...P.donts.map(d => el("li", {}, el("b", {textContent: d.dont}), document.createTextNode(". " + d.example))));
  $("pb-maint").replaceChildren(...P.maintenance.map(m => el("li", {textContent: m})));
  $("pb-roles").replaceChildren(el("thead", {}, el("tr", {}, ...["Role", "Owns", "Channel"].map(x => el("th", {textContent: x})))),
    el("tbody", {}, ...P.roles.map(r => el("tr", {}, el("td", {}, el("b", {textContent: r.role})), el("td", {textContent: r.owns}), el("td", {textContent: r.channel})))));
  const med = a => { a = a.filter(v => v != null).sort((p, q) => p - q); return a.length ? a[Math.floor(a.length / 2)] : null; };
  const exs = inRegion();
  const tb = $("pb-bench");
  tb.replaceChildren(el("thead", {}, el("tr", {}, el("th", {textContent: "Measure"}), el("th", {textContent: "S1 target"}), el("th", {textContent: "S2 target"}), ...exs.map(e => el("th", {textContent: e.name})))));
  const body = el("tbody");
  P.targets.forEach(tg => {
    const vals = exs.map(e => { const d = S.data[e.id] || {}; const src = tg.field === "minutes_to_first_exchange_reply" ? (d.x_incidents || []) : (d.incidents || []); return med(src.map(r => r[tg.field])); });
    body.append(el("tr", {}, el("td", {textContent: tg.metric}), el("td", {className: "num", textContent: tg.s1 + " min"}), el("td", {className: "num", textContent: tg.s2 + " min"}),
      ...vals.map(v => el("td", {className: "num " + (v == null ? "" : grade(tg.field, v)), textContent: v == null ? "" : hm(v)}))));
  });
  tb.append(body);
}

function compare() {
  const exs = inRegion();
  const rg = S.regions.find(r => r.id === S.region);
  $("cmp-title").textContent = `${rg ? rg.name : ""}: exchanges side by side`;
  const t1 = $("cmp-posts");
  t1.replaceChildren(el("thead", {}, el("tr", {}, ...["Exchange", "Posts tracked", "Avg views", "Promo share", "Downtime posts", "BTC/market posts"].map(h => el("th", {textContent: h})))));
  const b1 = el("tbody");
  exs.forEach(ex => { const s = stats(S.data[ex.id].posts || []);
    b1.append(el("tr", {}, el("td", {textContent: ex.name}), ...[s.n ? fmt(s.n) : "", s.n ? short(s.avg) : "", s.n ? s.promo + "%" : "", s.n ? s.alerts : "", s.n ? s.btc : ""].map(v => el("td", {className: "num", textContent: String(v)})))); });
  t1.append(b1);
  const head = t1.tHead.rows[0]; ["Incidents", "Median min to first admin reply", "Median hours to solved", "Playbook checks passed", "App rating", "1–2 star share", "Status-page incidents", "Median hours to resolve (status page)", "X posts", "X avg views", "X downtime posts"].forEach(x => head.append(el("th", {textContent: x})));
  const med = a => { a = a.filter(v => v != null).sort((p, q) => p - q); return a.length ? a[Math.floor(a.length / 2)] : null; };
  [...b1.rows].forEach((tr, i) => { const incs = S.data[exs[i].id].incidents || [];
    const a = med(incs.map(r => r.minutes_to_first_admin_reply)), s2 = med(incs.map(r => r.minutes_to_solved));
    const xp = S.data[exs[i].id].x_posts || [];
    const xv = xp.length ? short(xp.reduce((a2, p) => a2 + (+p.views || 0), 0) / xp.length) : "";
    const checks = S.pb ? incs.flatMap(r => playbookCheck(r)).filter(c => c.st !== "na") : [];
    const pbs = checks.length ? Math.round(checks.filter(c => c.st === "pass").length / checks.length * 100) + "%" : "";
    const vv = S.data[exs[i].id].voice;
    [incs.length || "", a != null ? a : "", s2 != null ? (s2 / 60).toFixed(1) : "", pbs, vv && vv.avg_rating != null ? vv.avg_rating.toFixed(1) + " ★" : "", vv && vv.low_rating_share != null ? Math.round(vv.low_rating_share * 100) + "%" : "", (S.data[exs[i].id].status_incidents || []).length || "", (() => { const m = med((S.data[exs[i].id].status_incidents || []).map(r => r.minutes_to_resolve)); return m != null ? (m / 60).toFixed(1) : ""; })(), xp.length || "", xv, xp.length ? xp.filter(p => p.category === "incident" || p.category === "maintenance").length : ""].forEach(v => tr.append(el("td", {className: "num", textContent: String(v)}))); });
  const dims = [...new Set(exs.flatMap(ex => (S.data[ex.id].scorecard || []).map(r => r.dimension)))];
  const t2 = $("cmp-score");
  t2.replaceChildren(el("thead", {}, el("tr", {}, el("th", {textContent: "Area"}), ...exs.map(ex => el("th", {textContent: ex.name})))));
  const b2 = el("tbody");
  if (!dims.length) b2.append(el("tr", {}, el("td", {colSpan: exs.length + 1, className: "empty", textContent: "No scorecards yet."})));
  dims.forEach(dm => b2.append(el("tr", {}, el("td", {textContent: dm}), ...exs.map(ex => {
    const r = (S.data[ex.id].scorecard || []).find(x => x.dimension === dm);
    return r ? dots(r.score, r.status) : el("td", {className: "muted", textContent: ""});
  }))));
  t2.append(b2);
}

load();
})();
