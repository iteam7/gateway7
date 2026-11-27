"use strict";
import {
  node,
  field,
  button,
  panel,
  table,
  task,
  lines,
} from "./admin_forms.js";

export function policyPanel(context) {
  const view = panel(
    "policy-management",
    "Policy builder",
    "Choose a template, check it on sample text, then assign it to your gateway or a user.",
  );
  let current = null;
  let editorRevision = null;
  let editing = null;
  let editorDirty = false;
  let assignmentDocument = null;
  let assignmentDirty = false;
  let order = [];
  const list = node("div", undefined, "policy-list");
  const workspace = node("div", undefined, "policy-workspace");
  const form = node("form", undefined, "admin-form");
  const id = field("Policy ID", {
    required: true,
    id: "policy-id",
    help: "A stable name using letters, numbers, underscores or hyphens.",
  });
  id.input.pattern = "[A-Za-z][A-Za-z0-9_.-]{0,55}";
  id.input.maxLength = 56;
  const label = field("Policy name", { required: true, id: "policy-label" });
  label.input.maxLength = 64;
  const template = field("Template", {
    options: [
      ["literal_guard", "Block matching text"],
      ["literal_redact", "Redact matching text"],
      ["email_mask", "Mask email addresses"],
      ["phone_mask", "Mask phone numbers"],
    ],
    id: "policy-template",
  });
  const phase = field("Apply to", {
    options: [
      ["request", "Incoming requests"],
      ["response", "Outgoing responses"],
      ["both", "Requests and responses"],
    ],
    id: "policy-phase",
  });
  const terms = field("Text to match", {
    multiline: true,
    required: true,
    id: "policy-terms",
    help: "One literal term per line, up to 32 terms. No regular expressions or code.",
  });
  const replacement = field("Replacement text", {
    value: "[REDACTED]",
    id: "policy-replacement",
  });
  replacement.input.maxLength = 128;
  const save = node("button", "Create policy", "button primary");
  save.id = "save-policy";
  save.type = "submit";
  const editorActions = node("div", undefined, "form-actions");
  editorActions.append(save, button("New policy", resetEditor));
  const phaseNote = node(
    "small",
    "Response policies require buffered responses. Sample text does not test tools or protocol compatibility.",
    "field-help full-width",
  );
  form.append(
    id.root,
    label.root,
    template.root,
    phase.root,
    terms.root,
    replacement.root,
    phaseNote,
    editorActions,
  );
  form.addEventListener("input", () => {
    if (!editorDirty) editorRevision = current?.revision;
    editorDirty = true;
  });
  function syncTemplate() {
    const literal = template.input.value.startsWith("literal_");
    terms.root.hidden = !literal;
    terms.input.required = literal;
    replacement.root.hidden = template.input.value === "literal_guard";
    if (
      ["", "[REDACTED]", "[EMAIL]", "[PHONE]"].includes(replacement.input.value)
    )
      replacement.input.value =
        template.input.value === "email_mask"
          ? "[EMAIL]"
          : template.input.value === "phone_mask"
            ? "[PHONE]"
            : "[REDACTED]";
    const allowed = current?.templates.find(
      (item) => item.id === template.input.value,
    )?.phases ?? ["request", "response", "both"];
    for (const option of phase.input.options)
      option.disabled = !allowed.includes(option.value);
    if (!allowed.includes(phase.input.value)) phase.input.value = allowed[0];
  }
  template.input.addEventListener("change", syncTemplate);
  function resetEditor() {
    editing = null;
    editorDirty = false;
    editorRevision = current?.revision;
    form.reset();
    replacement.input.value = "[REDACTED]";
    id.input.disabled = false;
    save.textContent = "Create policy";
    syncTemplate();
  }
  function specification() {
    return {
      id: id.input.value.trim(),
      label: label.input.value.trim(),
      template: template.input.value,
      phase: phase.input.value,
      ...(template.input.value.startsWith("literal_")
        ? { terms: lines(terms.input.value) }
        : {}),
      ...(template.input.value !== "literal_guard"
        ? { replacement: replacement.input.value }
        : {}),
    };
  }
  const preview = node("div", undefined, "policy-preview");
  preview.append(
    node("h3", "Try sample text"),
    node(
      "p",
      "A local policy check. Nothing is sent to your model provider.",
      "field-help",
    ),
  );
  const sample = field("Sample text", {
    multiline: true,
    id: "policy-sample",
    value: "A synthetic example to check before you save.",
  });
  sample.input.maxLength = 8192;
  const previewMessage = node("p", undefined, "message");
  previewMessage.setAttribute("role", "status");
  const output = node("div", "Your result will appear here.", "preview-output");
  output.id = "policy-preview-output";
  output.setAttribute("role", "status");
  const previewActions = node("div", undefined, "form-actions");
  previewActions.append(
    button(
      "Test policy",
      () => {
        if (!form.reportValidity()) return;
        void task(form, previewMessage, async () => {
          const result = await context.request("./policy-preview", {
            method: "POST",
            revision: editorRevision,
            body: { spec: specification(), text: sample.input.value },
          });
          output.textContent = result.denied
            ? `Blocked · ${result.matched} match${result.matched === 1 ? "" : "es"}. No provider call.`
            : `${result.text}\n\n${result.matched} match${result.matched === 1 ? "" : "es"} · No provider call.`;
        });
      },
      { id: "preview-policy" },
    ),
  );
  preview.append(sample.root, previewActions, previewMessage, output);
  const editor = node("div");
  editor.append(node("h3", "Create or edit a policy"), form);
  workspace.append(editor, preview);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    void task(form, view.message, async () => {
      await context.request(
        editing ? `./policies/${encodeURIComponent(editing)}` : "./policies",
        {
          method: editing ? "PUT" : "POST",
          revision: editorRevision,
          body: specification(),
        },
      );
      editorDirty = false;
      await context.reload();
      resetEditor();
    }).finally(() => {
      id.input.disabled = editing !== null;
    });
  });
  const assignment = node("section", undefined, "field-section");
  assignment.append(
    node("h3", "Assign policies"),
    node(
      "p",
      "Policies run in the order shown. Existing server-configured middleware stays in place.",
      "field-help",
    ),
  );
  const assignmentForm = node("form", undefined, "admin-form");
  const target = field("Apply policies to", {
    options: [
      ["global", "Every user (gateway baseline)"],
      ["client", "One user (after the baseline)"],
    ],
    id: "policy-assignment-target",
  });
  const user = field("User ID", {
    id: "policy-assignment-user",
    help: "Enter the exact user ID.",
  });
  const choice = field("Add a policy", {
    options: [["", "Choose a policy"]],
    id: "policy-assignment-choice",
  });
  const ordered = node("ol", undefined, "middleware-order full-width");
  ordered.id = "policy-assignment-order";
  const assignmentMessage = node("p", undefined, "message full-width");
  assignmentMessage.setAttribute("role", "status");
  const add = button(
    "Add policy",
    () => {
      if (!choice.input.value || order.includes(choice.input.value)) return;
      order.push(choice.input.value);
      assignmentDirty = true;
      renderOrder();
    },
    { id: "add-policy-assignment" },
  );
  const saveAssignments = node("button", "Save assignments", "button primary");
  saveAssignments.id = "save-policy-assignments";
  saveAssignments.type = "submit";
  assignmentForm.append(
    target.root,
    user.root,
    choice.root,
    add,
    ordered,
    assignmentMessage,
    saveAssignments,
  );
  function renderOrder() {
    ordered.replaceChildren();
    if (!order.length)
      ordered.append(node("li", "No managed policies assigned.", "field-help"));
    order.forEach((policyId, index) => {
      const row = node("li");
      row.append(
        node(
          "span",
          current?.items.find((item) => item.id === policyId)?.label ??
            policyId,
        ),
      );
      const up = button("Move up", () => {
        [order[index - 1], order[index]] = [order[index], order[index - 1]];
        assignmentDirty = true;
        renderOrder();
      });
      const down = button("Move down", () => {
        [order[index + 1], order[index]] = [order[index], order[index + 1]];
        assignmentDirty = true;
        renderOrder();
      });
      up.disabled = index === 0;
      down.disabled = index === order.length - 1;
      row.append(
        up,
        down,
        button("Remove", () => {
          order.splice(index, 1);
          assignmentDirty = true;
          renderOrder();
        }),
      );
      ordered.append(row);
    });
  }
  function selectAssignment() {
    user.root.hidden = target.input.value !== "client";
    user.input.required = target.input.value === "client";
    assignmentDocument = current ? structuredClone(current) : null;
    order = [
      ...(target.input.value === "global"
        ? (current?.global ?? [])
        : (current?.clients[user.input.value.trim()] ?? [])),
    ];
    assignmentDirty = false;
    renderOrder();
  }
  target.input.addEventListener("change", selectAssignment);
  user.input.addEventListener("change", selectAssignment);
  assignmentForm.addEventListener("submit", (event) => {
    event.preventDefault();
    void task(assignmentForm, assignmentMessage, async () => {
      const global = [...assignmentDocument.global];
      const clients = structuredClone(assignmentDocument.clients);
      if (target.input.value === "global")
        global.splice(0, global.length, ...order);
      else clients[user.input.value.trim()] = [...order];
      await context.request("./policy-assignments", {
        method: "PUT",
        revision: assignmentDocument.revision,
        body: { global, clients },
      });
      assignmentDirty = false;
      await context.reload();
    }).finally(renderOrder);
  });
  assignment.append(assignmentForm);
  const note = node(
    "p",
    "Server-configured middleware remains available below. Custom modules are managed in server configuration; this builder edits only the four supported policy templates.",
    "inline-notice",
  );
  view.content.append(list, workspace, assignment, note);
  async function load() {
    current = await context.request("./policies");
    if (!context.connected()) return;
    workspace.hidden = assignment.hidden = !context.canWrite();
    list.replaceChildren(
      table(
        ["Policy", "Template", "Applies to", "Actions"],
        current.items.map((item) => {
          const actions = node("div", undefined, "row-actions");
          if (context.canWrite())
            actions.append(
              button("Edit", () => {
                editing = item.id;
                editorRevision = current.revision;
                editorDirty = true;
                id.input.value = item.id;
                id.input.disabled = true;
                label.input.value = item.label;
                template.input.value = item.template;
                phase.input.value = item.phase;
                terms.input.value = (item.terms ?? []).join("\n");
                replacement.input.value = item.replacement ?? "[REDACTED]";
                save.textContent = "Save policy";
                syncTemplate();
                form.scrollIntoView({ block: "start" });
                label.input.focus();
              }),
              button(
                "Delete",
                () => {
                  if (
                    current.global.includes(item.id) ||
                    Object.values(current.clients).some((ids) =>
                      ids.includes(item.id),
                    )
                  ) {
                    view.message.textContent =
                      "Remove this policy from gateway and user assignments before deleting it.";
                    return;
                  }
                  if (
                    !window.confirm(
                      `Delete policy ${item.label}? Remove its assignments first.`,
                    )
                  )
                    return;
                  void task(form, view.message, async () => {
                    await context.request(
                      `./policies/${encodeURIComponent(item.id)}`,
                      { method: "DELETE", revision: current.revision },
                    );
                    await context.reload();
                  });
                },
                { danger: true },
              ),
            );
          return [
            `${item.label} (${item.id})`,
            current.templates.find((value) => value.id === item.template)
              ?.label ?? item.template,
            item.phase,
            actions,
          ];
        }),
        "No policies yet. Create a policy using a template below.",
      ),
    );
    for (const row of list.querySelectorAll("tbody tr"))
      [...row.cells].forEach((cell, index) => {
        if (cell.colSpan === 1)
          cell.dataset.label = ["Policy", "Template", "Applies to", "Actions"][
            index
          ];
      });
    choice.input.replaceChildren();
    for (const [value, text] of [
      ["", "Choose a policy"],
      ...current.items.map((item) => [item.id, item.label]),
    ]) {
      const option = node("option", text);
      option.value = value;
      choice.input.append(option);
    }
    if (!editorDirty) resetEditor();
    if (!assignmentDirty) selectAssignment();
  }
  function clear() {
    current = null;
    editorDirty = assignmentDirty = false;
    editorRevision = assignmentDocument = null;
    editing = null;
    form.reset();
    sample.input.value = "";
    output.textContent = "Your result will appear here.";
    list.replaceChildren();
    ordered.replaceChildren();
    assignmentMessage.textContent =
      previewMessage.textContent =
      view.message.textContent =
        "";
    assignmentForm.reset();
  }
  return { root: view.root, load, clear };
}
