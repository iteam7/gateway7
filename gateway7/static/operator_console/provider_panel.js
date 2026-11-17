"use strict";
import {
  node,
  field,
  button,
  panel,
  table,
  task,
  lines,
  dateLabel,
  statusText,
} from "./admin_forms.js";

export function providerPanel(context) {
  const view = panel(
    "provider-management",
    "Provider & models",
    "Configure the active provider, canonical model permissions, aliases and connection health.",
  );
  let current = null;
  const summary = node("div");
  const form = node("form", undefined, "admin-form");
  form.autocomplete = "off";
  const grid = node("div", undefined, "form-grid");
  const kind = field("Provider", {
    options: [
      ["openai", "OpenAI"],
      ["claude", "Anthropic Claude"],
      ["gemini", "Google Gemini"],
      ["fake", "Synthetic provider"],
    ],
    id: "provider-kind",
  });
  const origin = field("Provider origin", {
    type: "url",
    required: true,
    id: "provider-origin",
    help: "Use the provider's approved HTTPS origin. Custom upstream origins remain disabled.",
  });
  const model = field("Default canonical model", {
    required: true,
    id: "provider-model",
  });
  const mode = field("Gateway model access", {
    options: [
      ["listed", "Only listed canonical models"],
      ["all", "All models available to the provider account"],
      ["none", "Deny all model access"],
    ],
    id: "provider-model-mode",
  });
  const models = field("Allowed canonical model IDs", {
    multiline: true,
    id: "provider-models",
    help: "One ID per line. User permissions are intersected with this list.",
  });
  const aliases = field("Model aliases", {
    multiline: true,
    id: "provider-aliases",
    help: "One alias=canonical-model per line. Alias chains are not allowed.",
  });
  const timeout = field("Provider timeout, seconds", {
    type: "number",
    min: 0.1,
    max: 300,
    step: 0.1,
    required: true,
    id: "provider-timeout",
  });
  const concurrency = field("Gateway concurrent requests", {
    type: "number",
    min: 1,
    max: 10000,
    step: 1,
    required: true,
    id: "provider-concurrency",
  });
  const credential = field("New provider API key", {
    type: "password",
    id: "provider-credential",
    help: "Leave empty to retain the current key. Supplied keys are encrypted on the server and are never shown again.",
  });
  grid.append(
    kind.root,
    origin.root,
    model.root,
    mode.root,
    models.root,
    aliases.root,
    timeout.root,
    concurrency.root,
    credential.root,
  );
  const notice = node("p", undefined, "panel-note");
  const actions = node("div", undefined, "form-actions");
  const save = node("button", "Save provider configuration", "button primary");
  save.type = "submit";
  save.id = "save-provider";
  const test = button(
    "Test connection",
    async () => {
      await task(form, view.message, async () => {
        const result = await context.request("./provider/test", {
          method: "POST",
          body: values(),
        });
        credential.input.value = "";
        context.setRevision(result.revision);
        await load();
        view.message.textContent =
          result.status === "reachable"
            ? "Connection check succeeded."
            : "The provider connection check failed.";
      });
    },
    { id: "test-provider" },
  );
  actions.append(save, test);
  form.append(grid, notice, actions);
  const registry = node("div");
  const refresh = button("Refresh model catalog", () => void loadModels(true), {
    id: "refresh-model-catalog",
  });
  view.content.append(summary, form, refresh, registry);
  function values() {
    const mapping = {};
    for (const entry of lines(aliases.input.value)) {
      const separator = entry.indexOf("=");
      if (separator < 1 || !entry.slice(separator + 1).trim())
        throw new Error("rejected");
      const name = entry.slice(0, separator).trim();
      if (Object.hasOwn(mapping, name)) throw new Error("rejected");
      mapping[name] = entry.slice(separator + 1).trim();
    }
    return {
      kind: kind.input.value,
      base_url: origin.input.value.trim(),
      model: model.input.value.trim(),
      allowed_models:
        mode.input.value === "all"
          ? null
          : mode.input.value === "none"
            ? []
            : lines(models.input.value),
      timeout_seconds: Number(timeout.input.value),
      max_concurrent_requests: Number(concurrency.input.value),
      aliases: mapping,
      ...(credential.input.value ? { credential: credential.input.value } : {}),
    };
  }
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    void task(form, view.message, async () => {
      const result = await context.request("./provider", {
        method: "PUT",
        body: values(),
        revision: current.revision,
      });
      credential.input.value = "";
      context.setRevision(result.revision);
      await context.reload();
      view.message.textContent =
        "Provider settings saved. New requests use this configuration.";
    });
  });
  kind.input.addEventListener("change", () => {
    const defaults = {
      openai: "https://api.openai.com",
      claude: "https://api.anthropic.com",
      gemini: "https://generativelanguage.googleapis.com",
      fake: "http://127.0.0.1:8001",
    };
    origin.input.value = defaults[kind.input.value];
  });
  mode.input.addEventListener("change", () => {
    models.root.hidden = mode.input.value !== "listed";
  });
  async function loadModels(force = false) {
    try {
      const result = await context.request(
        `./models${force ? "?refresh=true" : ""}`,
      );
      if (!context.connected()) return;
      registry.replaceChildren(
        node(
          "p",
          `${result.source === "provider_catalog" ? "Provider account catalog" : "Configured model registry"} · ${result.refreshed_at ? `refreshed ${dateLabel(result.refreshed_at)}` : "not verified against the provider"}${result.error ? " · catalog unavailable" : ""}`,
          "panel-note",
        ),
        table(
          ["Canonical model", "Aliases", "Gateway access", "Availability"],
          (result.items ?? []).map((item) => [
            item.id,
            (item.aliases ?? []).join(", ") || "—",
            item.globally_allowed
              ? item.is_default
                ? "Allowed · default"
                : "Allowed"
              : "Denied",
            item.availability,
          ]),
        ),
        node(
          "p",
          "Catalog membership does not guarantee that every request can run. User permissions and request capabilities still apply.",
          "panel-note",
        ),
      );
    } catch (error) {
      if (context.connected()) view.message.textContent = statusText(error);
    }
  }
  async function load() {
    current = await context.request("./provider");
    if (!context.connected()) return;
    const data = current.provider;
    context.setRevision(current.revision);
    kind.input.value = data.kind;
    origin.input.value = data.base_url;
    model.input.value = data.model;
    mode.input.value =
      data.allowed_models === null
        ? "all"
        : data.allowed_models.length
          ? "listed"
          : "none";
    models.input.value = (data.allowed_models ?? []).join("\n");
    models.root.hidden = mode.input.value !== "listed";
    aliases.input.value = Object.entries(data.aliases ?? {})
      .map(([alias, target]) => `${alias}=${target}`)
      .join("\n");
    timeout.input.value = data.timeout_seconds;
    concurrency.input.value = data.max_concurrent_requests;
    credential.input.value = "";
    notice.textContent = `Saving validates the connection before switching. Connection checks may send a tiny synthetic request to Claude, Gemini or a synthetic provider; provider charges may apply.${data.credential_writes_available ? "" : " New key storage requires the server's encryption key to be configured."}`;
    const health = current.health;
    summary.replaceChildren(
      table(
        [
          "Provider",
          "Default model",
          "Credential",
          "Last explicit connection check",
        ],
        [
          [
            data.kind,
            data.model,
            data.credential_configured
              ? "Configured · value hidden"
              : "Missing",
            `${health.status} · ${dateLabel(health.checked_at)}${health.latency_ms === undefined ? "" : ` · ${health.latency_ms} ms`}`,
          ],
        ],
      ),
    );
    form.hidden = !context.canWrite();
    await loadModels();
  }
  function clear() {
    current = null;
    credential.input.value = "";
    form.reset();
    summary.replaceChildren();
    registry.replaceChildren();
    view.message.textContent = "";
  }
  return { root: view.root, load, clear };
}
