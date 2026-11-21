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
  nullableNumber,
  usd,
  statusText,
} from "./admin_forms.js";

export function reportingPanels(context) {
  const accounting = panel(
    "accounting-management",
    "Pricing, budgets & retention",
    "Set model prices and daily or monthly allowances. Costs are estimates from observed usage; unknown usage and reservations remain explicit.",
  );
  let policies = null;
  const pricesTable = node("div");
  const pricingForm = node("form", undefined, "admin-form");
  const priceModel = field("Canonical model ID", {
    required: true,
    id: "price-model",
  });
  const inputPrice = field("Input price, USD per million tokens", {
    type: "number",
    min: 0,
    step: 0.000001,
    max: "9007199254.740991",
    required: true,
    id: "input-price",
  });
  const outputPrice = field("Output price, USD per million tokens", {
    type: "number",
    min: 0,
    step: 0.000001,
    max: "9007199254.740991",
    required: true,
    id: "output-price",
  });
  const savePrice = node("button", "Save model price", "button primary");
  savePrice.id = "save-price";
  savePrice.type = "submit";
  pricingForm.append(
    priceModel.root,
    inputPrice.root,
    outputPrice.root,
    savePrice,
  );
  const budgetsTable = node("div");
  const budgetStatus = node("div");
  const budgetForm = node("form", undefined, "admin-form");
  const budgetId = field("Budget rule ID", { required: true, id: "budget-id" });
  const budgetUser = field("User ID", {
    id: "budget-user",
    help: "Leave empty to cover all users.",
  });
  const budgetModel = field("Canonical model ID", {
    id: "budget-model",
    help: "Leave empty to cover all models.",
  });
  const period = field("Budget period (UTC)", {
    options: [
      ["day", "Calendar day"],
      ["month", "Calendar month"],
    ],
    id: "budget-period",
  });
  const tokenLimit = field("Total token allowance", {
    type: "number",
    min: 1,
    step: 1,
    max: Number.MAX_SAFE_INTEGER,
    id: "budget-tokens",
    help: "Input plus output tokens. Leave empty for no token cap.",
  });
  const costLimit = field("Estimated cost allowance, USD", {
    type: "number",
    min: 0.000001,
    step: 0.000001,
    max: "9007199254.740991",
    id: "budget-cost",
    help: "Hard cost limits require known model pricing and usage.",
  });
  const enforcement = field("Enforcement", {
    options: [
      ["warn", "Warn at the limit"],
      ["hard", "Block requests beyond the allowance"],
    ],
    id: "budget-mode",
  });
  const enabled = field("Rule state", {
    options: [
      ["true", "Enabled"],
      ["false", "Disabled"],
    ],
    id: "budget-enabled",
  });
  const saveBudget = node("button", "Save budget rule", "button primary");
  saveBudget.id = "save-budget";
  saveBudget.type = "submit";
  budgetForm.append(
    budgetId.root,
    budgetUser.root,
    budgetModel.root,
    period.root,
    tokenLimit.root,
    costLimit.root,
    enforcement.root,
    enabled.root,
    saveBudget,
  );
  const retentionForm = node("form", undefined, "admin-form compact-form");
  const days = field("Keep reports and audit events, days", {
    type: "number",
    min: 32,
    max: 3650,
    step: 1,
    required: true,
    id: "retention-days",
    help: "Minimum 32 days preserves current monthly budget accounting. Older settled events are removed by retention cleanup.",
  });
  const saveRetention = node(
    "button",
    "Save retention policy",
    "button secondary",
  );
  saveRetention.type = "submit";
  retentionForm.append(days.root, saveRetention);
  accounting.content.append(
    node("h3", "Model prices"),
    pricesTable,
    pricingForm,
    node("h3", "Budget rules"),
    budgetsTable,
    budgetForm,
    node("h3", "Current allowances & reservations"),
    budgetStatus,
    node("h3", "Data retention"),
    retentionForm,
  );
  const draftRevisions = new Map();
  for (const form of [pricingForm, budgetForm, retentionForm])
    form.addEventListener("input", () => {
      if (!draftRevisions.has(form) && policies)
        draftRevisions.set(form, policies.revision);
    });
  const money = (input) => {
    if (input.value === "") return null;
    if (!/^\d+(?:\.\d{1,6})?$/.test(input.value))
      throw new Error("amount-invalid");
    const [whole, fraction = ""] = input.value.split(".");
    const micro = BigInt(whole) * 1_000_000n + BigInt(fraction.padEnd(6, "0"));
    if (micro > BigInt(Number.MAX_SAFE_INTEGER))
      throw new Error("amount-invalid");
    return Number(micro);
  };
  const amountError = () => {
    accounting.message.textContent =
      "Enter whole token counts and USD amounts with at most six decimal places. Values must fit the displayed limits.";
  };

  async function write(path, body, form) {
    await task(form, accounting.message, async () => {
      const result = await context.request(path, {
        method: "PUT",
        body,
        revision: draftRevisions.get(form) ?? policies.revision,
      });
      context.setRevision(result?.revision);
      await context.reload();
    });
  }
  pricingForm.addEventListener("submit", (event) => {
    event.preventDefault();
    try {
      const entry = {
        model: priceModel.input.value.trim(),
        input_micro_usd_per_million: money(inputPrice.input),
        output_micro_usd_per_million: money(outputPrice.input),
      };
      const prices = [
        ...policies.pricing.prices.filter(
          (price) => price.model !== entry.model,
        ),
        entry,
      ];
      void write("./pricing", { prices }, pricingForm);
    } catch {
      amountError();
    }
  });
  budgetForm.addEventListener("submit", (event) => {
    event.preventDefault();
    if (tokenLimit.input.value === "" && costLimit.input.value === "") {
      accounting.message.textContent =
        "Set a token allowance, a cost allowance, or both.";
      return;
    }
    try {
      const tokenAmount = nullableNumber(tokenLimit.input);
      if (tokenAmount !== null && !Number.isSafeInteger(tokenAmount))
        throw new Error("amount-invalid");
      const rule = {
        id: budgetId.input.value.trim(),
        client_id: budgetUser.input.value.trim() || null,
        model: budgetModel.input.value.trim() || null,
        period: period.input.value,
        tokens: tokenAmount,
        micro_usd: money(costLimit.input),
        mode: enforcement.input.value,
        enabled: enabled.input.value === "true",
      };
      void write(
        "./budgets",
        {
          rules: [
            ...policies.budgets.rules.filter((item) => item.id !== rule.id),
            rule,
          ],
        },
        budgetForm,
      );
    } catch {
      amountError();
    }
  });
  retentionForm.addEventListener("submit", (event) => {
    event.preventDefault();
    if (
      window.confirm(
        "Apply this retention policy? Settled report and audit events older than this period will be permanently removed during cleanup.",
      )
    )
      void write(
        "./retention",
        { days: Number(days.input.value) },
        retentionForm,
      );
  });
  async function loadAccounting() {
    policies = await context.request("./accounting");
    if (!context.connected()) return;
    context.setRevision(policies.revision);
    for (const form of [pricingForm, budgetForm, retentionForm]) {
      form.reset();
      draftRevisions.delete(form);
    }
    for (const form of [pricingForm, budgetForm, retentionForm])
      form.hidden = !context.canWrite();
    pricesTable.replaceChildren(
      table(
        [
          "Model",
          "Input / million tokens",
          "Output / million tokens",
          "Actions",
        ],
        policies.pricing.prices.map((price) => {
          const actions = node("div", undefined, "row-actions");
          if (context.canWrite())
            actions.append(
              button("Edit price", () => {
                draftRevisions.set(pricingForm, policies.revision);
                priceModel.input.value = price.model;
                inputPrice.input.value =
                  price.input_micro_usd_per_million / 1_000_000;
                outputPrice.input.value =
                  price.output_micro_usd_per_million / 1_000_000;
                priceModel.input.focus();
              }),
              button(
                "Remove price",
                () => {
                  if (
                    window.confirm(
                      `Remove the current price for ${price.model}? New attempts will have unknown cost until a price is set.`,
                    )
                  )
                    void write(
                      "./pricing",
                      {
                        prices: policies.pricing.prices.filter(
                          (item) => item.model !== price.model,
                        ),
                      },
                      pricingForm,
                    );
                },
                { danger: true },
              ),
            );
          return [
            price.model,
            usd(price.input_micro_usd_per_million),
            usd(price.output_micro_usd_per_million),
            actions,
          ];
        }),
      ),
    );
    budgetsTable.replaceChildren(
      table(
        ["Rule", "Scope", "Allowance", "Enforcement", "Actions"],
        policies.budgets.rules.map((rule) => {
          const actions = node("div", undefined, "row-actions");
          if (context.canWrite())
            actions.append(
              button("Edit rule", () => {
                draftRevisions.set(budgetForm, policies.revision);
                budgetId.input.value = rule.id;
                budgetUser.input.value = rule.client_id ?? "";
                budgetModel.input.value = rule.model ?? "";
                period.input.value = rule.period;
                tokenLimit.input.value = rule.tokens ?? "";
                costLimit.input.value =
                  rule.micro_usd == null ? "" : rule.micro_usd / 1_000_000;
                enforcement.input.value = rule.mode;
                enabled.input.value = String(rule.enabled);
                budgetId.input.focus();
              }),
              button(
                "Remove rule",
                () => {
                  if (
                    window.confirm(
                      `Remove budget rule ${rule.id}? Its allowance will no longer constrain requests.`,
                    )
                  )
                    void write(
                      "./budgets",
                      {
                        rules: policies.budgets.rules.filter(
                          (item) => item.id !== rule.id,
                        ),
                      },
                      budgetForm,
                    );
                },
                { danger: true },
              ),
            );
          return [
            rule.id,
            `${rule.client_id ?? "All users"} · ${rule.model ?? "all models"} · ${rule.period}`,
            `${rule.tokens ?? "No"} token cap · ${rule.micro_usd === null ? "no cost cap" : usd(rule.micro_usd)}`,
            `${rule.enabled ? "Enabled" : "Disabled"} · ${rule.mode}`,
            actions,
          ];
        }),
      ),
    );
    days.input.value = policies.retention.days;
    const status = await context.request("./budgets/status");
    if (!context.connected()) return;
    budgetStatus.replaceChildren(
      table(
        [
          "Rule",
          "Used / reserved tokens",
          "Used / reserved cost",
          "Window ends",
          "Status",
        ],
        (status.items ?? []).map((item) => [
          item.id,
          `${item.used_tokens} / ${item.reserved_tokens}`,
          `${usd(item.used_micro_usd)} / ${usd(item.reserved_micro_usd)}`,
          dateLabel(item.window_end),
          `${item.exhausted ? "Exhausted" : item.warning ? "Warning" : "Within allowance"}${item.unknown_cost_attempts ? ` · ${item.unknown_cost_attempts} attempts with unknown cost` : ""}`,
        ]),
      ),
    );
  }

  const diagnostics = panel(
    "request-diagnostics",
    "Request diagnostics",
    "Inspect errors, denials, request latency and usage activity without saving prompts or answers.",
  );
  const diagnosticForm = node("form", undefined, "admin-form audit-filters");
  const user = field("User ID", { id: "diagnostic-user" });
  const model = field("Model", { id: "diagnostic-model" });
  const from = field("From (UTC)", {
    type: "datetime-local",
    id: "diagnostic-start",
  });
  const until = field("Until (UTC, exclusive)", {
    type: "datetime-local",
    id: "diagnostic-end",
  });
  const filter = node("button", "Filter diagnostics", "button secondary");
  filter.type = "submit";
  diagnosticForm.append(user.root, model.root, from.root, until.root, filter);
  const diagnosticSummary = node("div");
  const diagnosticRows = node("div");
  diagnostics.content.append(diagnosticForm, diagnosticSummary, diagnosticRows);
  let diagnosticOffset = 0;
  async function loadDiagnostics(offset = diagnosticOffset) {
    diagnosticOffset = offset;
    const query = new URLSearchParams({ offset: String(offset), limit: "25" });
    for (const [name, input] of [
      ["client_id", user.input],
      ["model", model.input],
    ])
      if (input.value.trim()) query.set(name, input.value.trim());
    for (const [name, input] of [
      ["start", from.input],
      ["end", until.input],
    ])
      if (input.value) query.set(name, `${input.value}:00Z`);
    const result = await context.request(`./diagnostics?${query}`);
    if (!context.connected()) return;
    diagnosticSummary.replaceChildren(
      table(
        [
          "Last seen",
          "Mean latency on this page",
          "HTTP outcomes on this page",
          "Active requests",
        ],
        [
          [
            dateLabel(result.last_seen),
            result.mean_latency_ms === null
              ? "—"
              : `${result.mean_latency_ms?.toFixed(1)} ms`,
            Object.entries(result.http_outcomes ?? {})
              .map(([outcome, count]) => `${outcome}: ${count}`)
              .join(" · ") || "—",
            typeof result.active_requests === "object"
              ? Object.entries(result.active_requests)
                  .map(([id, count]) => `${id}: ${count}`)
                  .join(" · ") || "None"
              : (result.active_requests ?? result.active ?? "—"),
          ],
        ],
      ),
    );
    const rows = result.items ?? [];
    diagnosticRows.replaceChildren(
      table(
        ["Time", "User / key", "Model", "Outcome", "Latency"],
        rows.map((item) => [
          `${dateLabel(item.started_at)} · ${item.kind}`,
          `${item.client_id ?? "Anonymous"} / ${item.key_id ?? "—"}`,
          item.model ?? "—",
          item.status ?? item.outcome,
          item.duration_ms == null ? "—" : `${item.duration_ms} ms`,
        ]),
      ),
      pagination(
        {
          offset: result.offset ?? offset,
          limit: result.limit ?? 25,
          total: result.total ?? result.pagination?.total ?? rows.length,
        },
        (next) =>
          void task(diagnosticForm, diagnostics.message, () =>
            loadDiagnostics(next),
          ),
      ),
    );
  }
  diagnosticForm.addEventListener("submit", (event) => {
    event.preventDefault();
    void task(diagnosticForm, diagnostics.message, () => loadDiagnostics(0));
  });

  const trendRoot = node("div", undefined, "usage-trends");
  trendRoot.id = "usage-trends";
  function renderUsage(report) {
    trendRoot.replaceChildren();
    if (!report.summary) return;
    const total = report.summary;
    trendRoot.append(
      table(
        [
          "Known estimated cost",
          "Attempts with unknown cost",
          "In-flight reservations",
          "Report precision",
        ],
        [
          [
            usd(total.cost_micro_usd),
            total.unknown_cost_attempts,
            total.pending_attempts ?? 0,
            report.legacy_daily_precision
              ? "Includes historical daily aggregates"
              : "Event timestamps",
          ],
        ],
      ),
    );
    const series = report.timeseries ?? [];
    if (series.length) {
      const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      svg.setAttribute("viewBox", "0 0 800 160");
      svg.setAttribute("role", "img");
      svg.setAttribute(
        "aria-label",
        "Provider attempts by selected UTC time bucket",
      );
      const maximum = Math.max(
        1,
        ...series.map((point) => point.provider_attempts),
      );
      series.slice(-100).forEach((point, index, values) => {
        const rect = document.createElementNS(svg.namespaceURI, "rect");
        const width = 780 / values.length;
        const height = (point.provider_attempts / maximum) * 130;
        rect.setAttribute("x", String(10 + index * width));
        rect.setAttribute("y", String(145 - height));
        rect.setAttribute("width", String(Math.max(1, width - 2)));
        rect.setAttribute("height", String(height));
        rect.setAttribute("fill", "#157c70");
        const title = document.createElementNS(svg.namespaceURI, "title");
        title.textContent = `${dateLabel(point.at)}: ${point.provider_attempts} attempts`;
        rect.append(title);
        svg.append(rect);
      });
      trendRoot.append(
        node("p", "Provider attempts by UTC time bucket", "panel-note"),
        svg,
        table(
          [
            "UTC bucket",
            "Attempts",
            "Input / output tokens",
            "Known estimated cost",
          ],
          series
            .slice(-100)
            .map((point) => [
              dateLabel(point.at),
              point.provider_attempts,
              `${point.known_input_tokens} / ${point.known_output_tokens}`,
              usd(point.cost_micro_usd),
            ]),
        ),
      );
    }
    const page = report.pagination;
    if (page)
      trendRoot.append(pagination(page, (offset) => context.usagePage(offset)));
  }
  async function load() {
    const results = await Promise.allSettled([
      loadAccounting(),
      loadDiagnostics(),
    ]);
    for (const result of results)
      if (result.status === "rejected" && context.connected())
        diagnostics.message.textContent = statusText(result.reason);
  }
  function clear() {
    policies = null;
    diagnosticOffset = 0;
    for (const form of [pricingForm, budgetForm, retentionForm, diagnosticForm])
      form.reset();
    for (const root of [
      pricesTable,
      budgetsTable,
      budgetStatus,
      diagnosticRows,
      diagnosticSummary,
      trendRoot,
    ])
      root.replaceChildren();
    accounting.message.textContent = diagnostics.message.textContent = "";
  }
  return {
    roots: [accounting.root, diagnostics.root],
    trendRoot,
    renderUsage,
    load,
    clear,
  };
}
