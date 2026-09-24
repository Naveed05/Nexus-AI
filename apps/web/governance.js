const governance = (id) => document.getElementById(id);

async function loadGovernanceAudit() {
  const tenant = governance("governance-tenant")?.value.trim();
  if (!tenant) return;
  const summary = governance("governance-summary");
  try {
    const response = await fetch("/api/v1/governance/audit?tenant_id=" + encodeURIComponent(tenant));
    if (!response.ok) throw new Error("Governance API unavailable");
    const events = await response.json();
    const allows = events.filter(event => event.decision === "allow").length;
    const denies = events.filter(event => event.decision === "deny").length;
    governance("governance-events").textContent = events.length;
    governance("governance-allows").textContent = allows;
    governance("governance-denies").textContent = denies;
    summary.textContent = tenant + " · " + events.length + " audit events";
    governance("governance-audit-list").innerHTML = events.length
      ? events.map(event => `<article class="job-row"><div><b>${event.action}</b><small>${event.principal_id || "system"} · ${new Date(event.created_at).toLocaleString()}</small></div><span class="status-pill">${event.decision}</span></article>`).join("")
      : '<div class="empty">No audit events for this tenant.</div>';
  } catch (error) {
    summary.textContent = error.message;
  }
}

governance("governance-load")?.addEventListener("click", loadGovernanceAudit);
window.addEventListener("hashchange", () => { if (location.hash === "#governance") governance("governance-tenant")?.focus(); });
