"use strict";
import { node } from "./admin_forms.js";

const routes = {
  overview: ["Overview", "Your gateway at a glance.", "WORKSPACE"],
  users: [
    "Users & keys",
    "Manage access, credentials and capacity for every user.",
    "ACCESS",
  ],
  models: [
    "Models",
    "Connect your provider and control which models are available.",
    "GATEWAY",
  ],
  "policy-builder": [
    "Policies",
    "Build, test and assign policies without writing code.",
    "GATEWAY",
  ],
  usage: [
    "Usage",
    "Explore provider activity, tokens and estimated costs.",
    "OBSERVABILITY",
  ],
  budgets: [
    "Budgets & pricing",
    "Set spending allowances and keep cost estimates useful.",
    "COST CONTROL",
  ],
  operators: [
    "Operators",
    "Manage the people and automation that administer this gateway.",
    "ADMINISTRATION",
  ],
  activity: [
    "Activity",
    "Investigate request outcomes and attributed administrative changes.",
    "ADMINISTRATION",
  ],
};
const aliases = {
  clients: "users",
  "user-keys": "users",
  "client-editor": "users",
  "provider-management": "models",
  policies: "policy-builder",
  "operator-management": "operators",
  "accounting-management": "budgets",
  "audit-log": "activity",
  diagnostics: "activity",
  "request-diagnostics": "activity",
};

export function createNavigation() {
  const dashboard = document.getElementById("dashboard");
  document.querySelector(".skip-link").addEventListener("click", (event) => {
    event.preventDefault();
    document.getElementById("workspace-content").focus();
  });
  const managedRoutes = new Set(["models", "budgets", "operators", "activity"]);
  for (const link of document.querySelectorAll(".nav-link"))
    if (managedRoutes.has(link.hash.slice(1)))
      link.dataset.managedOnly = "true";
  const views = new Map();
  for (const name of Object.keys(routes)) {
    const view = node("div", undefined, "workspace-view");
    view.dataset.view = name;
    view.hidden = true;
    dashboard.append(view);
    views.set(name, view);
  }
  function place(name, ...elements) {
    for (const element of elements)
      if (element) views.get(name).append(element);
  }
  place(
    "overview",
    dashboard.querySelector(".status-line"),
    dashboard.querySelector(".summary-grid"),
    dashboard.querySelector(".footer-note"),
  );
  for (const [name, ids] of Object.entries({
    users: ["clients", "client-editor", "user-keys"],
    models: ["provider-management"],
    "policy-builder": ["policy-management", "policies", "plugin-capabilities"],
    usage: ["usage"],
    budgets: ["accounting-management"],
    operators: ["operator-management"],
    activity: ["request-diagnostics", "audit-log"],
  }))
    place(name, ...ids.map((id) => document.getElementById(id)));
  const tokenPanel = document.getElementById("issued-token-panel");
  document.body.append(tokenPanel);
  const shortcuts = node("section", undefined, "overview-links");
  shortcuts.setAttribute("aria-label", "Workspace shortcuts");
  for (const [name, description] of [
    ["users", "Give a user the access they need."],
    ["models", "Choose your provider and available models."],
    ["policy-builder", "Define how requests and responses are handled."],
    ["usage", "See what is running and how much it uses."],
  ]) {
    const link = node("a", undefined, "shortcut-card");
    link.href = `#${name}`;
    link.append(
      node("span", routes[name][0]),
      node("p", description),
      node("span", "→", "shortcut-arrow"),
    );
    shortcuts.append(link);
  }
  views
    .get("overview")
    .insertBefore(shortcuts, views.get("overview").lastElementChild);
  const toggle = document.getElementById("toggle-navigation");
  const backdrop = node("button", undefined, "navigation-backdrop");
  backdrop.type = "button";
  backdrop.setAttribute("aria-label", "Close navigation");
  document.body.append(backdrop);
  function closeMenu() {
    document.body.classList.remove("navigation-open");
    toggle.setAttribute("aria-expanded", "false");
  }
  backdrop.addEventListener("click", closeMenu);
  toggle.addEventListener("click", () => {
    const open = document.body.classList.toggle("navigation-open");
    toggle.setAttribute("aria-expanded", String(open));
    if (open) document.querySelector(".nav-link.selected")?.focus();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeMenu();
  });
  document.addEventListener("click", (event) => {
    if (!event.target.closest(".sidebar, #toggle-navigation")) closeMenu();
  });
  function render({ focus = false } = {}) {
    const raw = location.hash.slice(1);
    let name = aliases[raw] ?? (routes[raw] ? raw : "overview");
    if (
      document.body.dataset.authenticated === "true" &&
      document.body.dataset.managed === "false" &&
      managedRoutes.has(name)
    )
      name = "overview";
    for (const [route, view] of views) view.hidden = route !== name;
    for (const link of document.querySelectorAll(".nav-link")) {
      const selected = link.hash === `#${name}`;
      link.classList.toggle("selected", selected);
      if (selected) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    }
    const [title, description, eyebrow] = routes[name];
    document.getElementById("page-title").textContent = title;
    document.getElementById("breadcrumb").textContent = title;
    document.getElementById("page-description").textContent = description;
    document.getElementById("page-eyebrow").textContent = eyebrow;
    document.title = `${title} · Gateway7`;
    closeMenu();
    if (focus) {
      document
        .getElementById("workspace-content")
        .focus({ preventScroll: true });
      window.scrollTo(0, 0);
    }
  }
  window.addEventListener("hashchange", () => render({ focus: true }));
  render();
  return {
    render,
    go: (route) => {
      location.hash = route;
      render();
    },
  };
}
