"use strict";

const $ = (s) => document.querySelector(s);
const state = { scan: null, charts: {} };
const SEV = {
  critical: { icon: "◆", label: "Critical" },
  serious: { icon: "▲", label: "Serious" },
  warning: { icon: "●", label: "Warning" },
  info: { icon: "i", label: "Info" },
};
const money = (n) => "$" + Math.abs(n).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 });
const money2 = (n) => "$" + Math.abs(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();

async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  const body = res.headers.get("content-type")?.includes("json") ? await res.json() : await res.text();
  if (!res.ok) throw new Error(body.detail || body || res.statusText);
  return body;
}

// ---------------------------------------------------------------- navigation
async function loadScanList(selectId) {
  const scans = await api("/api/scans");
  const picker = $("#scanPicker");
  picker.innerHTML = scans.length
    ? scans.map((s) => `<option value="${esc(s.id)}">${esc(s.name)} (${s.open_issues} open)</option>`).join("")
    : `<option value="">No scans yet</option>`;
  if (selectId) picker.value = selectId;
  return scans;
}

function showUpload() {
  $("#dashView").classList.add("hidden");
  $("#uploadView").classList.remove("hidden");
}

async function openScan(id) {
  const scan = await api(`/api/scans/${id}`);
  render(scan);
  history.replaceState(null, "", `#${id}`);
}

// ---------------------------------------------------------------- rendering
function render(scan) {
  state.scan = scan;
  $("#uploadView").classList.add("hidden");
  $("#dashView").classList.remove("hidden");
  const s = scan.summary;
  $("#scanName").textContent = scan.name;
  $("#scanMeta").textContent =
    `Data through ${s.as_of} · ${s.counts.bank} bank lines, ${s.counts.ledger} ledger entries, ${s.counts.invoices} invoices`;

  $("#kScore").textContent = `${s.health_score}/100`;
  $("#kScoreSub").textContent = s.health_score >= 85 ? "In good shape" : s.health_score >= 60 ? "Needs attention" : "Needs work soon";
  $("#kOpen").textContent = s.open_issues;
  $("#kSev").innerHTML = `<div class="sev-list">${Object.entries(s.by_severity).filter(([, n]) => n)
    .map(([k, n]) => badge(k, `${n} ${SEV[k].label.toLowerCase()}`)).join("")}</div>`;
  $("#kStake").textContent = money(s.amount_at_stake);
  $("#kDone").textContent = s.approved + s.rejected;
  $("#kDoneSub").textContent = `${s.approved} approved, ${s.rejected} rejected`;

  $("#exportMenu").innerHTML = ["ledger", "bank", "invoices", "audit"]
    .filter((k) => k === "audit" || s.counts[k])
    .map((k) => `<a href="/api/scans/${scan.id}/export/${k}">${k === "audit" ? "Audit log" : k[0].toUpperCase() + k.slice(1)} (CSV)</a>`).join("");

  const fCheck = $("#fCheck"), cur = fCheck.value;
  fCheck.innerHTML = `<option value="">All types</option>` +
    [...new Map(scan.issues.map((i) => [i.check, i])).keys()]
      .map((c) => `<option value="${c}">${esc(labelFor(c))}</option>`).join("");
  fCheck.value = cur;

  renderCharts(s);
  renderIssues();
  renderAudit(scan.audit);
  renderChat(scan.chat);
  $("#llmStatus").textContent = scan.llm.configured
    ? `Powered by ${scan.llm.model}. It sees your scan results, not your login or bank.`
    : "No AI key configured, so answers come from a built-in summary. Add LLM_API_KEY for full conversations.";
}

function labelFor(check) {
  const found = state.scan.summary.by_check.find((b) => b.check === check);
  return found ? found.label : ({ duplicate: "Duplicate entries", uncategorized: "Uncategorized",
    miscategorized: "Inconsistent categories", unreconciled: "Bank vs. books mismatch",
    anomaly: "Unusual amounts", invoice: "Invoice problems" }[check] || check);
}

function badge(sev, text) {
  return `<span class="badge sev-${sev}"><span aria-hidden="true" style="color:var(--sev)">${SEV[sev].icon}</span>${esc(text ?? SEV[sev].label)}</span>`;
}

function renderIssues() {
  const sev = $("#fSeverity").value, chk = $("#fCheck").value, st = $("#fStatus").value;
  const list = state.scan.issues.filter((i) => (!sev || i.severity === sev) && (!chk || i.check === chk) && (!st || i.status === st));
  $("#issues").innerHTML = list.length ? list.map(issueHtml).join("")
    : `<p class="muted">No issues match these filters.${st === "open" && !sev && !chk ? " Nice work!" : ""}</p>`;
}

function issueHtml(i) {
  const decided = i.status !== "open";
  const actions = decided
    ? `<span class="status-${i.status}">${i.status === "approved" ? "✓ Approved" : "✕ Rejected"}</span>`
    : `<div class="row"><button class="btn approve" data-act="approve" data-id="${esc(i.id)}">${i.fix.action === "review" ? "Mark handled" : "Approve fix"}</button>
       <button class="btn" data-act="reject" data-id="${esc(i.id)}">${i.fix.action === "review" ? "Not an issue" : "Reject"}</button>
       <button class="chip" data-act="ask" data-id="${esc(i.id)}">Ask about this</button></div>`;
  return `<article class="issue sev-${i.severity} ${decided ? "done" : ""}">
    <div class="issue-top"><span class="issue-title">${esc(i.title)}</span>
      <span class="row">${badge(i.severity)}<span class="muted small">${esc(labelFor(i.check))}</span></span></div>
    <p>${esc(i.explanation)}</p>
    <div class="fix"><div><div class="fix-label">${i.fix.action === "review" ? "Suggested action" : "Proposed fix"}</div>${esc(i.fix.summary)}</div>${actions}</div>
  </article>`;
}

function renderAudit(audit) {
  $("#auditBody").innerHTML = audit.length
    ? audit.slice().reverse().map((a) => `<tr><td>${esc(a.time.replace("T", " ").replace("+00:00", ""))}</td><td>${esc(a.issue_id)}</td><td>${esc(a.decision)}</td><td>${esc(a.note)}</td></tr>`).join("")
    : `<tr><td colspan="4" class="muted">No decisions yet.</td></tr>`;
}

// ---------------------------------------------------------------- charts
function baseOptions(extra = {}) {
  const text = css("--text-secondary"), grid = css("--grid");
  return {
    responsive: true, maintainAspectRatio: false, animation: false,
    plugins: { legend: { display: false }, tooltip: { intersect: false } },
    scales: {
      x: { grid: { color: grid }, ticks: { color: text }, border: { display: false } },
      y: { grid: { display: false }, ticks: { color: text }, border: { display: false } },
    },
    ...extra,
  };
}

function chart(id, config) {
  if (!window.Chart) return;
  state.charts[id]?.destroy();
  state.charts[id] = new Chart(document.getElementById(id), config);
}

function renderCharts(s) {
  const s1 = css("--series-1"), s2 = css("--series-2"), text = css("--text-secondary"), grid = css("--grid");
  const bar = { borderRadius: 4, borderSkipped: "start", maxBarThickness: 22 };

  const byType = [...s.by_check].sort((a, b) => b.count - a.count);
  chart("byTypeChart", {
    type: "bar",
    data: { labels: byType.map((b) => b.label), datasets: [{ data: byType.map((b) => b.count), backgroundColor: s1, ...bar }] },
    options: baseOptions({
      indexAxis: "y",
      plugins: { legend: { display: false }, tooltip: { callbacks: {
        label: (c) => `${c.raw} open issue(s), ${money2(byType[c.dataIndex].amount)} involved` } } },
    }),
  });

  chart("cashChart", {
    type: "bar",
    data: {
      labels: s.monthly.map((m) => new Date(m.month + "-15").toLocaleString(undefined, { month: "short", year: "numeric" })),
      datasets: [
        { label: "Money in", data: s.monthly.map((m) => m.in), backgroundColor: s1, ...bar },
        { label: "Money out", data: s.monthly.map((m) => m.out), backgroundColor: s2, ...bar },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      interaction: { mode: "index", intersect: false },
      datasets: { bar: { categoryPercentage: 0.7, barPercentage: 0.9 } },
      plugins: {
        legend: { display: true, position: "top", align: "start", labels: { color: text, boxWidth: 10, boxHeight: 10, useBorderRadius: true, borderRadius: 2 } },
        tooltip: { callbacks: {
          label: (c) => `${c.dataset.label}: ${money2(c.raw)}`,
          footer: (items) => { const m = s.monthly[items[0].dataIndex]; const net = m.in - m.out; return `Net: ${net < 0 ? "-" : "+"}${money2(net)}`; },
        } },
      },
      scales: {
        x: { grid: { display: false }, ticks: { color: text }, border: { display: false } },
        y: { grid: { color: grid }, ticks: { color: text, callback: (v) => money(v) }, border: { display: false } },
      },
    },
  });

  chart("spendChart", {
    type: "bar",
    data: { labels: s.top_spend.map((t) => t.category), datasets: [{ data: s.top_spend.map((t) => t.amount), backgroundColor: s1, ...bar }] },
    options: baseOptions({
      indexAxis: "y",
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => money2(c.raw) } } },
      scales: {
        x: { grid: { color: grid }, ticks: { color: text, callback: (v) => money(v) }, border: { display: false } },
        y: { grid: { display: false }, ticks: { color: text }, border: { display: false } },
      },
    }),
  });
}

// ---------------------------------------------------------------- chat
function mdLite(text) {
  return esc(text).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>");
}

function renderChat(chat) {
  const log = $("#chatLog");
  log.innerHTML = chat.length ? chat.map((m) => `<div class="msg ${m.role}">${mdLite(m.content)}</div>`).join("")
    : `<p class="muted small">Ask what to fix first, what an issue means, or how a fix affects your books.</p>`;
  log.scrollTop = log.scrollHeight;
}

async function sendChat(message) {
  if (!message.trim() || !state.scan) return;
  const log = $("#chatLog");
  if (!state.scan.chat.length) log.innerHTML = "";
  log.insertAdjacentHTML("beforeend", `<div class="msg user">${esc(message)}</div><div class="msg assistant muted" id="pending">Thinking...</div>`);
  log.scrollTop = log.scrollHeight;
  $("#chatInput").value = "";
  try {
    const res = await api(`/api/scans/${state.scan.id}/chat`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message }) });
    state.scan.chat = res.chat;
    renderChat(res.chat);
  } catch (e) {
    $("#pending").textContent = "Error: " + e.message;
    $("#pending").removeAttribute("id");
  }
}

// ---------------------------------------------------------------- events
document.addEventListener("DOMContentLoaded", async () => {
  $("#newScanBtn").onclick = showUpload;
  $("#scanPicker").onchange = (e) => e.target.value && openScan(e.target.value);
  ["#fSeverity", "#fCheck", "#fStatus"].forEach((s) => ($(s).onchange = renderIssues));

  $("#uploadForm").onsubmit = async (e) => {
    e.preventDefault();
    $("#uploadError").textContent = "";
    const btn = e.submitter; btn.disabled = true;
    try {
      const scan = await api("/api/scans", { method: "POST", body: new FormData(e.target) });
      await loadScanList(scan.id); render(scan); history.replaceState(null, "", `#${scan.id}`);
    } catch (err) { $("#uploadError").textContent = err.message; }
    btn.disabled = false;
  };
  $("#sampleBtn").onclick = async (e) => {
    e.target.disabled = true;
    try {
      const scan = await api("/api/scans/sample", { method: "POST" });
      await loadScanList(scan.id); render(scan); history.replaceState(null, "", `#${scan.id}`);
    } catch (err) { $("#uploadError").textContent = err.message; }
    e.target.disabled = false;
  };

  $("#issues").onclick = async (e) => {
    const btn = e.target.closest("button[data-act]");
    if (!btn) return;
    const id = btn.dataset.id;
    if (btn.dataset.act === "ask") { sendChat(`Explain issue ${id} and whether I should approve the fix.`); return; }
    btn.disabled = true;
    try {
      const scan = await api(`/api/scans/${state.scan.id}/issues/${id}/decision`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ decision: btn.dataset.act }) });
      render(scan); loadScanList(scan.id);
    } catch (err) { alert(err.message); btn.disabled = false; }
  };
  $("#rescanBtn").onclick = async () => {
    const scan = await api(`/api/scans/${state.scan.id}/rescan`, { method: "POST" });
    render(scan); loadScanList(scan.id);
  };

  $("#chatForm").onsubmit = (e) => { e.preventDefault(); sendChat($("#chatInput").value); };
  document.querySelectorAll(".suggestions .chip").forEach((c) => (c.onclick = () => sendChat(c.textContent)));

  const scans = await loadScanList();
  const wanted = location.hash.slice(1) || scans[0]?.id;
  if (wanted) { try { await openScan(wanted); $("#scanPicker").value = wanted; } catch { showUpload(); } }
  else showUpload();
});
