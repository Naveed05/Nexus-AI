const rel = (id) => document.getElementById(id);
const escRel = (v) => String(v ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

async function refreshReliability() {
  try {
    const [summaryRes, historyRes] = await Promise.all([
      fetch("/api/v1/reliability/summary"),
      fetch("/api/v1/reliability/history?limit=20"),
    ]);
    if (!summaryRes.ok || !historyRes.ok) throw new Error("Reliability API unavailable");
    const summary = await summaryRes.json();
    const history = await historyRes.json();
    rel("reliability-status").textContent = summary.status;
    rel("reliability-jobs").textContent = summary.jobs.total ?? "—";
    rel("reliability-failed").textContent = summary.jobs.failed ?? "—";
    rel("reliability-workers").textContent = summary.workers.worker_count ?? "—";
    rel("reliability-events").textContent = summary.events.event_count ?? "—";
    rel("reliability-history").innerHTML = history.length
      ? history.map(item => '<article class="job-row"><div><b>'+escRel(item.action)+'</b><small>'+escRel(item.status)+' · '+new Date(item.created_at).toLocaleString()+'</small></div><span class="status-pill">'+escRel(item.details?.recovered_jobs ?? "—")+' recovered</span></article>').join("")
      : '<div class="empty">No recovery actions recorded yet.</div>';
  } catch (error) {
    rel("reliability-status").textContent = error.message;
  }
}

async function reconcileReliability() {
  const button = rel("reliability-reconcile");
  button.disabled = true;
  try {
    const response = await fetch("/api/v1/reliability/reconcile", {method:"POST"});
    if (!response.ok) throw new Error(await response.text());
    await refreshReliability();
    button.textContent = "Reconciled";
    setTimeout(() => { button.textContent = "Reconcile now"; button.disabled = false; }, 1200);
  } catch (error) {
    button.disabled = false;
    button.textContent = "Retry reconcile";
  }
}

rel("reliability-refresh")?.addEventListener("click", refreshReliability);
rel("reliability-reconcile")?.addEventListener("click", reconcileReliability);
window.addEventListener("hashchange", () => { if (location.hash === "#reliability") refreshReliability(); });
if (location.hash === "#reliability") refreshReliability();
