"use strict";
import { createAdminWorkspace } from "./admin_console.js";
import { createNavigation } from "./navigation.js";

(() => {
  const byId = (id) => document.getElementById(id);
  const number = (value) => {
    if (
      typeof value !== "number" ||
      !Number.isFinite(value) ||
      !Number.isInteger(value) ||
      value < 0
    )
      throw new Error("invalid-state");
    return value;
  };
  const formatted = (value) =>
    `${Number.isSafeInteger(number(value)) ? "" : "≈ "}${value.toLocaleString()}`;
  let token = "";
  let authentication = null;
  let csrfToken = "";
  let loggingOut = false;
  let signingIn = false;
  let navigation = null;
  let tokenReturnFocus = null;
  let session = 0;
  let latestLoad = 0;
  let snapshot = null;
  let panels = null;
  let clientOffset = 0;
  let usageOffset = 0;
  let editingId = null;
  let editingRevision = null;
  let middlewareOrder = [];
  let mutating = false;
  let filtering = false;
  let exporting = false;
  let operatorRotation = null;
  const pending = new Set();

  function element(tag, text, className) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = String(text);
    if (className) node.className = className;
    return node;
  }
  function cell(row, text, className) {
    const node = element("td", text, className);
    row.append(node);
    return node;
  }
  function badge(text, status) {
    return element("span", text, `badge ${status}`);
  }
  function clientName(target, name) {
    const wrapper = element("div", undefined, "client-name");
    wrapper.append(
      element("span", String(name).slice(0, 1).toUpperCase(), "avatar"),
      element("span", name),
    );
    target.append(wrapper);
  }
  function pills(target, values) {
    const wrapper = element("div", undefined, "pills");
    for (const value of values) wrapper.append(element("span", value, "pill"));
    if (!values.length)
      wrapper.append(element("span", "None configured", "secondary-line"));
    target.append(wrapper);
  }
  function emptyRow(id, columns, message) {
    const row = element("tr");
    cell(row, message, "empty-row").colSpan = columns;
    byId(id).append(row);
  }
  function managed() {
    return snapshot?.configuration?.management_enabled === true;
  }
  function clearIssuedToken() {
    document.querySelector(".workspace").inert = false;
    document.querySelector(".sidebar").inert = false;
    byId("issued-token").value = "";
    byId("issued-token").type = "password";
    byId("issued-token-note").textContent = "";
    byId("issued-token-panel").hidden = true;
    byId("reveal-token").textContent = "Reveal";
    byId("copy-token").textContent = "Copy";
    if (tokenReturnFocus?.isConnected && !tokenReturnFocus.closest("[hidden]"))
      tokenReturnFocus.focus({ preventScroll: true });
    tokenReturnFocus = null;
  }
  function closeEditor() {
    byId("client-editor").hidden = true;
    byId("client-form").reset();
    byId("client-id").disabled = false;
    byId("editor-message").textContent = "";
    byId("middleware-order").replaceChildren();
    middlewareOrder = [];
    editingId = null;
    editingRevision = null;
  }
  function clearData() {
    for (const id of [
      "clients-body",
      "usage-body",
      "plugins-body",
      "chains",
      "usage-client-options",
      "middleware-choice",
    ])
      byId(id).replaceChildren();
    for (const id of [
      "client-count",
      "attempt-count",
      "token-count",
      "plugin-count",
    ])
      byId(id).textContent = "—";
    for (const id of [
      "client-summary",
      "token-summary",
      "plugin-summary",
      "shared-limit",
      "usage-window",
      "refreshed-at",
      "usage-message",
    ])
      byId(id).textContent = "";
    byId("usage-filters").reset();
    byId("dashboard").hidden = true;
    byId("dashboard").inert = false;
    byId("dashboard").setAttribute("aria-busy", "false");
    byId("connected-actions").hidden = true;
    byId("mode-badge").textContent = "OPERATOR";
    byId("workspace-mode").textContent = "Operator workspace";
    closeEditor();
    clearIssuedToken();
    snapshot = null;
    panels?.clear();
    byId("client-directory-filters").reset();
    clientOffset = usageOffset = 0;
  }
  function disconnect() {
    session += 1;
    operatorRotation = null;
    latestLoad += 1;
    for (const controller of pending) controller.abort();
    pending.clear();
    token = "";
    authentication = null;
    signingIn = false;
    csrfToken = "";
    document.body.dataset.authenticated = "false";
    document.body.dataset.managed = "false";
    mutating = filtering = exporting = false;
    byId("operator-token").value = "";
    byId("login-password").value = "";
    byId("login-password").type = "password";
    byId("sign-in").disabled = false;
    byId("sign-in").textContent = "Sign in →";
    byId("connect").disabled = false;
    byId("show-token-login").disabled = false;
    byId("show-password").textContent = "Show";
    byId("connection-panel").hidden = false;
    for (const id of [
      "connect",
      "refresh",
      "apply-usage",
      "clear-usage",
      "export-usage",
    ])
      byId(id).disabled = false;
    byId("message").textContent = "";
    clearData();
    setMutationBusy(false);
  }
  async function request(
    path,
    { method = "GET", body, blob = false, revision, rotation = null } = {},
  ) {
    const currentSession = session;
    const controller = new AbortController();
    pending.add(controller);
    try {
      const headers =
        authentication === "token" ? { Authorization: `Bearer ${token}` } : {};
      if (method !== "GET") {
        headers["X-Gateway7-Operator"] = "true";
        if (authentication === "session")
          headers["X-Gateway7-CSRF"] = csrfToken;
        const expectedRevision = revision ?? snapshot?.revision;
        if (expectedRevision !== undefined)
          headers["If-Match"] = String(expectedRevision);
      }
      if (body !== undefined) headers["Content-Type"] = "application/json";
      const response = await fetch(path, {
        method,
        headers,
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
        credentials: authentication === "session" ? "same-origin" : "omit",
        cache: "no-store",
        redirect: "error",
        signal: controller.signal,
      });
      if (currentSession !== session) throw new Error("stale-session");
      if (!response.ok) {
        if (response.status === 401) {
          if (
            operatorRotation?.session === currentSession &&
            rotation !== operatorRotation
          ) {
            operatorRotation.unauthorized = true;
            throw new Error("stale-session");
          }
          disconnect();
          byId("message").textContent =
            "Your session has expired or access was revoked. Sign in again.";
          throw new Error("stale-session");
        }
        throw new Error(
          response.status === 404
            ? "not-found"
            : response.status === 409
              ? "conflict"
              : response.status === 403
                ? "forbidden"
                : [400, 422].includes(response.status)
                  ? "rejected"
                  : "request-failed",
        );
      }
      const result =
        response.status === 204
          ? null
          : blob
            ? await response.blob()
            : await response.json();
      if (currentSession !== session) throw new Error("stale-session");
      return result;
    } finally {
      pending.delete(controller);
    }
  }
  function failureMessage(failure) {
    return failure?.message === "conflict"
      ? "Another operator changed this configuration. Refresh and apply your change again."
      : failure?.message === "not-found"
        ? "This item is unavailable. Refresh the workspace and try again."
        : failure?.message === "rejected"
          ? "Request rejected. Check the user ID, models, limits and middleware selection."
          : "Could not confirm the request. Check your connection and refresh before retrying.";
  }
  function ignorable(failure) {
    return (
      failure?.name === "AbortError" || failure?.message === "stale-session"
    );
  }
  function clientQuery() {
    const query = new URLSearchParams({
      offset: String(clientOffset),
      limit: "25",
    });
    for (const [name, id] of [
      ["search", "client-search"],
      ["status", "client-status"],
      ["owner", "client-owner-filter"],
      ["tag", "client-tag-filter"],
    ])
      if (byId(id).value.trim()) query.set(name, byId(id).value.trim());
    return `?${query}`;
  }
  function usageQuery() {
    const query = new URLSearchParams({
      offset: String(usageOffset),
      limit: "25",
      bucket: byId("usage-bucket")?.value || "day",
    });
    for (const [field, id] of [
      ["client_id", "usage-client"],
      ["model", "usage-model"],
    ])
      if (byId(id).value.trim()) query.set(field, byId(id).value.trim());
    if (byId("usage-start").value)
      query.set("start", `${byId("usage-start").value}T00:00:00Z`);
    if (byId("usage-end").value) {
      const end = new Date(`${byId("usage-end").value}T00:00:00Z`);
      end.setUTCDate(end.getUTCDate() + 1);
      query.set("end", end.toISOString());
    }
    return `?${query}`;
  }

  function validateDates() {
    if (
      byId("usage-start").value &&
      byId("usage-end").value &&
      byId("usage-start").value > byId("usage-end").value
    ) {
      byId("usage-message").textContent =
        "The start date must be on or before the end date.";
      return false;
    }
    return true;
  }
  function renderUsage(usage) {
    if (!usage.clients || typeof usage.clients !== "object")
      throw new Error("invalid-state");
    const persistent =
      usage.scope === "persistent" && usage.reset_on_restart === false;
    const appliedFilters =
      persistent && usage.filters
        ? Object.entries(usage.filters).filter(
            ([, value]) => value !== null && value !== "",
          )
        : [];
    const filtered = appliedFilters.length > 0;
    const accounts = Object.entries(usage.clients);
    const totals = accounts.reduce(
      (total, [, account]) => ({
        attempts: total.attempts + number(account.provider_attempts),
        input: total.input + number(account.known_input_tokens),
        output: total.output + number(account.known_output_tokens),
      }),
      { attempts: 0, input: 0, output: 0 },
    );
    byId("attempt-count").textContent = formatted(totals.attempts);
    byId("token-count").textContent = formatted(totals.input + totals.output);
    byId("token-summary").textContent =
      `${formatted(totals.input)} input · ${formatted(totals.output)} output${filtered ? " · filtered" : ""}`;
    byId("attempt-summary").textContent = persistent
      ? filtered
        ? "Matching applied usage filters"
        : "All recorded usage, across restarts"
      : "Since this process started";
    byId("usage-scope").textContent = persistent
      ? "PERSISTENT USAGE · UTC DAYS"
      : "PROCESS LIFETIME";
    byId("usage-persistence").textContent = persistent
      ? "Retained across restarts"
      : "Resets on restart";
    const started = new Date(usage.started_at);
    byId("usage-window").textContent =
      `${persistent ? "Recorded since" : "Process started"} ${Number.isNaN(started.getTime()) ? "startup" : started.toLocaleString()}${filtered ? ` · ${appliedFilters.map(([key, value]) => `${key}: ${value}`).join(" · ")}` : ""}`;
    byId("usage-model-heading").hidden = !persistent;
    const rows =
      persistent && Array.isArray(usage.rows)
        ? usage.rows
        : accounts.map(([client_id, account]) => ({ client_id, ...account }));
    const body = byId("usage-body");
    body.replaceChildren();
    for (const account of rows) {
      const row = element("tr");
      cell(row, account.client_id);
      if (persistent) {
        const model = cell(row, account.model);
        model.append(element("span", account.day, "secondary-line"));
      }
      cell(row, formatted(account.provider_attempts), "numeric");
      const outcomes = cell(row);
      outcomes.append(
        element(
          "span",
          `${formatted(account.outcomes.complete)} complete`,
          "good",
        ),
        element(
          "span",
          `${formatted(account.outcomes.provider_error)} error · ${formatted(account.outcomes.cancelled)} cancelled`,
          "secondary-line",
        ),
      );
      cell(
        row,
        `${formatted(account.known_input_tokens)} / ${formatted(account.known_output_tokens)}`,
        "numeric",
      );
      cell(
        row,
        `${formatted(account.input_usage_unknown_attempts)} input / ${formatted(account.output_usage_unknown_attempts)} output`,
        "numeric",
      );
      body.append(row);
    }
    panels?.renderUsage(usage);
    if (!rows.length)
      emptyRow(
        "usage-body",
        persistent ? 6 : 5,
        "No recorded provider usage matches these filters.",
      );
  }
  function actionButton(text, action, className = "secondary") {
    const button = element(
      "button",
      text,
      `button compact mutation-button ${className}`,
    );
    button.type = "button";
    button.disabled = mutating;
    button.addEventListener("click", action);
    return button;
  }
  function render(state, usage) {
    if (
      !Array.isArray(state.clients) ||
      !Array.isArray(state.middleware.plugins)
    )
      throw new Error("invalid-state");
    snapshot = state;
    const clients = state.clients;
    const plugins = state.middleware.plugins;
    const writable = managed() && state.actor?.role !== "viewer";
    byId("mode-badge").textContent = writable ? "LIVE MANAGEMENT" : "READ ONLY";
    byId("workspace-mode").textContent = writable
      ? "Live user management"
      : "Read-only workspace";
    byId("create-client").hidden = !writable;
    byId("actions-heading").hidden = !writable;
    byId("usage-filters").hidden = !managed();
    byId("client-directory-filters").hidden = !managed();
    byId("previous-clients").disabled = clientOffset === 0;
    byId("next-clients").disabled =
      clientOffset + 25 >= (state.clients_total ?? clients.length);
    byId("clients-page").textContent =
      `${state.clients_total ? clientOffset + 1 : 0}–${Math.min(clientOffset + clients.length, state.clients_total ?? clients.length)} of ${state.clients_total ?? clients.length}`;
    byId("management-note-title").textContent = writable
      ? "User changes apply immediately."
      : "Enable user management in this console.";
    byId("management-note").textContent = writable
      ? "Access, provider settings and managed policies are saved across restarts and apply to new requests. Requests already in progress may finish. Custom middleware modules stay managed on the server."
      : "Enable PostgreSQL administration using the server's management database and operator credential settings, then restart once. SQLite remains available for local setups. This gateway currently uses configuration-file accounts.";
    byId("client-count").textContent = formatted(
      state.clients_total ?? clients.length,
    );
    const enabled = clients.filter((client) => client.enabled).length;
    byId("client-summary").textContent =
      `${enabled} enabled · ${clients.length - enabled} suspended on this page`;
    byId("plugin-count").textContent = formatted(
      plugins.filter((plugin) => plugin.in_chain).length,
    );
    byId("plugin-summary").textContent =
      `${plugins.length} configured instances`;
    byId("shared-limit").textContent =
      `Shared concurrency cap: ${formatted(state.gateway.max_concurrent_requests)}`;
    const options = byId("usage-client-options");
    options.replaceChildren();
    for (const id of new Set([
      ...clients.map((client) => client.id),
      ...Object.keys(usage.clients),
    ])) {
      const option = element("option");
      option.value = id;
      options.append(option);
    }
    const clientBody = byId("clients-body");
    clientBody.replaceChildren();
    for (const client of clients) {
      const row = element("tr");
      const identity = cell(row);
      clientName(identity, client.id);
      if (client.owner || client.tags?.length)
        identity.append(
          element(
            "span",
            `${client.owner || "No owner"}${client.tags?.length ? ` · ${client.tags.join(", ")}` : ""}`,
            "secondary-line",
          ),
        );
      const status = cell(row);
      status.append(
        badge(
          client.enabled ? "Enabled" : "Suspended",
          client.enabled ? "active" : "suspended",
        ),
      );
      if (writable && !client.credential_active)
        status.append(element("span", "No active token", "secondary-line"));
      const permission = cell(row);
      if (client.models === null)
        permission.append(element("span", "All gateway-allowed models"));
      else if (client.models.length === 0)
        permission.append(element("span", "No models allowed"));
      else pills(permission, client.models);
      if (
        client.effective_models &&
        JSON.stringify(client.effective_models) !==
          JSON.stringify(client.models)
      )
        permission.append(
          element(
            "span",
            `Effective: ${client.effective_models.join(", ") || "No models"}`,
            "secondary-line warning-text",
          ),
        );
      if (client.default_denied)
        permission.append(
          element(
            "span",
            "The default model is denied; choose an allowed model explicitly.",
            "secondary-line warning-text",
          ),
        );
      if (client.default_model)
        permission.append(
          element(
            "span",
            `User default: ${client.default_model}`,
            "secondary-line",
          ),
        );
      cell(
        row,
        client.limits.max_concurrent_requests === null
          ? "Shared limit only"
          : formatted(client.limits.max_concurrent_requests),
        "numeric",
      );
      cell(
        row,
        client.limits.requests_per_minute === null
          ? "No user rate cap"
          : formatted(client.limits.requests_per_minute),
        "numeric",
      );
      if (writable) {
        const actions = element("div", undefined, "row-actions");
        actions.append(
          actionButton("Edit", () => openEditor(client)),
          actionButton(client.enabled ? "Suspend" : "Enable", () =>
            toggleClient(client),
          ),
          actionButton("Keys", () => {
            void panels.selectClient(client.id);
          }),
        );
        actions.append(
          actionButton("Delete", () => deleteClient(client), "danger"),
        );
        cell(row).append(actions);
      }
      clientBody.append(row);
    }
    if (!clients.length)
      emptyRow(
        "clients-body",
        writable ? 6 : 5,
        writable
          ? "No users yet. Add a user to grant gateway access."
          : "No configured clients.",
      );
    renderUsage(usage);
    const chainRoot = byId("chains");
    chainRoot.replaceChildren();
    function chain(label, baseline, extra, caption) {
      const row = element("div", undefined, "chain-row");
      row.append(element("div", label, "chain-label"));
      const content = element("div");
      const track = element("div", undefined, "chain-track");
      const nodes = [
        ...baseline.map((name) => ({ name, extra: false })),
        ...extra.map((name) => ({ name, extra: true })),
      ];
      nodes.forEach((node, index) => {
        if (index) track.append(element("span", "→", "chain-arrow"));
        track.append(
          element("span", node.name, `chain-node${node.extra ? " extra" : ""}`),
        );
      });
      if (!nodes.length)
        track.append(element("span", "No active middleware", "chain-empty"));
      content.append(track);
      if (caption) content.append(element("p", caption, "chain-caption"));
      row.append(content);
      chainRoot.append(row);
    }
    chain(
      "Shared baseline",
      state.middleware.active_global,
      [],
      "Active global order",
    );
    for (const client of clients) {
      const activeExtra = client.effective_middleware.slice(
        state.middleware.active_global.length,
      );
      chain(
        client.id,
        client.enabled ? state.middleware.active_global : [],
        activeExtra,
        client.enabled
          ? client.additional_middleware.length
            ? `Configured additions: ${client.additional_middleware.join(" → ")}`
            : "Uses the shared baseline"
          : "Account suspended; no request pipeline",
      );
    }

    const pluginBody = byId("plugins-body");
    pluginBody.replaceChildren();
    for (const plugin of plugins) {
      const row = element("tr");
      const name = cell(row, plugin.instance);
      if (plugin.capabilities)
        name.append(
          element("span", plugin.capabilities.plugin_id, "secondary-line"),
        );
      const configuration = cell(row);
      const statuses = element("div", undefined, "pills");
      statuses.append(
        badge(
          plugin.enabled ? "Enabled" : "Disabled",
          plugin.enabled ? "active" : "muted",
        ),
      );
      if (plugin.required) statuses.append(badge("Required", "required"));
      configuration.append(
        statuses,
        element(
          "span",
          plugin.validation === "validated_before_activation"
            ? "Validated before activation"
            : "Validated at startup",
          "secondary-line",
        ),
      );
      const caps = plugin.capabilities;
      cell(
        row,
        caps
          ? caps.tool_inspection
            ? "Declared"
            : "Not declared"
          : "Not instantiated",
      );
      cell(
        row,
        caps
          ? [
              caps.responses_request_hook && "Request",
              caps.responses_response_hook && "Response",
            ]
              .filter(Boolean)
              .join(" + ") || "None registered"
          : "Not instantiated",
      );
      cell(
        row,
        caps
          ? [
              caps.chat_early_hook && "Chat",
              caps.responses_early_hook && "Responses",
            ]
              .filter(Boolean)
              .join(" + ") || "None registered"
          : "Not instantiated",
      );
      pluginBody.append(row);
    }

    if (!plugins.length)
      emptyRow("plugins-body", 5, "No configured middleware instances.");
    byId("refreshed-at").textContent =
      `Updated ${new Date().toLocaleTimeString()}`;
  }

  async function load() {
    const loadId = ++latestLoad;
    const currentSession = session;
    byId("dashboard").inert = true;
    byId("dashboard").setAttribute("aria-busy", "true");
    byId("message").textContent = "";
    byId("connect").disabled = byId("refresh").disabled = true;
    try {
      const state = await request("./state");
      if (state.configuration.management_enabled) {
        const directory = await request(`./clients${clientQuery()}`);
        state.clients = directory.items;
        state.clients_total = directory.total;
        state.revision = directory.revision;
      }
      const usage =
        state.configuration.management_enabled && usageQuery()
          ? await request(`./usage${usageQuery()}`)
          : state.usage;
      if (loadId !== latestLoad || currentSession !== session) return;
      render(state, usage);
      byId("connection-panel").hidden = true;
      byId("dashboard").hidden = false;
      byId("connected-actions").hidden = false;
      document.body.dataset.authenticated = "true";
      document.body.dataset.managed = String(
        state.configuration.management_enabled === true,
      );
      await panels.render(state);
      navigation?.render();
    } catch (failure) {
      if (
        ignorable(failure) ||
        loadId !== latestLoad ||
        currentSession !== session
      )
        return;
      if (!snapshot) disconnect();
      byId("message").textContent = failureMessage(failure);
    } finally {
      if (currentSession === session && loadId === latestLoad) {
        byId("connect").disabled = byId("refresh").disabled = false;
        byId("dashboard").inert = false;
        byId("dashboard").setAttribute("aria-busy", "false");
      }
    }
  }
  function editable(client) {
    return {
      enabled: client.enabled,
      owner: client.owner ?? "",
      tags: client.tags ?? [],
      default_model: client.default_model ?? null,
      models: client.models,
      limits: { ...client.limits },
      additional_middleware: [...client.additional_middleware],
    };
  }
  function renderMiddlewareOrder() {
    byId("middleware-order").replaceChildren();
    middlewareOrder.forEach((name, index) => {
      const row = element("li");
      row.append(element("span", name, "pill"));
      for (const [text, delta] of [
        ["Move up", -1],
        ["Move down", 1],
      ]) {
        const button = element("button", text, "text-button");
        button.type = "button";
        button.disabled =
          index + delta < 0 || index + delta >= middlewareOrder.length;
        button.addEventListener("click", () => {
          [middlewareOrder[index], middlewareOrder[index + delta]] = [
            middlewareOrder[index + delta],
            middlewareOrder[index],
          ];
          renderMiddlewareOrder();
        });
        row.append(button);
      }
      const remove = element("button", "Remove", "text-button danger-text");
      remove.type = "button";
      remove.addEventListener("click", () => {
        middlewareOrder.splice(index, 1);
        renderMiddlewareOrder();
      });
      row.append(remove);
      byId("middleware-order").append(row);
    });
  }
  function openEditor(client = null) {
    if (!managed() || mutating) return;
    navigation?.go("users");
    closeEditor();
    editingId = client?.id ?? null;
    editingRevision = client?.revision ?? snapshot?.revision;
    byId("client-id").value = editingId ?? "";
    byId("client-id").disabled = editingId !== null;
    byId("editor-title").textContent = client
      ? `Edit user: ${client.id}`
      : "Add user";
    byId("save-client").textContent = client
      ? "Save changes"
      : "Create user & issue token";
    byId("client-enabled").value = String(client?.enabled ?? true);
    byId("client-owner").value = client?.owner ?? "";
    byId("client-tags").value = (client?.tags ?? []).join(", ");
    byId("client-default-model").value = client?.default_model ?? "";
    byId("client-model-mode").value = client
      ? client.models === null
        ? "all"
        : client.models.length
          ? "listed"
          : "none"
      : "listed";
    const availableModels = snapshot.gateway.allowed_models;
    const defaultModel = snapshot.gateway.default_model;
    const suggestedModels = [
      ...new Set(
        [defaultModel, ...(availableModels ?? [])].filter(
          (value) =>
            typeof value === "string" &&
            (availableModels == null || availableModels.includes(value)),
        ),
      ),
    ];
    byId("client-models").value =
      client?.models?.join("\n") ?? (client ? "" : (suggestedModels[0] ?? ""));
    const modelChoice = byId("model-suggestion");
    modelChoice.replaceChildren();
    const modelPlaceholder = element("option", "Add a suggested gateway model");
    modelPlaceholder.value = "";
    modelChoice.append(modelPlaceholder);
    for (const model of suggestedModels) {
      const option = element("option", model);
      option.value = model;
      modelChoice.append(option);
    }
    modelChoice.hidden = suggestedModels.length === 0;
    byId("client-concurrency").value =
      client?.limits.max_concurrent_requests ?? "";
    byId("client-rate").value = client?.limits.requests_per_minute ?? "";
    middlewareOrder = [...(client?.additional_middleware ?? [])];
    const choice = byId("middleware-choice");
    choice.replaceChildren();
    const placeholder = element(
      "option",
      "Choose a configured middleware instance",
    );
    placeholder.value = "";
    choice.append(placeholder);
    for (const plugin of snapshot.middleware.plugins) {
      if (
        !plugin.enabled ||
        snapshot.middleware.global.includes(plugin.instance)
      )
        continue;
      const option = element("option", plugin.instance);
      option.value = plugin.instance;
      choice.append(option);
    }
    renderMiddlewareOrder();
    updateModelField();
    byId("client-editor").hidden = false;
    byId(client ? "client-enabled" : "client-id").focus();
    byId("client-editor").scrollIntoView({ block: "start" });
  }
  function updateModelField() {
    byId("model-list-field").hidden =
      byId("client-model-mode").value !== "listed";
    byId("client-models").required =
      byId("client-model-mode").value === "listed";
  }
  function setMutationBusy(value) {
    mutating = value;
    for (const button of document.querySelectorAll(
      ".mutation-button, #create-client",
    ))
      button.disabled = value;
    for (const control of byId("client-form").elements)
      control.disabled = value;
    if (!value) {
      byId("client-id").disabled = editingId !== null;
      renderMiddlewareOrder();
    }
  }
  async function mutate(path, options, onSuccess, target = "message") {
    if (mutating || !managed() || snapshot?.actor?.role === "viewer") return;
    const currentSession = session;
    setMutationBusy(true);
    byId(target).textContent = "";
    try {
      const result = await request(path, options);
      if (currentSession !== session) return;
      if (onSuccess) onSuccess(result);
      await load();
    } catch (failure) {
      if (!ignorable(failure) && currentSession === session)
        byId(target).textContent = failureMessage(failure);
    } finally {
      if (currentSession === session) setMutationBusy(false);
    }
  }
  function allowNewToken() {
    return (
      byId("issued-token-panel").hidden ||
      window.confirm(
        "A token is still displayed. Have you saved it? Continuing replaces that one-time display.",
      )
    );
  }
  function showIssuedToken(id, value) {
    const focused = document.activeElement;
    clearIssuedToken();
    if (typeof value !== "string" || !/^[\x21-\x7e]{16,512}$/.test(value))
      throw new Error("invalid-token-response");
    byId("issued-token").value = value;
    byId("issued-token-note").textContent =
      `New credential for ${id}. Save it now; it cannot be retrieved again.`;
    byId("issued-token-panel").hidden = false;
    document.querySelector(".workspace").inert = true;
    document.querySelector(".sidebar").inert = true;
    tokenReturnFocus = focused;
    byId("issued-token-panel").scrollIntoView({ block: "center" });
    byId("reveal-token").focus();
  }
  function showRotatedOperatorToken(id, value) {
    showIssuedToken(`operator ${id}`, value);
    if (
      authentication !== "token" ||
      snapshot?.actor?.id !== id ||
      token === ""
    )
      return;
    // Requests admitted with the previous credential must not disconnect the
    // replacement session when their responses arrive after this handoff.
    session += 1;
    latestLoad += 1;
    for (const controller of pending) controller.abort();
    pending.clear();
    token = value;
    mutating = filtering = exporting = false;
    for (const id of ["apply-usage", "clear-usage", "export-usage"])
      byId(id).disabled = false;
    setMutationBusy(false);
  }
  async function rotateOperatorToken(id, body) {
    const own =
      authentication === "token" && snapshot?.actor?.id === id && token !== "";
    if (own && operatorRotation?.session === session)
      throw new Error("rotation-pending");
    const transition = own ? { session, unauthorized: false } : null;
    if (own) operatorRotation = transition;
    try {
      const result = await request(
        `./operators/${encodeURIComponent(id)}/token`,
        { method: "POST", body, rotation: transition },
      );
      showRotatedOperatorToken(id, result.token);
      return result;
    } catch (failure) {
      if (transition?.session === session && transition.unauthorized) {
        disconnect();
        byId("message").textContent =
          "The operator token was not accepted. Connect again.";
      }
      throw failure;
    } finally {
      if (operatorRotation === transition) operatorRotation = null;
    }
  }
  function toggleClient(client) {
    void mutate(`./clients/${encodeURIComponent(client.id)}`, {
      method: "PUT",
      body: { ...editable(client), enabled: !client.enabled },
      revision: client.revision,
    });
  }
  function issueToken(client) {
    if (
      !allowNewToken() ||
      !window.confirm(
        `Issue a new token for ${client.id}? Any existing token will stop working immediately.`,
      )
    )
      return;
    void mutate(
      `./clients/${encodeURIComponent(client.id)}/token`,
      { method: "POST" },
      (result) => showIssuedToken(client.id, result.token),
    );
  }
  function revokeToken(client) {
    if (
      !window.confirm(
        `Revoke the token for ${client.id}? New requests will be denied until a new token is issued.`,
      )
    )
      return;
    void mutate(
      `./clients/${encodeURIComponent(client.id)}/token`,
      { method: "DELETE" },
      clearIssuedToken,
    );
  }
  function deleteClient(client) {
    if (
      !window.confirm(
        `Delete ${client.id}? Access will be revoked immediately. Usage history is retained and this user ID cannot be reused.`,
      )
    )
      return;
    void mutate(
      `./clients/${encodeURIComponent(client.id)}`,
      { method: "DELETE" },
      () => {
        if (editingId === client.id) closeEditor();
        clearIssuedToken();
      },
    );
  }
  byId("client-form").addEventListener("submit", (event) => {
    event.preventDefault();
    if (mutating || !managed() || snapshot?.actor?.role === "viewer") return;
    const mode = byId("client-model-mode").value;
    const models = byId("client-models")
      .value.split(/\r?\n/)
      .map((value) => value.trim())
      .filter(Boolean);
    if (
      mode === "listed" &&
      (!models.length || new Set(models).size !== models.length)
    ) {
      byId("editor-message").textContent =
        "Enter one or more unique model IDs, one per line.";
      return;
    }
    const id = editingId ?? byId("client-id").value.trim();
    const body = {
      enabled: byId("client-enabled").value === "true",
      owner: byId("client-owner").value.trim(),
      tags: byId("client-tags")
        .value.split(/[,\s]+/)
        .filter(Boolean),
      default_model: byId("client-default-model").value.trim() || null,
      models: mode === "all" ? null : mode === "none" ? [] : models,
      limits: {
        max_concurrent_requests:
          byId("client-concurrency").value === ""
            ? null
            : Number(byId("client-concurrency").value),
        requests_per_minute:
          byId("client-rate").value === ""
            ? null
            : Number(byId("client-rate").value),
      },
      additional_middleware: [...middlewareOrder],
    };
    const creating = editingId === null;
    if (creating && !allowNewToken()) return;
    void mutate(
      creating ? "./clients" : `./clients/${encodeURIComponent(id)}`,
      {
        method: creating ? "POST" : "PUT",
        revision: editingRevision,
        body: creating ? { id, ...body } : body,
      },
      (result) => {
        closeEditor();
        if (creating) showIssuedToken(id, result.token);
      },
      "editor-message",
    );
  });
  byId("create-client").addEventListener("click", () => openEditor());
  byId("cancel-edit").addEventListener("click", closeEditor);
  byId("client-model-mode").addEventListener("change", updateModelField);
  byId("model-suggestion").addEventListener("change", () => {
    const selected = byId("model-suggestion").value;
    const models = byId("client-models")
      .value.split(/\r?\n/)
      .map((value) => value.trim())
      .filter(Boolean);
    if (selected && !models.includes(selected)) {
      models.push(selected);
      byId("client-models").value = models.join("\n");
    }
    byId("model-suggestion").value = "";
  });
  byId("add-middleware").addEventListener("click", () => {
    const name = byId("middleware-choice").value;
    if (!name || middlewareOrder.includes(name)) return;
    middlewareOrder.push(name);
    renderMiddlewareOrder();
    byId("middleware-choice").value = "";
  });
  byId("dismiss-token").addEventListener("click", clearIssuedToken);
  byId("reveal-token").addEventListener("click", () => {
    const reveal = byId("issued-token").type === "password";
    byId("issued-token").type = reveal ? "text" : "password";
    byId("reveal-token").textContent = reveal ? "Hide" : "Reveal";
  });
  byId("copy-token").addEventListener("click", async () => {
    const currentSession = session;
    const input = byId("issued-token");
    try {
      await navigator.clipboard.writeText(input.value);
      if (session === currentSession && !byId("issued-token-panel").hidden)
        byId("copy-token").textContent = "Copied";
    } catch {
      input.type = "text";
      byId("reveal-token").textContent = "Hide";
      input.focus();
      input.select();
      byId("copy-token").textContent = "Select & copy manually";
    }
  });
  async function filterUsage() {
    if (!managed() || filtering || !validateDates()) return;
    const currentSession = session;
    const loadId = ++latestLoad;
    const query = usageQuery();
    filtering = true;
    byId("apply-usage").disabled = byId("clear-usage").disabled = true;
    byId("usage-message").textContent = "";
    try {
      const usage = await request(`./usage${query}`);
      if (currentSession === session && loadId === latestLoad)
        renderUsage(usage);
    } catch (failure) {
      if (!ignorable(failure) && currentSession === session)
        byId("usage-message").textContent = failureMessage(failure);
    } finally {
      if (currentSession === session) {
        filtering = false;
        byId("apply-usage").disabled = byId("clear-usage").disabled = false;
      }
    }
  }
  byId("usage-filters").addEventListener("submit", (event) => {
    event.preventDefault();
    usageOffset = 0;
    void filterUsage();
  });
  byId("clear-usage").addEventListener("click", () => {
    byId("usage-filters").reset();
    usageOffset = 0;
    void filterUsage();
  });
  byId("export-usage").addEventListener("click", async () => {
    if (!managed() || exporting || !validateDates()) return;
    const currentSession = session;
    exporting = true;
    byId("export-usage").disabled = true;
    byId("usage-message").textContent = "";
    try {
      const blob = await request(`./usage/export${usageQuery()}`, {
        blob: true,
      });
      if (currentSession !== session) return;
      const url = URL.createObjectURL(blob);
      const anchor = element("a");
      anchor.href = url;
      anchor.download = "gateway7-usage.csv";
      document.body.append(anchor);
      anchor.click();
      anchor.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (failure) {
      if (!ignorable(failure) && currentSession === session)
        byId("usage-message").textContent = failureMessage(failure);
    } finally {
      if (currentSession === session) {
        exporting = false;
        byId("export-usage").disabled = false;
      }
    }
  });
  byId("connect-form").addEventListener("submit", (event) => {
    event.preventDefault();
    if (signingIn || loggingOut) return;
    const candidate = byId("operator-token").value;
    byId("operator-token").value = "";
    if (!/^[\x21-\x7e]{16,512}$/.test(candidate)) {
      byId("message").textContent =
        "Enter a valid operator token without spaces.";
      return;
    }
    disconnect();
    token = candidate;
    authentication = "token";
    csrfToken = "";
    void load();
  });
  byId("refresh").addEventListener("click", () => {
    void load();
  });
  async function logout() {
    const cookieSession = authentication === "session";
    const csrf = csrfToken;
    loggingOut = cookieSession;
    disconnect();
    byId("sign-in").disabled = cookieSession;
    if (!cookieSession) return;
    try {
      const response = await fetch("./session", {
        method: "DELETE",
        credentials: "same-origin",
        cache: "no-store",
        redirect: "error",
        headers: { "X-Gateway7-Operator": "true", "X-Gateway7-CSRF": csrf },
      });
      if (!response.ok && response.status !== 401)
        throw new Error("logout-failed");
    } catch {
      byId("message").textContent =
        "Could not confirm server sign-out. Close this browser session or try signing out again after reconnecting.";
    } finally {
      loggingOut = false;
      byId("sign-in").disabled = false;
    }
  }
  byId("disconnect").addEventListener("click", () => {
    void logout();
  });
  window.addEventListener("pagehide", disconnect);
  byId("client-directory-filters").addEventListener("submit", (event) => {
    event.preventDefault();
    clientOffset = 0;
    void load();
  });
  byId("previous-clients").addEventListener("click", () => {
    clientOffset = Math.max(0, clientOffset - 25);
    void load();
  });
  byId("next-clients").addEventListener("click", () => {
    clientOffset += 25;
    void load();
  });
  panels = createAdminWorkspace({
    request,
    reload: load,
    connected: () => snapshot !== null && authentication !== null,
    canWrite: () => managed() && snapshot?.actor?.role !== "viewer",
    showToken: showIssuedToken,
    rotateOperatorToken,
    actor: () => snapshot?.actor,
    clients: () => snapshot?.clients ?? [],
    go: (view) => navigation?.go(view),
    reauthenticate: () => {
      disconnect();
      byId("message").textContent =
        "Password changed. Sign in with your new password.";
    },
    setRevision: () => {},
    usagePage: (offset) => {
      usageOffset = offset;
      void filterUsage();
    },
  });
  navigation = createNavigation();
  byId("show-token-login").addEventListener("click", () => {
    if (signingIn || loggingOut) return;
    const open = byId("connect-form").hidden;
    byId("connect-form").hidden = !open;
    byId("show-token-login").setAttribute("aria-expanded", String(open));
    if (open) byId("operator-token").focus();
  });
  byId("show-password").addEventListener("click", () => {
    const show = byId("login-password").type === "password";
    byId("login-password").type = show ? "text" : "password";
    byId("show-password").textContent = show ? "Hide" : "Show";
    byId("show-password").setAttribute(
      "aria-label",
      show ? "Hide password" : "Show password",
    );
  });
  byId("issued-token-panel").addEventListener("keydown", (event) => {
    const controls = [
      ...byId("issued-token-panel").querySelectorAll("button,input"),
    ].filter((control) => !control.disabled);
    if (event.key === "Tab") {
      const first = controls[0],
        last = controls.at(-1);
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
    if (
      event.key === "Escape" &&
      window.confirm("Have you saved this one-time token? Dismiss its display?")
    )
      clearIssuedToken();
  });
  byId("login-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (loggingOut || signingIn) return;
    const password = byId("login-password").value;
    disconnect();
    const currentSession = session;
    signingIn = true;
    const controller = new AbortController();
    pending.add(controller);
    byId("sign-in").disabled = true;
    byId("sign-in").textContent = "Signing in…";
    byId("connect").disabled = true;
    byId("show-token-login").disabled = true;
    byId("message").textContent = "";
    try {
      const response = await fetch("./session", {
        method: "POST",
        credentials: "same-origin",
        cache: "no-store",
        redirect: "error",
        signal: controller.signal,
        headers: {
          "Content-Type": "application/json",
          "X-Gateway7-Operator": "true",
        },
        body: JSON.stringify({
          username: byId("login-username").value.trim(),
          password,
          remember: byId("login-remember").checked,
        }),
      });
      if (currentSession !== session) return;
      if (!response.ok) {
        byId("message").textContent =
          response.status === 429
            ? "Too many sign-in attempts. Please wait before trying again."
            : response.status === 403
              ? "Use the HTTPS gateway address to sign in. Ask your administrator if you need local development access."
              : response.status === 422
                ? "Check the sign-in fields and use your HTTPS gateway address. Ask your administrator if you need local development access."
                : response.status >= 500
                  ? "Sign-in is temporarily unavailable. Please try again shortly."
                  : "Could not sign in. Check your username and password.";
        return;
      }
      const result = await response.json();
      if (currentSession !== session) return;
      authentication = "session";
      csrfToken = result.csrf_token;
      token = "";
      await load();
    } catch {
      if (currentSession === session)
        byId("message").textContent =
          "The gateway could not be reached. Try signing in again.";
    } finally {
      pending.delete(controller);
      if (currentSession === session) {
        signingIn = false;
        byId("sign-in").disabled = false;
        byId("sign-in").textContent = "Sign in →";
        byId("connect").disabled = false;
        byId("show-token-login").disabled = false;
      }
    }
  });
  clearData();
  void (async () => {
    const currentSession = session;
    try {
      const response = await fetch("./session", {
        credentials: "same-origin",
        cache: "no-store",
        redirect: "error",
      });
      if (!response.ok || currentSession !== session || authentication !== null)
        return;
      const result = await response.json();
      if (currentSession !== session || authentication !== null) return;
      authentication = "session";
      csrfToken = result.csrf_token;
      await load();
    } catch {
      /* The sign-in form remains available when restoration fails. */
    }
  })();
})();
