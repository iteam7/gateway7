# Decisions

Decisions confirmed at the kickoff meeting. Source: [reports/week-01/meeting-report.md](../reports/week-01/meeting-report.md#decisions).

| Decision | Made by | Traces to |
| -------- | ------- | --------- |
| The gateway is a plugin host; how a company reacts to a policy hit (block, log, flag, or allow and log) is configured per plugin, not fixed in the core | Customer | `VP-02` |
| Plugins intercept both the request and the response; priority is request, then response, then routing | Customer | `VP-01` |
| Plugins are installed by restarting the gateway, not loaded on the fly, to avoid complexity and security risks | Customer | `VP-02` |
| The gateway holds provider keys and authenticates clients with per-user model access; users' own keys only as an optional, switchable feature | Customer, after azamatbayramov's question | None |
| One or two provider API formats are enough; covering Claude and Gemini is acceptable | Customer | `VP-01` |
| The gateway is written in Python or Go | Customer, on azamatbayramov's proposal | None |
| Plugin-authoring instructions for coding agents (a skill, an example) are a nice-to-have | Customer, on azamatbayramov's proposal | `VP-02` |
| MVP-0 is a proxy with a provider key from `.env`, one provider, and a phone-number masking plugin, preceded by CI and linter setup | azamatbayramov, not contested | `VP-01` |

## Week 02 validation additions

The eight kickoff rows above are preserved for their separate identifier migration.
Identifiers DEC-001 through DEC-008 are reserved for those eight records; the additions below start at DEC-009.

## DEC-009

Validate an extensible plugin-host architecture and plugin integration workflow rather than phone-masking behavior alone.

- **Status:** Active
- **Date:** 2026-10-09, derived from the supplied transcript's filename; not spoken explicitly.
- **Made by:** Customer
- **Source:** [Week 02 validation meeting report](../reports/week-02/meeting-report.md#summary).
- **Why:** the difficult part is making company-authored plugins fit and work together; a masking screen does not establish the plugin interface, message flow or installation lifecycle. This confirms the plugin-host direction and changes what the next prototype must demonstrate.

## DEC-010

Allow the gateway to restart when adding plugins; live hot swapping is not required.

- **Status:** Active
- **Date:** 2026-10-09, derived from the supplied transcript's filename; not spoken explicitly.
- **Made by:** Customer
- **Source:** [Week 02 validation meeting report](../reports/week-02/meeting-report.md#summary).
- **Why:** confirms the previously agreed restart-based installation boundary; continuously online hot swapping is unnecessary for the initial usable system.

## DEC-011

Use a deterministic test or static upstream for the initial usable plugin demonstration; an actual LLM connection is not required at this stage.

- **Status:** Active
- **Date:** 2026-10-09, derived from the supplied transcript's filename; not spoken explicitly.
- **Made by:** Customer
- **Source:** [Week 02 validation meeting report](../reports/week-02/meeting-report.md#summary).
- **Why:** deterministic responses make it easier to check what plugins do to text. The Customer wants to start the system, add simple plugins, send a request and inspect the result, with a two-plugin example; this clarifies the initial demonstration rather than permanently excluding real providers or accepting a specific story bundle.
