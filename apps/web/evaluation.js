function arenaEsc(value) {
  return String(value ?? "").replace(/[&<>"']/g, char => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
  }[char]));
}

function renderArenaSelectors(models) {
  const root = $("model-arena-selectors");
  if (!root) return;
  const usable = models.filter(model => model.configured);
  if (!usable.length) {
    root.innerHTML = '<div class="empty">Configure a provider in Settings first.</div>';
    return;
  }
  root.innerHTML = usable.map(model => `
    <label class="job-row" style="cursor:pointer">
      <div>
        <b>${arenaEsc(model.provider.toUpperCase())} · ${arenaEsc(model.model_id)}</b>
        <small>${model.context_window >= 1000000 ? "1M" : Math.round(model.context_window / 1000) + "K"} context · tools ${model.supports_tools ? "yes" : "no"}</small>
      </div>
      <input type="checkbox" class="model-arena-check" value="${arenaEsc(model.key)}">
    </label>`).join("");
}

function renderArenaResults(results) {
  const root = $("model-arena-results");
  if (!root) return;
  if (!results.length) {
    root.innerHTML = '<div class="empty">No models completed this run.</div>';
    return;
  }
  root.innerHTML = results.map(result => {
    const statusClass = result.status === "completed" ? "success" : "warning";
    const score = typeof result.assertion_score === "number" ? ` · assertion ${(result.assertion_score * 100).toFixed(0)}%` : "";
    return `
      <article class="job-row">
        <div>
          <b>${arenaEsc(result.model_id || result.model)}</b>
          <small>${arenaEsc(result.status)} · ${result.latency_ms ?? "—"}ms · ${result.output_chars ?? 0} chars${score}</small>
          <p>${arenaEsc(result.output || result.error || "No output")}</p>
        </div>
        <span class="status-pill ${statusClass}">${arenaEsc(result.status)}</span>
      </article>`;
  }).join("");
}

async function runModelArena() {
  const button = $("model-arena-run");
  const status = $("model-arena-run-status");
  const prompt = $("model-arena-prompt")?.value.trim();
  const expected = $("model-arena-expected")?.value.split(",").map(item => item.trim()).filter(Boolean) || [];
  const models = [...document.querySelectorAll(".model-arena-check:checked")].map(input => input.value);
  if (!prompt) { status.textContent = "Enter a benchmark prompt."; return; }
  if (!models.length) { status.textContent = "Select at least one configured model."; return; }
  button.disabled = true;
  status.textContent = "Running selected models…";
  try {
    const response = await fetch("/api/v1/models/arena/run", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Nexus-User-ID": localStorage.getItem("nexus-user-id") || "local-user"
      },
      body: JSON.stringify({prompt, models, expected_contains: expected})
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Arena run failed");
    renderArenaResults(data.results || []);
    status.textContent = `${data.completed} completed · ${data.failed} failed · ${data.skipped} skipped`;
  } catch (error) {
    status.textContent = error.message;
  } finally {
    button.disabled = false;
  }
}

function renderModelArena(models) {
  const root = $("model-arena-list");
  if (!root) return;
  if (!models.length) {
    root.innerHTML = '<div class="empty">No models are registered.</div>';
    return;
  }
  root.innerHTML = models.map(model => {
    const context = model.context_window >= 1000000 ? "1M context" : `${Math.round(model.context_window / 1000)}K context`;
    const configured = model.configured ? "Configured" : "BYOK required";
    const health = model.available ? "Healthy" : "Degraded";
    return `
      <article class="job-row">
        <div>
          <b>${model.provider.toUpperCase()} · ${model.model_id}</b>
          <small>${model.description} · ${context} · tools ${model.supports_tools ? "yes" : "no"} · ${configured}</small>
        </div>
        <span class="status-pill ${model.available ? "success" : "warning"}">${health} · ${model.latency_ms ? Math.round(model.latency_ms) + "ms" : "—"}</span>
      </article>`;
  }).join("");
}

async function refreshModelArena() {
  const root = $("model-arena-list");
  if (!root) return;
  try {
    const data = await fetch("/api/v1/models/arena", {
      headers: {"X-Nexus-User-ID": localStorage.getItem("nexus-user-id") || "local-user"}
    }).then(r => { if (!r.ok) throw new Error("Model Arena unavailable"); return r.json(); });
    renderModelArena(data.models || []);
    renderArenaSelectors(data.models || []);
  } catch (error) {
    root.innerHTML = `<div class="empty">${error.message}</div>`;
  }
}

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

window.addEventListener("hashchange", () => { if (location.hash === "#evaluation") { refreshEvaluation(); refreshModelArena(); } });
$("evaluation-refresh")?.addEventListener("click", refreshEvaluation);
$("model-arena-refresh")?.addEventListener("click", refreshModelArena);
$("model-arena-run")?.addEventListener("click", runModelArena);
if (location.hash === "#evaluation") refreshEvaluation();


async function runEvaluationGate() {
  const button = $("evaluation-gate");
  if (!button) return;
  button.disabled = true;
  try {
    const quality = await fetch("/api/v1/evaluations/quality?limit=20").then(r => { if (!r.ok) throw new Error("Evaluation quality unavailable"); return r.json(); });
    if (!quality.latest_run_id) throw new Error("No evaluation run available");
    const decision = await fetch("/api/v1/evaluations/gate", {
      method: "POST", headers: {"Content-Type":"application/json"},
      body: JSON.stringify({run_id: quality.latest_run_id})
    }).then(r => { if (!r.ok) throw new Error("Quality gate unavailable"); return r.json(); });
    $("evaluation-gate-detail").textContent = decision.passed
      ? "PASS · latest evaluation satisfies the production quality floor."
      : "BLOCKED · " + decision.reasons.join(", ");
    button.textContent = decision.passed ? "Gate passed" : "Gate blocked";
    button.classList.toggle("ghost", !decision.passed);
  } catch (error) {
    $("evaluation-gate-detail").textContent = error.message;
    button.textContent = "Gate unavailable";
  } finally {
    setTimeout(() => { button.disabled = false; button.textContent = "Run quality gate"; }, 1400);
  }
}
$("evaluation-gate")?.addEventListener("click", runEvaluationGate);
