"use strict";
import {
  button,
  field,
  lines,
  node,
  panel,
  statusText,
  table,
} from "./admin_forms.js";

const templates = [
  ["phone_mask", "Mask phone numbers"],
  ["email_mask", "Mask email addresses"],
  ["literal_guard", "Block matching text"],
  ["literal_redact", "Redact matching text"],
];
const examples = [
  { kind: "positive", text: "Fictional contact: +7 000 000-00-00." },
  { kind: "negative", text: "No contact number here." },
  { kind: "boundary", text: "Incomplete number: +7 000 000-00-0." },
];

export function pluginPanel(context) {
  const view = panel(
    "plugin-workspace",
    "Draft plugin chain",
    "Edit and test this chain before activating it for gateway traffic.",
  );
  const base = "./plugin-draft";
  let items = [],
    cases = [],
    revision = null,
    editing = null;
  let configured = [],
    managedChain = [],
    deploymentDisabled = [],
    hasSaved = false,
    isActive = false;
  let dirty = false,
    busy = false,
    session = 0,
    formDirty = false;
  const mandatory = node("p", undefined, "field-help");
  const state = node("p", undefined, "status-line");
  const chain = node("div");
  const baseline = node("div");
  const managed = node("div");
  const form = node("form", undefined, "admin-form");
  const id = field("Plugin ID", { required: true, id: "draft-id" });
  id.input.pattern = "[A-Za-z][A-Za-z0-9_.\\-]{0,55}";
  const label = field("Name", { required: true, id: "draft-label" });
  label.input.maxLength = 64;
  const template = field("Template", {
    options: templates,
    value: "phone_mask",
    id: "draft-template",
  });
  const phase = field("Apply to", {
    options: [
      ["request", "Requests"],
      ["response", "Responses"],
      ["both", "Both"],
    ],
    value: "request",
  });
  const terms = field("Literal terms (one per line)", { multiline: true });
  const replacement = field("Replacement text", { value: "[PHONE]" });
  replacement.input.maxLength = 128;
  const add = node("button", "Add to draft", "button primary");
  add.type = "submit";
  const reset = button("Clear editor", () => {
    resetEditor();
    render();
  });
  const formActions = node("div", undefined, "form-actions");
  formActions.append(add, reset);
  form.append(
    id.root,
    label.root,
    template.root,
    phase.root,
    terms.root,
    replacement.root,
    formActions,
  );
  function syncTemplate() {
    terms.root.hidden = !template.input.value.startsWith("literal_");
    terms.input.required = !terms.root.hidden;
    replacement.root.hidden = template.input.value === "literal_guard";
    if (
      ["", "[PHONE]", "[EMAIL]", "[REDACTED]"].includes(replacement.input.value)
    )
      replacement.input.value =
        { phone_mask: "[PHONE]", email_mask: "[EMAIL]" }[
          template.input.value
        ] ?? "[REDACTED]";
  }
  form.addEventListener("input", () => {
    formDirty = true;
    syncButtons();
  });
  template.input.addEventListener("change", syncTemplate);
  function resetEditor() {
    editing = null;
    formDirty = false;
    form.reset();
    template.input.value = "phone_mask";
    phase.input.value = "request";
    replacement.input.value = "[PHONE]";
    add.textContent = "Add to draft";
    syncTemplate();
  }
  function fillEditor(spec, existing) {
    editing = existing ? spec.id : null;
    id.input.value = spec.id;
    label.input.value = spec.label;
    template.input.value = spec.template;
    phase.input.value = spec.phase;
    syncTemplate();
    terms.input.value = (spec.terms ?? []).join("\n");
    replacement.input.value = spec.replacement ?? "";
    formDirty = !existing;
    add.textContent = existing ? "Update draft plugin" : "Add to draft";
    syncButtons();
  }
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const spec = {
      id: id.input.value.trim(),
      label: label.input.value.trim(),
      template: template.input.value,
      phase: phase.input.value,
    };
    if (!terms.root.hidden) spec.terms = lines(terms.input.value);
    if (!replacement.root.hidden && replacement.input.value)
      spec.replacement = replacement.input.value;
    if (editing === null && items.some((item) => item.spec.id === spec.id)) {
      view.message.textContent = "Choose a unique plugin ID.";
      return;
    }
    if (editing === null) items.push({ spec, enabled: true });
    else items.find((item) => item.spec.id === editing).spec = spec;
    resetEditor();
    changed();
  });
  const description = field("Describe a plugin using synthetic details only", {
    multiline: true,
    id: "draft-description",
  });
  description.input.maxLength = 512;
  const generate = button("Generate editable plugin", () =>
    run(async () => {
      const result = await context.request("./policy-draft/generate", {
        method: "POST",
        revision,
        body: { description: description.input.value.trim() },
      });
      fillEditor(result.spec, false);
    }, true),
  );
  const generateCases = button("Generate test cases", () =>
    run(async () => {
      const result = await context.request("./policy-draft/generate-cases", {
        method: "POST",
        revision,
        body: {
          template: template.input.value,
          ...(template.input.value.startsWith("literal_") &&
          lines(terms.input.value)[0]
            ? { term: lines(terms.input.value)[0] }
            : {}),
        },
      });
      setCases(result.cases);
    }, true),
  );
  const ai = node("details");
  ai.append(
    node("summary", "Generate with a configured local model"),
    description.root,
    generate,
    generateCases,
  );
  const testPhase = field("Test phase", {
    options: [
      ["request", "Request"],
      ["response", "Response"],
    ],
    value: "request",
  });
  const samples = node("div");
  const result = node("div");
  result.setAttribute("aria-live", "polite");
  const demo = button("Load phone examples", () => setCases(examples));
  function setCases(values) {
    cases = values.map((value) => ({ ...value }));
    samples.replaceChildren();
    for (const item of cases) {
      const sample = field(item.kind + " input", {
        multiline: true,
        value: item.text,
      });
      sample.input.maxLength = 8192;
      sample.input.addEventListener("input", () => {
        item.text = sample.input.value;
        result.replaceChildren();
      });
      samples.append(sample.root);
    }
    result.replaceChildren();
  }
  testPhase.input.addEventListener("change", () => result.replaceChildren());
  const preview = button(
    "Test draft chain",
    () =>
      run(async () => {
        result.replaceChildren();
        for (const item of cases) {
          const trace = await context.request(base + "/preview", {
            method: "POST",
            revision,
            body: {
              items,
              configured,
              managed_chain: managedChain,
              text: item.text,
              phase: testPhase.input.value,
            },
          });
          result.append(
            node("h4", item.kind + " result"),
            table(
              ["Input", "Output", "Error"],
              [[trace.input, trace.output, trace.error]],
            ),
            table(
              ["Plugin", "Status", "Input", "Output", "Error"],
              trace.steps.map((step) => [
                step.id,
                step.status,
                step.input,
                step.output,
                step.error,
              ]),
              "No draft steps ran.",
            ),
          );
        }
      }),
    { id: "test-draft-chain" },
  );
  const save = button(
    "Save draft",
    () =>
      run(async () => {
        apply(
          await context.request(base, {
            method: "PUT",
            revision,
            body: { items, configured, managed_chain: managedChain },
          }),
        );
        view.message.textContent = "Draft saved.";
        await context.reload();
      }),
    { id: "save-plugin-draft" },
  );
  const activate = button(
    "Activate saved chain",
    () => {
      if (!window.confirm("Apply the saved plugin chain to gateway traffic?"))
        return;
      void run(async () => {
        apply(
          await context.request(base + "/activate", {
            method: "POST",
            revision,
            body: {},
          }),
        );
        view.message.textContent = "Saved chain activated.";
        await context.reload();
      });
    },
    { id: "activate-plugin-draft", primary: true },
  );
  const reload = button("Reload saved draft", () => {
    if (
      (dirty || formDirty) &&
      !window.confirm("Discard local edits and reload the saved draft?")
    )
      return;
    void run(async () => {
      apply(await context.request(base));
      resetEditor();
      result.replaceChildren();
    });
  });
  function changed() {
    dirty = true;
    view.message.textContent = "";
    result.replaceChildren();
    render();
  }
  function syncButtons() {
    const locked = busy || !context.canWrite() || revision === null;
    for (const control of view.root.querySelectorAll(
      "button,input,textarea,select",
    ))
      control.disabled = locked;
    id.input.disabled = locked || editing !== null;
    save.disabled = locked || !dirty || formDirty;
    activate.disabled = locked || dirty || formDirty || !hasSaved || isActive;
    preview.disabled = locked || formDirty;
    generate.disabled = locked || !description.input.value.trim();
    for (const control of view.root.querySelectorAll("[data-boundary]"))
      control.disabled = true;
  }
  description.input.addEventListener("input", syncButtons);
  async function run(operation, generation = false) {
    if (busy || !context.canWrite()) return;
    const token = session;
    busy = true;
    view.message.textContent = "";
    syncButtons();
    try {
      await operation();
    } catch (error) {
      if (
        session === token &&
        error?.name !== "AbortError" &&
        error?.message !== "stale-session"
      )
        view.message.textContent =
          generation && error?.message === "request-failed"
            ? "Generation unavailable. Check the local model configuration or enter the draft manually."
            : statusText(error);
    } finally {
      if (session === token) {
        busy = false;
        render();
      }
    }
  }
  function renderSegment(container, heading, entries, lockedIds = []) {
    const rows = entries.map((item, index) => {
      const actions = node("div", undefined, "form-actions");
      if (!item.required) {
        for (const [label, delta] of [
          ["Up", -1],
          ["Down", 1],
        ]) {
          const next = index + delta;
          const move = button(label, () => {
            [entries[index], entries[next]] = [entries[next], entries[index]];
            changed();
          });
          if (!entries[next] || entries[next].required)
            move.dataset.boundary = "true";
          actions.append(move);
        }
        const toggle = button(item.enabled ? "Disable" : "Enable", () => {
          item.enabled = !item.enabled;
          changed();
        });
        if (lockedIds.includes(item.id)) toggle.dataset.boundary = "true";
        actions.append(toggle);
      }
      return [
        index + 1,
        item.id,
        item.required
          ? "Required"
          : lockedIds.includes(item.id)
            ? "Disabled by deployment"
            : item.enabled
              ? "Enabled"
              : "Disabled",
        actions,
      ];
    });
    container.replaceChildren();
    if (rows.length)
      container.append(
        node("h4", heading),
        table(["Order", "Plugin", "Status", "Actions"], rows),
      );
  }
  function render() {
    renderSegment(
      baseline,
      "Server-configured plugins",
      configured,
      deploymentDisabled,
    );
    renderSegment(managed, "Assigned global policies", managedChain);
    const rows = items.map((item, index) => {
      const actions = node("div", undefined, "form-actions");
      const move = (delta) => {
        const next = index + delta;
        [items[index], items[next]] = [items[next], items[index]];
        changed();
      };
      const up = button("Up", () => move(-1)),
        down = button("Down", () => move(1));
      if (!index) up.dataset.boundary = "true";
      if (index + 1 === items.length) down.dataset.boundary = "true";
      actions.append(
        button("Edit", () => fillEditor(item.spec, true)),
        up,
        down,
        button(item.enabled ? "Disable" : "Enable", () => {
          item.enabled = !item.enabled;
          changed();
        }),
        button("Remove", () => {
          items.splice(index, 1);
          if (editing === item.spec.id) resetEditor();
          changed();
        }),
      );
      return [
        String(index + 1),
        item.spec.label + " (" + item.spec.id + ")",
        item.enabled ? "Enabled" : "Disabled",
        actions,
      ];
    });
    chain.replaceChildren(
      table(
        ["Order", "Plugin", "Status", "Actions"],
        rows,
        "The draft chain is empty.",
      ),
    );
    state.textContent = formDirty
      ? "Add or update the plugin to include your editor changes."
      : dirty
        ? "Draft has unsaved changes."
        : revision === null
          ? ""
          : isActive
            ? "Saved draft matches the active chain."
            : hasSaved
              ? "Saved draft is awaiting activation."
              : "No draft saved yet.";
    syncButtons();
  }
  function apply(document) {
    items = document.items;
    configured = document.configured;
    deploymentDisabled = document.deployment_disabled ?? [];
    managedChain = document.managed_chain ?? [];
    hasSaved = document.has_saved;
    isActive = document.is_active;
    revision = document.revision;
    dirty = false;
    mandatory.textContent = document.mandatory?.length
      ? "Required gateway steps: " + document.mandatory.join(", ")
      : "";
    render();
  }
  const actions = node("div", undefined, "form-actions");
  actions.append(save, activate, reload);
  view.content.append(
    mandatory,
    node("h3", "Create or edit a plugin"),
    ai,
    form,
    node("h3", "Draft order"),
    baseline,
    managed,
    chain,
    state,
    actions,
    node("h3", "Test synthetic input"),
    node(
      "p",
      "Use fictional text. An unsupported plugin stops the preview at its step.",
      "field-help",
    ),
    testPhase.root,
    demo,
    samples,
    preview,
    result,
  );
  resetEditor();
  setCases([{ kind: "Sample", text: "Fictional contact: +7 000 000-00-00." }]);
  return {
    root: view.root,
    async load() {
      const token = session;
      const document = await context.request(base);
      if (
        session === token &&
        !dirty &&
        !formDirty &&
        !busy &&
        document.revision >= (revision ?? 0)
      )
        apply(document);
    },
    clear() {
      session++;
      busy = false;
      dirty = false;
      revision = null;
      items = [];
      configured = [];
      deploymentDisabled = [];
      isActive = false;
      hasSaved = false;
      managedChain = [];
      mandatory.textContent = "";
      description.input.value = "";
      view.message.textContent = "";
      resetEditor();
      setCases([{ kind: "Sample", text: "" }]);
      render();
    },
  };
}
