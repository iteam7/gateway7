"use strict";

export function node(tag, text, className) {
  const result = document.createElement(tag);
  if (text !== undefined && text !== null) result.textContent = String(text);
  if (className) result.className = className;
  return result;
}
export function field(
  label,
  {
    type = "text",
    value = "",
    options,
    help,
    required = false,
    min,
    max,
    step,
    multiline = false,
    id,
  } = {},
) {
  const root = node("label", label, "admin-field");
  const input = node(options ? "select" : multiline ? "textarea" : "input");
  if (id) input.id = id;
  if (!options && !multiline) input.type = type;
  if (options)
    for (const [value, text] of options) {
      const option = node("option", text);
      option.value = value;
      input.append(option);
    }
  input.value = value ?? "";
  input.required = required;
  if (min !== undefined) input.min = min;
  if (max !== undefined) input.max = max;
  if (step !== undefined) input.step = step;
  input.autocomplete = "off";
  if (multiline) {
    input.rows = 3;
    input.spellcheck = false;
  }
  root.append(input);
  if (help) root.append(node("small", help));
  return { root, input };
}
export function button(
  text,
  onClick,
  { danger = false, primary = false, id } = {},
) {
  const result = node(
    "button",
    text,
    `button ${danger ? "danger" : primary ? "primary" : "secondary"}`,
  );
  result.type = "button";
  if (id) result.id = id;
  result.addEventListener("click", onClick);
  return result;
}
export function panel(id, title, description) {
  const root = node("section", undefined, "panel admin-panel");
  root.id = id;
  const heading = node("div", undefined, "panel-heading");
  const copy = node("div");
  copy.append(node("h2", title));
  if (description) copy.append(node("p", description));
  heading.append(copy);
  const content = node("div", undefined, "admin-content");
  const message = node("p", undefined, "message");
  message.setAttribute("role", "status");
  message.setAttribute("aria-live", "polite");
  content.append(message);
  root.append(heading, content);
  return { root, heading, content, message };
}
export function table(headers, rows, empty = "No matching records.") {
  const scroll = node("div", undefined, "table-scroll");
  const root = node("table");
  const head = node("thead");
  const labels = node("tr");
  for (const text of headers) {
    const th = node("th", text);
    th.scope = "col";
    labels.append(th);
  }
  head.append(labels);
  const body = node("tbody");
  for (const values of rows) {
    const row = node("tr");
    for (const value of values) {
      const td = node("td");
      if (value instanceof Node) td.append(value);
      else td.textContent = value ?? "—";
      row.append(td);
    }
    body.append(row);
  }
  if (!rows.length) {
    const row = node("tr");
    const cell = node("td", empty, "empty-row");
    cell.colSpan = headers.length;
    row.append(cell);
    body.append(row);
  }
  root.append(head, body);
  scroll.append(root);
  return scroll;
}
export function statusText(error) {
  if (error?.message === "conflict")
    return "Another administrator changed this configuration. Refresh and apply your change again.";
  if (error?.message === "forbidden")
    return "This operator does not have permission to make this change.";
  if (error?.message === "rejected")
    return "The gateway rejected this change. Check the fields and current policy.";
  if (error?.message === "not-found")
    return "This record is no longer available. Refresh the workspace.";
  return "Could not complete the request. Refresh before trying again.";
}
export async function task(form, message, operation) {
  const controls = [...form.querySelectorAll("input,button,select,textarea")];
  const previous = controls.map((control) => control.disabled);
  controls.forEach((control) => {
    control.disabled = true;
  });
  message.textContent = "";
  try {
    return await operation();
  } catch (error) {
    if (error?.message !== "stale-session" && error?.name !== "AbortError")
      message.textContent = statusText(error);
    return undefined;
  } finally {
    controls.forEach((control, index) => {
      control.disabled = previous[index];
    });
  }
}
export const lines = (value) =>
  value
    .split(/\r?\n/)
    .map((part) => part.trim())
    .filter(Boolean);
export const nullableNumber = (input) =>
  input.value === "" ? null : Number(input.value);
export const dateLabel = (value) =>
  value
    ? `${new Date(value).toLocaleString(undefined, { timeZone: "UTC" })} UTC`
    : "Never";
export const usd = (micro) =>
  micro === null || micro === undefined
    ? "Unknown"
    : new Intl.NumberFormat(undefined, {
        style: "currency",
        currency: "USD",
        maximumFractionDigits: 6,
      }).format(micro / 1_000_000);
export function pagination({ offset, limit, total }, change) {
  const root = node("div", undefined, "form-actions");
  const previous = button("Previous page", () =>
    change(Math.max(0, offset - limit)),
  );
  previous.disabled = offset === 0;
  const next = button("Next page", () => change(offset + limit));
  next.disabled = offset + limit >= total;
  root.append(
    previous,
    node(
      "span",
      `${total ? offset + 1 : 0}–${Math.min(offset + limit, total)} of ${total}`,
    ),
    next,
  );
  return root;
}
