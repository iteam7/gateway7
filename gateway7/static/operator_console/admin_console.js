"use strict";
import { providerPanel } from "./provider_panel.js";
import { identityPanels } from "./identity_panel.js";
import { reportingPanels } from "./reporting_panel.js";
import { statusText } from "./admin_forms.js";
import { policyPanel } from "./policy_panel.js";

export function createAdminWorkspace(context) {
  const provider = providerPanel(context);
  const identities = identityPanels(context);
  const reports = reportingPanels(context);
  const policies = policyPanel(context);
  document
    .getElementById("extended-admin")
    .append(
      provider.root,
      ...identities.roots,
      ...reports.roots,
      policies.root,
    );
  document.getElementById("usage-extra").append(reports.trendRoot);
  let generation = 0;
  async function render(state) {
    const current = ++generation;
    document.getElementById("extended-admin").hidden =
      state.configuration.management_enabled !== true;
    if (!state.configuration.management_enabled) return;
    const role = state.actor?.role ?? "admin";
    document.getElementById("operator-identity").textContent =
      `${state.actor?.id ?? "bootstrap"} · ${role === "viewer" ? "Viewer — read only" : "Administrator"}`;
    const results = await Promise.allSettled([
      provider.load(),
      identities.load(),
      reports.load(),
      policies.load(),
    ]);
    if (current !== generation || !context.connected()) return;
    for (const result of results)
      if (
        result.status === "rejected" &&
        result.reason?.message !== "stale-session"
      )
        document.getElementById("extended-message").textContent = statusText(
          result.reason,
        );
  }
  function clear() {
    generation += 1;
    provider.clear();
    identities.clear();
    reports.clear();
    policies.clear();
    document.getElementById("extended-admin").hidden = true;
    document.getElementById("operator-identity").textContent = "";
    document.getElementById("extended-message").textContent = "";
  }
  return {
    render,
    clear,
    renderUsage: reports.renderUsage,
    selectClient: identities.selectClient,
  };
}
