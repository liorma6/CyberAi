"use strict";

const $ = id => document.getElementById(id);
const PAGE_SIZE = 6;
const state = {rows: [], byId: new Map(), filter: "all", page: 0, current: null,
  detail: null, baseline: null, view: "trail", event: null, storage: "", notes: {},
  reviews: new Map(), pending: new Set(), errors: new Map(), version: 0};
const decisions = ["Escalate", "Monitor", "Close"];
const label = n => "FILE " + String(n).padStart(3, "0");
const time = iso => new Date(iso).toISOString().slice(11, 19);
const date = iso => new Intl.DateTimeFormat("en-GB", {day: "2-digit", month: "short",
  year: "numeric", timeZone: "UTC"}).format(new Date(iso));
const el = (tag, cls = "", content) => {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (content != null) node.textContent = content;
  return node;
};
function button(text, cls, action) {
  const node = el("button", cls, text);
  node.type = "button";
  node.addEventListener("click", action);
  return node;
}
async function api(path, options) {
  const url = new URL(path, location.origin);
  const dataset = new URLSearchParams(location.search).get("dataset");
  if (dataset) url.searchParams.set("dataset", dataset);
  const resp = await fetch(url, options);
  const body = await resp.json();
  if (!resp.ok) throw new Error(body.error || "Request failed.");
  return body;
}
function announce(text) { $("announce").textContent = text; }
function note() {
  return state.notes[state.current] ??= {pins: [], decision: "", reason: "", filed: false};
}
function persist() {
  try {
    localStorage.setItem(state.storage + state.current, JSON.stringify(note()));
    return true;
  } catch {
    announce("Browser storage is unavailable. Changes last for this session.");
    return false;
  }
}
function readNotes() {
  try {
    for (const id of state.byId.keys()) {
      const item = JSON.parse(localStorage.getItem(state.storage + id) || "null");
      if (item && Array.isArray(item.pins)) {
        state.notes[id] = {pins: [...new Set(item.pins.filter(x => typeof x === "string"))],
          decision: decisions.includes(item.decision) ? item.decision : "",
          reason: typeof item.reason === "string" ? item.reason : "", filed: item.filed === true};
      }
    }
  } catch { announce("Saved assessments could not be loaded."); }
}
function filtered() {
  const query = $("search").value.trim().toLowerCase();
  return state.rows.filter(row => {
    const filed = Boolean(state.notes[row.case_id]?.filed);
    const status = state.filter === "all" || (state.filter === "filed") === filed;
    return status && [label(row.number), row.case_id, row.title, ...row.accounts, ...row.source_ips,
      ...row.rules, ...row.technique_candidates].join(" ").toLowerCase().includes(query);
  });
}
function renderQueue() {
  const items = filtered();
  const pages = Math.ceil(items.length / PAGE_SIZE);
  state.page = Math.max(0, Math.min(state.page, pages - 1));
  const list = $("case-list");
  list.replaceChildren();
  for (const row of items.slice(state.page * PAGE_SIZE, (state.page + 1) * PAGE_SIZE)) {
    const node = button("", "case-item", () => {
      if (state.current !== row.case_id) location.hash = row.case_id;
      setQueue(false);
    });
    node.setAttribute("aria-current", String(state.current === row.case_id));
    const meta = el("span", "queue-meta");
    meta.append(el("span", "", label(row.number)), el("span", state.notes[row.case_id]?.filed ? "filed" : "",
      state.notes[row.case_id]?.filed ? "FILED" : time(row.first_trigger_utc).slice(0, 5) + " UTC"));
    node.append(meta, el("span", "case-title", row.title),
      el("span", "case-sub", row.accounts[0] + (row.accounts.length > 1 ? " +" + (row.accounts.length - 1) : "") + "  /  " + row.source_ips[0]));
    list.append(node);
  }
  if (!items.length) list.append(el("p", "empty", state.filter === "filed" && !$("search").value ? "Filed assessments appear here." : "No cases match this filter."));
  $("page-info").textContent = pages ? (state.page + 1) + " / " + pages : "0 cases";
  $("previous").disabled = state.page === 0;
  $("next").disabled = state.page + 1 >= pages;
  $("total-filed").textContent = Object.values(state.notes).filter(x => x.filed).length;
  for (const node of document.querySelectorAll("[data-filter]")) node.setAttribute("aria-pressed", String(node.dataset.filter === state.filter));
}
function setQueue(open) {
  document.querySelector(".queue").classList.toggle("expanded", open);
  $("queue-toggle").setAttribute("aria-expanded", String(open));
  $("queue-toggle").textContent = open ? "Hide queue" : "Browse cases";
}
function renderHeader() {
  const row = state.byId.get(state.current), data = state.detail;
  const top = el("div", "file-top");
  top.append(el("span", "folio", "DOSSIER  /  " + label(row.number)), el("span", "stamp", note().filed ? "Assessment filed" : "Open case"));
  const info = el("div", "meta");
  info.append(el("strong", "", date(row.first_trigger_utc)), el("span", "", data.accounts.join(", ")),
    el("span", "", data.source_ips.join(", ")), el("span", "", data.trigger_count + (data.trigger_count === 1 ? " trigger" : " triggers")));
  $("case-header").replaceChildren(top, el("h2", "", row.title), info);
}
function showView(view) {
  state.view = view;
  for (const b of document.querySelectorAll("[data-view]")) b.setAttribute("aria-pressed", String(b.dataset.view === view));
  $("pin-count").textContent = note().pins.length ? "(" + note().pins.length + ")" : "";
  if (view === "trail") renderTrail();
  if (view === "brief") renderReview();
  if (view === "assess") renderAssessment();
}
function openSource(id, focus = true) {
  if (!Object.hasOwn(state.detail.sources, id)) return;
  state.event = id;
  showView("trail");
  if (focus) document.querySelector(".source h3").focus();
}
function fileRef(id) {
  const source = state.detail.sources[id];
  return source.file + ":" + source.line;
}
function reference(id) {
  const node = button(fileRef(id), "pinref", () => openSource(id));
  node.title = id;
  return node;
}
function renderSource() {
  const id = state.event, record = state.detail.sources[id];
  const box = el("aside", "source");
  box.setAttribute("aria-label", "Source record");
  const title = el("h3", "", "Original record");
  title.tabIndex = -1;
  const pinned = note().pins.includes(id);
  const pin = button(pinned ? "Unpin evidence" : "Pin evidence", "action", () => {
    const draft = note();
    draft.pins = pinned ? draft.pins.filter(x => x !== id) : [...draft.pins, id];
    persist();
    showView("trail");
    document.querySelector(".source button").focus();
    announce(pinned ? "Evidence unpinned." : "Evidence pinned to the assessment.");
  });
  pin.setAttribute("aria-pressed", String(pinned));
  pin.disabled = note().filed;
  if (pin.disabled) pin.textContent = pinned ? "Filed with assessment" : "Assessment filed";
  box.append(el("div", "source-label", "Source inspector"), title, el("div", "filepath", fileRef(id)),
    el("pre", "", JSON.stringify(record.raw, null, 2)), pin);
  return box;
}
function renderTrail() {
  const data = state.detail;
  const grid = el("div", "trail-grid"), left = el("section"), head = el("div", "section-line");
  head.append(el("h3", "section-heading", "Event timeline"), el("span", "legend", data.timeline.length + " records"));
  const events = el("div", "events");
  const triggers = new Set(data.findings.map(f => f.trigger_id));
  for (const id of data.timeline) {
    const raw = data.sources[id].raw, name = el("span", "event-name");
    name.append(el("span", "", raw.outcome === "success" ? "Sign-in accepted" : "Sign-in failed"));
    if (triggers.has(id)) name.append(el("span", "kind", "TRIGGER"));
    const entry = button("", "event", () => openSource(id));
    entry.setAttribute("aria-pressed", String(id === state.event));
    entry.append(el("span", "dot " + raw.outcome), el("time", "", time(raw.time)), name);
    events.append(entry);
  }
  left.append(head, events);
  const signals = el("div", "signals");
  signals.append(el("h3", "section-heading", "Detection signals"));
  const finding = data.findings.find(f => f.trigger_id === state.event);
  if (finding) {
    for (const hit of finding.rule_hits) {
      const row = el("div", "signal-row");
      row.append(el("b", "", hit.rule), document.createTextNode(data.rule_definitions[hit.rule]));
      signals.append(row);
    }
    const m = finding.model;
    signals.append(el("p", "small", "Isolation Forest scored " + m.score.toFixed(4) + " against a threshold of " + m.threshold.toFixed(4) + "."));
    if (finding.attack_candidates.length) signals.append(el("p", "small", "ATT&CK candidates · " + finding.attack_candidates.map(x => x.technique_id).join(", ")));
  } else {
    signals.append(el("p", "small", "Supporting record. Select a trigger to inspect its detection signals."));
  }
  left.append(signals); grid.append(left, renderSource()); $("panel").replaceChildren(grid);
}
function reviewSection(title) {
  const sec = el("section", "review-section");
  sec.append(el("h4", "", title));
  return sec;
}
async function askLlama() {
  const key = state.current;
  if (state.pending.has(key)) return;
  state.pending.add(key); state.errors.delete(key); renderReview();
  try {
    const result = await api("/api/cases/" + encodeURIComponent(key) + "/briefing", {method: "POST", headers: {"X-EvidenceSOC": "review"}});
    state.reviews.set(key, result);
  } catch (error) { state.errors.set(key, error.message); }
  finally {
    state.pending.delete(key);
    if (state.current === key && state.view === "brief" && state.detail) renderReview();
  }
}
function renderReview() {
  const key = state.current, live = state.reviews.get(key);
  const chosen = live || state.baseline, r = chosen.review;
  const wrap = el("div", "review"), head = el("div", "review-head"), controls = el("div", "review-controls");
  const ask = button(state.pending.has(key) ? "Llama is reviewing…" : live ? "Regenerate briefing" : "Ask local Llama", "action", askLlama);
  ask.disabled = state.pending.has(key);
  if (live) controls.append(button("Use template", "secondary", () => { state.reviews.delete(key); state.errors.delete(key); renderReview(); }));
  controls.append(ask); head.append(el("h3", "section-heading", "Analyst briefing"), controls); wrap.append(head);
  const source = live ? "Local Ollama · " + live.model + " · " + live.metrics.wall_seconds + " s" : "Source · deterministic template";
  wrap.append(el("p", "small", source));
  if (state.errors.has(key)) {const error = el("p", "error", "Llama unavailable. " + state.errors.get(key));error.setAttribute("role","alert");wrap.append(error);}
  const facts = reviewSection("Observed facts");
  for (const fact of r.facts) {
    facts.append(el("p", "", fact.text));
    const details = el("details"), refs = el("div", "ref-list");
    details.append(el("summary", "", fact.event_ids.length + " source records · " + fact.signal));
    for (const id of fact.event_ids) refs.append(reference(id));
    details.append(refs); facts.append(details);
  }
  wrap.append(facts);
  const hyp = reviewSection("Working hypotheses");
  if (!r.hypotheses.length) hyp.append(el("p", "small", "No ATT&CK technique is supported by this selection."));
  for (const h of r.hypotheses) {
    hyp.append(el("p", "", h.technique_id + " · " + h.name + " (candidate)"), el("p", "small", h.reason + " Alternative: " + h.alternative), reference(h.trigger_id));
  }
  wrap.append(hyp);
  for (const [title, items] of [["Missing information",r.missing_information],["Recommended check",r.recommended_checks]]) {
    const sec = reviewSection(title);
    for (const item of items) sec.append(el("p", "", item.text), reference(item.trigger_id));
    wrap.append(sec);
  }
  $("panel").replaceChildren(wrap);
}
function renderAssessment() {
  const draft = note(), wrap = el("div", "assessment"), pins = el("ul", "pins");
  wrap.append(el("h3", "section-heading", draft.filed ? "Filed assessment" : "Analyst assessment"),
    el("p", "secondary-text", "Anchor your decision to a source record. Assessments are saved in this browser."),
    el("h4", "subhead", "Pinned evidence"));
  for (const id of draft.pins) {
    const row = el("li"); row.append(reference(id)); pins.append(row);
  }
  wrap.append(draft.pins.length ? pins : el("p", "small", "Pin a record from the evidence trail to file this case."));
  const form = el("form"), decision = el("select"), reason = el("textarea");
  decision.id = "decision"; decision.required = true;
  for (const text of ["Choose a disposition", ...decisions]) {
    const opt = el("option", "", text); opt.value = decisions.includes(text) ? text : ""; decision.append(opt);
  }
  decision.value = draft.decision; decision.disabled = draft.filed;
  reason.id = "rationale"; reason.value = draft.reason; reason.required = true; reason.readOnly = draft.filed;
  reason.placeholder = "Which observation supports your decision?";
  const dl = el("label", "", "Disposition"), rl = el("label", "", "Reasoning"); dl.htmlFor = decision.id; rl.htmlFor = reason.id;
  const actions = el("div", "form-actions");
  const status = el("span","small");status.setAttribute("role","status");
  const save = el("button", draft.filed ? "secondary" : "action", draft.filed ? "Reopen case" : "File assessment");
  save.type = draft.filed ? "button" : "submit";
  function update() {
    if (draft.filed) return;
    draft.reason = reason.value; draft.decision = decision.value;
    save.disabled = !draft.pins.length || !draft.decision || !draft.reason.trim();
  }
  update();
  const saveDraft = () => {update(); status.textContent = persist() ? "Draft saved" : "Session only";};
  decision.addEventListener("change", saveDraft); reason.addEventListener("input", saveDraft);
  function settle(filed) {
    draft.filed = filed; const saved = persist(); renderQueue(); renderHeader(); showView("assess");
    announce((filed ? "Assessment filed." : "Case reopened.") + (saved ? "" : " Saved for this session only."));
  }
  form.addEventListener("submit", event => {event.preventDefault(); if (!save.disabled && !draft.filed) settle(true);});
  if (draft.filed) save.addEventListener("click", () => settle(false));
  actions.append(save,status); form.append(dl,decision,rl,reason,actions); wrap.append(form);
  if (draft.filed) {
    const review = state.baseline.review;
    const debrief = reviewSection("Case debrief");
    debrief.append(el("p", "small", "Template follow-up for the primary finding"),
      el("p", "", review.recommended_checks[0].text),
      el("p", "small", review.missing_information[0].text), reference(review.primary_trigger_id));
    wrap.append(debrief);
  }
  $("panel").replaceChildren(wrap);
}
async function openCase() {
  const key = location.hash.slice(1) || state.rows[0]?.case_id;
  const version = ++state.version;
  state.current = key; state.detail = null; state.view = "trail";
  $("views").hidden = true; $("panel").replaceChildren();
  const rows = filtered(), index = rows.findIndex(x => x.case_id === key);
  if (index >= 0) state.page = Math.floor(index / PAGE_SIZE);
  renderQueue();
  if (!state.byId.has(key)) {
    $("case-header").replaceChildren(el("p", "empty", state.rows.length ? "Case not found. Choose a file from the queue." : "No cases in this dataset."));
    return;
  }
  $("case-header").replaceChildren(el("p", "loading", "Opening case file…"));
  try {
    const result = await api("/api/cases/" + encodeURIComponent(key));
    if (version !== state.version) return;
    state.detail = result.case; state.baseline = result.baseline;
    state.event = result.baseline.review.primary_trigger_id;
    note().pins = note().pins.filter(id => Object.hasOwn(state.detail.sources, id));
    renderHeader(); $("views").hidden = false; showView("trail");
  } catch (error) {
    if (version !== state.version) return;
    $("case-header").replaceChildren(el("p", "error", error.message), button("Retry case", "secondary", openCase));
  }
}
async function init() {
  try {
    const data = await api("/api/cases");
    state.rows = data.cases; state.byId = new Map(data.cases.map(row => [row.case_id, row]));
    state.storage = "evidencesoc:desk:v1:" + data.provenance.manifest_sha256 + ":";
    readNotes();
    $("total-cases").textContent = data.cases.length; $("total-triggers").textContent = data.trigger_count;
    $("dataset-label").textContent = "Synthetic dataset / seed " + data.provenance.dataset_seed;
    if (data.cases.length) {
      const start = data.cases[0].first_trigger_utc;
      const end = data.cases.reduce((latest, row) => row.last_trigger_utc > latest ? row.last_trigger_utc : latest, start);
      $("shift-period").textContent = date(start) + " — " + date(end) + "  /  UTC";
    } else {
      $("shift-period").textContent = "No recorded triggers";
    }
    await openCase();
  } catch (error) {
    $("case-header").replaceChildren(el("p", "error", "Could not open the casebook. " + error.message), button("Retry", "secondary", init));
  }
}
for (const b of document.querySelectorAll("[data-view]")) b.addEventListener("click", () => showView(b.dataset.view));
for (const b of document.querySelectorAll("[data-filter]")) b.addEventListener("click", () => {state.filter = b.dataset.filter; state.page = 0; renderQueue();});
$("search").addEventListener("input", () => {state.page = 0; renderQueue();});
$("previous").addEventListener("click", () => {state.page--; renderQueue();});
$("next").addEventListener("click", () => {state.page++; renderQueue();});
$("queue-toggle").addEventListener("click", () => setQueue($("queue-toggle").getAttribute("aria-expanded") !== "true"));
window.addEventListener("hashchange", () => {if (state.storage) openCase();});
document.querySelector(".skip").addEventListener("click", event => {event.preventDefault(); $("workspace").focus();});
$("dataset-zip").addEventListener("change", async event => {
  const input = event.target, file = input.files[0];
  if (!file) return;
  input.disabled = true;
  $("import-status").textContent = "Verifying event streams and building the casebook…";
  try {
    const result = await api("/api/import", {method: "POST", headers: {"X-EvidenceSOC": "import"}, body: file});
    const url = new URL("/", location.origin);
    url.searchParams.set("dataset", result.dataset);
    location.assign(url);
  } catch (error) {
    $("import-status").textContent = error.message;
    input.value = "";
    input.disabled = false;
  }
});
init();
