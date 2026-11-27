"use strict";
import {
  node,
  field,
  button,
  panel,
  table,
  task,
  pagination,
  dateLabel,
  statusText,
} from "./admin_forms.js";

export function identityPanels(context) {
  const keys = panel(
    "user-keys",
    "User credentials",
    "Issue named keys with independent expiration and revocation. Existing keys remain valid when another key is added.",
  );
  const keyUser = field("User ID", {
    required: true,
    id: "keys-user",
    help: "Select Keys on a user row, or enter its exact ID.",
  });
  const keyLookup = node("form", undefined, "admin-form compact-form");
  const loadKeysButton = node("button", "Load user keys", "button secondary");
  loadKeysButton.type = "submit";
  keyLookup.append(keyUser.root, loadKeysButton);
  const keyTable = node("div");
  const keyForm = node("form", undefined, "admin-form");
  const keyLabel = field("Key label", {
    required: true,
    value: "Application key",
    id: "new-key-label",
  });
  const keyExpiry = field("Expiration (UTC)", {
    type: "datetime-local",
    id: "new-key-expiry",
    help: "Leave empty for 90 days. New credentials may expire at most one year from now.",
  });
  const issue = node("button", "Issue named user key", "button primary");
  issue.id = "issue-named-key";
  issue.type = "submit";
  keyForm.append(keyLabel.root, keyExpiry.root, issue);
  keys.content.append(keyLookup, keyTable, keyForm);
  function expiryValue(input) {
    return input.value ? { expires_at: `${input.value}:00Z` } : {};
  }
  async function keyWrite(path, method, body) {
    await task(keyForm, keys.message, async () => {
      const result = await context.request(path, {
        method,
        ...(body ? { body } : {}),
      });
      if (result?.token)
        context.showToken(`user ${keyUser.input.value}`, result.token);
      if (result?.revision !== undefined) context.setRevision(result.revision);
      await context.reload();
      await loadKeys();
    });
  }
  async function loadKeys() {
    const id = keyUser.input.value.trim();
    if (!id) {
      keyTable.replaceChildren(
        node("p", "Choose a user to inspect its credentials.", "panel-note"),
      );
      return;
    }
    try {
      const result = await context.request(
        `./clients/${encodeURIComponent(id)}/keys`,
      );
      if (!context.connected()) return;
      context.setRevision(result.revision);
      keyTable.replaceChildren(
        table(
          ["Label / ID", "Status", "Expires (UTC)", "Last used", "Actions"],
          (result.items ?? result.keys ?? []).map((key) => {
            const label = node("div", key.label);
            label.append(node("span", key.id, "secondary-line"));
            const actions = node("div", undefined, "row-actions");
            if (context.canWrite() && !key.revoked) {
              actions.append(
                button("Rotate this key", () => {
                  if (
                    window.confirm(
                      `Rotate ${key.label}? Its current token will stop working.`,
                    )
                  )
                    void keyWrite(
                      `./clients/${encodeURIComponent(id)}/keys/${encodeURIComponent(key.id)}/rotate`,
                      "POST",
                      { label: key.label, ...expiryValue(keyExpiry.input) },
                    );
                }),
                button(
                  "Revoke this key",
                  () => {
                    if (
                      window.confirm(
                        `Revoke ${key.label}? Other named keys for this user remain active.`,
                      )
                    )
                      void keyWrite(
                        `./clients/${encodeURIComponent(id)}/keys/${encodeURIComponent(key.id)}`,
                        "DELETE",
                      );
                  },
                  { danger: true },
                ),
              );
            }
            return [
              label,
              key.revoked
                ? "Revoked"
                : key.expires_at && Date.parse(key.expires_at) <= Date.now()
                  ? "Expired"
                  : "Active",
              dateLabel(key.expires_at),
              dateLabel(key.last_used_at),
              actions,
            ];
          }),
        ),
      );
    } catch (error) {
      if (context.connected()) keys.message.textContent = statusText(error);
    }
  }
  keyLookup.addEventListener("submit", (event) => {
    event.preventDefault();
    void loadKeys();
  });
  keyForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const id = keyUser.input.value.trim();
    if (!id) {
      keys.message.textContent = "Choose a user first.";
      return;
    }
    void keyWrite(`./clients/${encodeURIComponent(id)}/keys`, "POST", {
      label: keyLabel.input.value.trim(),
      ...expiryValue(keyExpiry.input),
    });
  });

  const operators = panel(
    "operator-management",
    "Operators & roles",
    "Give each person their own sign-in. Administrator and viewer roles keep every change attributable. Recovery access stays managed on the server.",
  );
  const operatorTable = node("div");
  const operatorForm = node("form", undefined, "admin-form");
  const operatorId = field("Username", {
    required: true,
    id: "new-operator-id",
  });
  const operatorLabel = field("Display name", {
    required: true,
    id: "new-operator-label",
  });
  const operatorRole = field("Role", {
    options: [
      ["viewer", "Viewer — read only"],
      ["admin", "Administrator"],
    ],
    id: "new-operator-role",
  });
  const operatorExpiry = field("Expiration (UTC)", {
    type: "datetime-local",
    id: "new-operator-expiry",
    help: "Leave empty for 90 days.",
  });
  const operatorMethod = field("Sign-in method", {
    options: [
      ["password", "Password account"],
      ["token", "Automation token"],
    ],
    id: "new-operator-method",
  });
  const operatorPassword = field("Password", {
    type: "password",
    id: "new-operator-password",
    help: "Use 12–128 characters. Share it securely with the account owner.",
  });
  operatorPassword.input.minLength = 12;
  operatorPassword.input.maxLength = 128;
  operatorPassword.input.autocomplete = "new-password";
  const createOperator = node("button", "Create operator", "button primary");
  createOperator.type = "submit";
  createOperator.id = "create-operator";
  const cancelOperator = button("Cancel operator edit", resetOperator);
  operatorForm.append(
    operatorId.root,
    operatorLabel.root,
    operatorRole.root,
    operatorMethod.root,
    operatorPassword.root,
    operatorExpiry.root,
    createOperator,
    cancelOperator,
  );
  operators.content.append(operatorTable, operatorForm);
  let editingOperator = null;
  let editingOperatorRevision = null;
  function updateOperatorMethod() {
    const password =
      !editingOperator && operatorMethod.input.value === "password";
    operatorMethod.root.hidden = Boolean(editingOperator);
    operatorPassword.root.hidden = !password;
    operatorPassword.input.required = password;
    operatorExpiry.root.hidden = password;
    if (!password) operatorPassword.input.value = "";
  }
  operatorMethod.input.addEventListener("change", updateOperatorMethod);
  function resetOperator() {
    editingOperator = null;
    editingOperatorRevision = null;
    operatorForm.reset();
    operatorId.input.disabled = false;
    createOperator.textContent = "Create operator";
    updateOperatorMethod();
  }
  const passwordDialog = node("dialog");
  passwordDialog.id = "reset-password-dialog";
  const passwordTitle = node("h2");
  passwordTitle.id = "reset-password-title";
  passwordDialog.setAttribute("aria-labelledby", passwordTitle.id);
  const passwordForm = node("form", undefined, "admin-form");
  const resetPassword = field("New password", {
    type: "password",
    required: true,
    id: "reset-operator-password",
    help: "12–128 characters. Existing browser sessions for this account will end.",
  });
  resetPassword.input.minLength = 12;
  resetPassword.input.maxLength = 128;
  resetPassword.input.autocomplete = "new-password";
  const passwordMessage = node("p", undefined, "message full-width");
  passwordMessage.setAttribute("role", "status");
  const passwordActions = node("div", undefined, "form-actions");
  const savePassword = node("button", "Save password", "button primary");
  savePassword.type = "submit";
  passwordActions.append(
    savePassword,
    button("Cancel", () => passwordDialog.close()),
  );
  passwordForm.append(resetPassword.root, passwordMessage, passwordActions);
  passwordDialog.append(passwordTitle, passwordForm);
  document.body.append(passwordDialog);
  let passwordTarget = null;
  let passwordRevision = null;
  passwordDialog.addEventListener("close", () => {
    resetPassword.input.value = "";
    passwordTarget = null;
    passwordMessage.textContent = "";
  });
  passwordForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const id = passwordTarget;
    const password = resetPassword.input.value;
    resetPassword.input.value = "";
    void task(passwordForm, passwordMessage, async () => {
      await context.request(`./accounts/${encodeURIComponent(id)}/password`, {
        method: "PUT",
        revision: passwordRevision,
        body: { password },
      });
      passwordDialog.close();
      if (context.actor()?.id === id) context.reauthenticate();
      else {
        await context.reload();
        operators.message.textContent =
          "Password updated. Previous sessions for this account have ended.";
      }
    });
  });
  operatorForm.addEventListener("submit", (event) => {
    event.preventDefault();
    void task(operatorForm, operators.message, async () => {
      const payload = {
        label: operatorLabel.input.value.trim(),
        role: operatorRole.input.value,
        ...expiryValue(operatorExpiry.input),
      };
      const accountPassword = operatorPassword.input.value;
      operatorPassword.input.value = "";
      const result = await context.request(
        editingOperator
          ? `./operators/${encodeURIComponent(editingOperator)}`
          : operatorMethod.input.value === "password"
            ? "./accounts"
            : "./operators",
        {
          method: editingOperator ? "PUT" : "POST",
          ...(editingOperator ? { revision: editingOperatorRevision } : {}),
          body: editingOperator
            ? payload
            : operatorMethod.input.value === "password"
              ? {
                  id: operatorId.input.value.trim(),
                  label: payload.label,
                  role: payload.role,
                  password: accountPassword,
                }
              : { id: operatorId.input.value.trim(), ...payload },
        },
      );
      if (result?.token)
        context.showToken(`operator ${operatorId.input.value}`, result.token);
      context.setRevision(result?.revision);
      resetOperator();
      await context.reload();
    });
  });
  async function loadOperators() {
    const result = await context.request("./operators");
    if (!context.connected()) return;
    context.setRevision(result.revision);
    resetOperator();
    operatorTable.replaceChildren(
      table(
        ["Operator", "Role", "Status", "Expiration", "Actions"],
        (result.items ?? result.operators ?? []).map((operator) => {
          const actions = node("div", undefined, "row-actions");
          if (
            context.canWrite() &&
            operator.id !== "bootstrap" &&
            !operator.revoked
          ) {
            actions.append(
              button("Edit role / expiry", () => {
                editingOperator = operator.id;
                editingOperatorRevision = result.revision;
                operatorId.input.value = operator.id;
                operatorId.input.disabled = true;
                operatorLabel.input.value = operator.label;
                operatorRole.input.value = operator.role;
                operatorExpiry.input.value =
                  operator.expires_at?.slice(0, 16) ?? "";
                createOperator.textContent = "Save operator";
                updateOperatorMethod();
                operatorLabel.input.focus();
              }),
              button(
                "Revoke operator",
                () => {
                  if (
                    !window.confirm(
                      `Revoke ${operator.label}? Its operator credential stops working immediately.`,
                    )
                  )
                    return;
                  void task(operatorForm, operators.message, async () => {
                    await context.request(
                      `./operators/${encodeURIComponent(operator.id)}`,
                      { method: "DELETE" },
                    );
                    await context.reload();
                  });
                },
                { danger: true },
              ),
            );
          }
          if (context.canWrite() && operator.id !== "bootstrap") {
            actions.append(
              button(
                operator.password_configured
                  ? "Reset password"
                  : "Set password",
                () => {
                  passwordTarget = operator.id;
                  passwordRevision = result.revision;
                  passwordTitle.textContent = `${operator.password_configured ? "Reset" : "Set"} password: ${operator.label ?? operator.id}`;
                  resetPassword.input.value = "";
                  passwordMessage.textContent = "";
                  passwordDialog.showModal();
                  resetPassword.input.focus();
                },
              ),
            );
            actions.append(
              button(
                operator.revoked
                  ? "Reissue operator token"
                  : "Rotate operator token",
                () => {
                  if (
                    !window.confirm(
                      `Replace the operator token for ${operator.label}? Its previous token will stop working.`,
                    )
                  )
                    return;
                  void task(operatorForm, operators.message, async () => {
                    const result = await context.rotateOperatorToken(
                      operator.id,
                      {
                        label: operator.label,
                        ...expiryValue(operatorExpiry.input),
                      },
                    );
                    context.setRevision(result.revision);
                    await context.reload();
                  });
                },
              ),
            );
          }
          return [
            `${operator.label ?? operator.id} (${operator.id})`,
            `${operator.role} · ${operator.password_configured ? "Password enabled" : "Token access"}`,
            operator.id === "bootstrap"
              ? "Server recovery credential"
              : operator.revoked
                ? "Revoked"
                : operator.expires_at &&
                    Date.parse(operator.expires_at) <= Date.now()
                  ? "Expired"
                  : "Active",
            dateLabel(operator.expires_at),
            actions,
          ];
        }),
      ),
    );
  }

  const audit = panel(
    "audit-log",
    "Administrative audit",
    "Inspect attributed configuration changes. Credentials and conversation content are excluded.",
  );
  const auditForm = node("form", undefined, "admin-form audit-filters");
  const actor = field("Actor ID", { id: "audit-actor" });
  const action = field("Action", { id: "audit-action" });
  const target = field("Target", { id: "audit-target" });
  const start = field("From (UTC)", {
    type: "datetime-local",
    id: "audit-start",
  });
  const end = field("Until (UTC, exclusive)", {
    type: "datetime-local",
    id: "audit-end",
  });
  const auditSubmit = node("button", "Filter audit", "button secondary");
  auditSubmit.type = "submit";
  auditForm.append(
    actor.root,
    action.root,
    target.root,
    start.root,
    end.root,
    auditSubmit,
  );
  const auditTable = node("div");
  audit.content.append(auditForm, auditTable);
  let auditOffset = 0;
  async function loadAudit(offset = auditOffset) {
    auditOffset = offset;
    const params = new URLSearchParams({ offset: String(offset), limit: "25" });
    for (const [name, input] of [
      ["actor", actor.input],
      ["action", action.input],
      ["target", target.input],
    ])
      if (input.value.trim()) params.set(name, input.value.trim());
    for (const [name, input] of [
      ["start", start.input],
      ["end", end.input],
    ])
      if (input.value) params.set(name, `${input.value}:00Z`);
    const result = await context.request(`./audit?${params}`);
    if (!context.connected()) return;
    const rows = result.items ?? [];
    auditTable.replaceChildren(
      table(
        ["Time", "Actor", "Action", "Target", "Changed fields"],
        rows.map((item) => [
          dateLabel(item.timestamp ?? item.at),
          typeof item.actor === "object" ? item.actor.id : item.actor,
          item.action,
          item.target,
          JSON.stringify(item.diff ?? {}),
        ]),
      ),
      pagination(
        {
          offset: result.offset ?? offset,
          limit: result.limit ?? 25,
          total: result.total ?? result.pagination?.total ?? rows.length,
        },
        (next) => void task(auditForm, audit.message, () => loadAudit(next)),
      ),
    );
  }
  auditForm.addEventListener("submit", (event) => {
    event.preventDefault();
    void task(auditForm, audit.message, () => loadAudit(0));
  });
  async function load() {
    keyForm.hidden = operatorForm.hidden = !context.canWrite();
    await Promise.allSettled([loadKeys(), loadOperators(), loadAudit()]).then(
      (results) => {
        for (const result of results)
          if (result.status === "rejected" && context.connected())
            audit.message.textContent = statusText(result.reason);
      },
    );
  }
  async function selectClient(id) {
    context.go("users");
    keyUser.input.value = id;
    keys.root.scrollIntoView({ block: "start" });
    await loadKeys();
  }
  function clear() {
    keyLookup.reset();
    keyForm.reset();
    operatorForm.reset();
    operatorPassword.input.value = "";
    if (passwordDialog.open) passwordDialog.close();
    resetPassword.input.value = "";
    auditForm.reset();
    for (const root of [keyTable, operatorTable, auditTable])
      root.replaceChildren();
    for (const item of [keys, operators, audit]) item.message.textContent = "";
    editingOperator = null;
    auditOffset = 0;
  }
  return {
    roots: [keys.root, operators.root, audit.root],
    load,
    selectClient,
    clear,
  };
}
