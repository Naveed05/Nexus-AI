const $ = (id) => document.getElementById(id);

function pct(value) {
  return typeof value === "number" ? `${(value * 100).toFixed(1)}%` : "—";
}

function renderRuns(data) {
  const root = $("evaluation-runs");
  if (!data.length) { root.innerHTML = '<div class="empty">No evaluation runs recorded yet.</div>'; return; }
  root.innerHTML = data.slice(0, 8).map(run => `
    <article class="job-row"><div><b>${run.suite_name} · v${run.suite_version}</b><small>${new Date(run.created_at).toLocaleString()}</small></div>
      <span class="status-pill ${run.report.pass_rate === 1 ? "success" : "warning"}">${pct(run.report.pass_rate)}</span></article>`).join("");
}

function renderComponents(data) {
  const root = $("evaluation-components");
  if (!data.length) { root.innerHTML = '<div class="empty">No component telemetry recorded yet.</div>'; return; }
  root.innerHTML = data.slice(0, 10).map(item => `
    <article class="job-row"><div><b>${item.component_type} · ${item.component_id}</b><small>${item.events} events · ${item.total_tokens} tokens · $${item.total_cost_usd.toFixed(4)}</small></div>
      <span class="status-pill">${pct(item.success_rate)}</span></article>`).join("");
}

async function refreshEvaluation() {
  try {
    const [trendRes, metricsRes] = await Promise.all([
      fetch("/api/v1/evaluations/trends?limit=20"),
      fetch("/api/v1/evaluations/metrics?limit=50"),
    ]);
    if (!trendRes.ok || !metricsRes.ok) throw new Error("Evaluation API unavailable");
    const trend = await trendRes.json();
    const metrics = await metricsRes.json();
    const latest = trend.points?.at(-1);
    $("eval-pass-rate").textContent = pct(latest?.pass_rate);
    $("eval-check-score").textContent = pct(latest?.check_score);
    $("eval-grounding").textContent = pct(latest?.grounding_score);
    $("eval-drift").textContent = trend.drift ? "Detected" : trend.direction === "insufficient-data" ? "—" : "Stable";
    $("evaluation-summary").textContent = trend.points?.length ? `${trend.points.length} recorded runs · ${trend.direction}` : "No runs recorded yet";
    renderRuns(trend.points ? [...trend.points].reverse().map(p => ({suite_name: "Evaluation", suite_version: "history", created_at: p.created_at, report: {pass_rate: p.pass_rate}})) : []);
    renderComponents(metrics);
  } catch (error) {
    $("evaluation-summary").textContent = error.message;
  }
}

window.addEventListener("hashchange", () => { if (location.hash === "#evaluation") refreshEvaluation(); });
$("evaluation-refresh")?.addEventListener("click", refreshEvaluation);
if (location.hash === "#evaluation") refreshEvaluation();
