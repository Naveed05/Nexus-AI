const $p = id => document.getElementById(id);
async function refreshPlatform() {
  try {
    const [infra, analytics, connectors, readiness, specialists] = await Promise.all([
      fetch("/api/v1/platform/infrastructure").then(r=>r.json()),
      fetch("/api/v1/platform/analytics").then(r=>r.json()),
      fetch("/api/v1/platform/connectors").then(r=>r.json()),
      fetch("/api/v1/platform/release/readiness").then(r=>r.json()),
      fetch("/api/v1/platform/specialists").then(r=>r.json()),
    ]);
    $p("platform-infra").textContent = infra.distributed ? "Distributed" : "Single";
    $p("platform-events").textContent = analytics.event_count ?? "0";
    $p("platform-tools").textContent = connectors.length;
    $p("platform-cost").textContent = "Tracked";
    $p("platform-readiness").textContent = readiness.ready ? "READY · current deployment contract is healthy" : "BLOCKED · " + (readiness.infrastructure?.blockers || []).join(", ");
    $p("platform-specialists").innerHTML = specialists.map(s => '<article class="job-row"><div><b>'+s.name+'</b><small>'+s.specialist_id+' · '+s.capabilities.join(", ")+'</small></div><span class="status-pill">'+s.risk_level+'</span></article>').join("");
  } catch (e) {
    $p("platform-readiness").textContent = e.message;
  }
}
$p("platform-refresh")?.addEventListener("click", refreshPlatform);
window.addEventListener("hashchange", () => { if (location.hash === "#platform") refreshPlatform(); });
if (location.hash === "#platform") refreshPlatform();
