"use strict";

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
  let pending = null;
  let generation = 0;

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
    );
    wrapper.append(element("span", name));
    target.append(wrapper);
  }

  function pills(target, values) {
    const wrapper = element("div", undefined, "pills");
    for (const value of values) wrapper.append(element("span", value, "pill"));
    if (!values.length)
      wrapper.append(element("span", "None configured", "secondary-line"));
    target.append(wrapper);
  }

  function clearData() {
    for (const id of ["clients-body", "usage-body", "plugins-body", "chains"])
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
    ])
      byId(id).textContent = "";
    byId("dashboard").hidden = true;
    byId("connected-actions").hidden = true;
  }

  function disconnect() {
    generation += 1;
    if (pending) pending.abort();
    pending = null;
    token = "";
    byId("operator-token").value = "";
    byId("connection-panel").hidden = false;
    byId("connect").disabled = false;
    byId("refresh").disabled = false;
    byId("message").textContent = "";
    clearData();
  }

  function render(state, usage) {
    if (
      !Array.isArray(state.clients) ||
      !Array.isArray(state.middleware.plugins) ||
      usage.scope !== "process_lifetime" ||
      usage.reset_on_restart !== true ||
      !usage.clients ||
      typeof usage.clients !== "object"
    )
      throw new Error("invalid-state");
    const clients = state.clients;
    const plugins = state.middleware.plugins;
    const accounts = Object.entries(usage.clients);
    const totals = accounts.reduce(
      (total, [, account]) => ({
        attempts: total.attempts + number(account.provider_attempts),
        input: total.input + number(account.known_input_tokens),
        output: total.output + number(account.known_output_tokens),
      }),
      { attempts: 0, input: 0, output: 0 },
    );
    byId("client-count").textContent = formatted(clients.length);
    const enabled = clients.filter((client) => client.enabled).length;
    byId("client-summary").textContent =
      `${enabled} enabled · ${clients.length - enabled} suspended`;
    byId("attempt-count").textContent = formatted(totals.attempts);
    byId("token-count").textContent = formatted(totals.input + totals.output);
    byId("token-summary").textContent =
      `${formatted(totals.input)} input · ${formatted(totals.output)} output`;
    byId("plugin-count").textContent = formatted(
      plugins.filter((plugin) => plugin.in_chain).length,
    );
    byId("plugin-summary").textContent =
      `${plugins.length} configured instances`;
    byId("shared-limit").textContent =
      `Shared concurrency cap: ${formatted(state.gateway.max_concurrent_requests)}`;
    const started = new Date(usage.started_at);
    byId("usage-window").textContent = Number.isNaN(started.getTime())
      ? "Current process counters"
      : `Process started ${started.toLocaleString()}`;

    const clientBody = byId("clients-body");
    clientBody.replaceChildren();
    for (const client of clients) {
      const row = element("tr");
      clientName(cell(row), client.id);
      cell(row).append(
        badge(
          client.enabled ? "Enabled" : "Suspended",
          client.enabled ? "active" : "suspended",
        ),
      );
      pills(cell(row), client.models);
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
          ? "No client rate cap"
          : formatted(client.limits.requests_per_minute),
        "numeric",
      );
      clientBody.append(row);
    }

    const usageBody = byId("usage-body");
    usageBody.replaceChildren();
    for (const [clientId, account] of accounts) {
      const row = element("tr");
      cell(row, clientId);
      cell(row, formatted(account.provider_attempts), "numeric");
      const outcomes = cell(row);
      outcomes.append(
        element(
          "span",
          `${formatted(account.outcomes.complete)} complete`,
          "good",
        ),
      );
      outcomes.append(
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
      usageBody.append(row);
    }

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
        element("span", "Validated at startup", "secondary-line"),
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
    for (const [id, count, columns] of [
      ["clients-body", clients.length, 5],
      ["usage-body", accounts.length, 5],
      ["plugins-body", plugins.length, 5],
    ]) {
      if (!count) {
        const row = element("tr");
        const placeholder = cell(
          row,
          "Nothing configured for this section",
          "empty-row",
        );
        placeholder.colSpan = columns;
        byId(id).append(row);
      }
    }
    byId("refreshed-at").textContent =
      `Updated ${new Date().toLocaleTimeString()}`;
  }

  async function load() {
    const currentGeneration = ++generation;
    if (pending) pending.abort();
    const controller = new AbortController();
    pending = controller;
    byId("message").textContent = "";
    byId("connect").disabled = true;
    byId("refresh").disabled = true;
    try {
      const headers = { Authorization: `Bearer ${token}` };
      const response = await fetch("./state", {
        method: "GET",
        headers,
        credentials: "omit",
        cache: "no-store",
        redirect: "error",
        signal: controller.signal,
      });
      if (!response.ok) {
        const code = response.status;
        throw new Error(
          code === 401
            ? "unauthorized"
            : code === 404
              ? "unavailable"
              : "request-failed",
        );
      }
      const state = await response.json();
      if (currentGeneration !== generation || controller.signal.aborted) return;
      render(state, state.usage);
      byId("connection-panel").hidden = true;
      byId("dashboard").hidden = false;
      byId("connected-actions").hidden = false;
    } catch (failure) {
      if (currentGeneration !== generation || controller.signal.aborted) return;
      const reason =
        failure instanceof Error ? failure.message : "request-failed";
      disconnect();
      byId("message").textContent =
        reason === "unauthorized"
          ? "The operator token was not accepted."
          : reason === "unavailable"
            ? "Operator access is unavailable on this gateway."
            : "Could not load gateway state. Check the connection and try again.";
    } finally {
      if (currentGeneration === generation) {
        pending = null;
        byId("connect").disabled = false;
        byId("refresh").disabled = false;
      }
    }
  }

  byId("connect-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const candidate = byId("operator-token").value;
    byId("operator-token").value = "";
    if (!/^[\x21-\x7e]{16,512}$/.test(candidate)) {
      byId("message").textContent =
        "Enter a valid operator token without spaces.";
      return;
    }
    token = candidate;
    void load();
  });
  byId("refresh").addEventListener("click", () => {
    void load();
  });
  byId("disconnect").addEventListener("click", disconnect);
  window.addEventListener("pagehide", disconnect);
  clearData();
})();
