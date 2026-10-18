# Decisions

Decisions confirmed at the kickoff meeting. Source: [reports/week-01/meeting-report.md](https://github.com/iteam7/gateway7/blob/main/reports/week-01/meeting-report.md#decisions).

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
- **Source:** [Week 02 validation meeting report](https://github.com/iteam7/gateway7/blob/main/reports/week-02/meeting-report.md#summary).
- **Why:** the difficult part is making company-authored plugins fit and work together; a masking screen does not establish the plugin interface, message flow or installation lifecycle. This confirms the plugin-host direction and changes what the next prototype must demonstrate.

## DEC-010

Allow the gateway to restart when adding plugins; live hot swapping is not required.

- **Status:** Active
- **Date:** 2026-10-09, derived from the supplied transcript's filename; not spoken explicitly.
- **Made by:** Customer
- **Source:** [Week 02 validation meeting report](https://github.com/iteam7/gateway7/blob/main/reports/week-02/meeting-report.md#summary).
- **Why:** confirms the previously agreed restart-based installation boundary; continuously online hot swapping is unnecessary for the initial usable system.

## DEC-011

Use a deterministic test or static upstream for the initial usable plugin demonstration; an actual LLM connection is not required at this stage.

- **Status:** Active
- **Date:** 2026-10-09, derived from the supplied transcript's filename; not spoken explicitly.
- **Made by:** Customer
- **Source:** [Week 02 validation meeting report](https://github.com/iteam7/gateway7/blob/main/reports/week-02/meeting-report.md#summary).
- **Why:** deterministic responses make it easier to check what plugins do to text. The Customer wants to start the system, add simple plugins, send a request and inspect the result, with a two-plugin example; this clarifies the initial demonstration rather than permanently excluding real providers or accepting a specific story bundle.

## DEC-012

Accept US-01, US-02 and US-03 as the proposed minimum usable product candidate.

- **Status:** Active
- **Date:** Customer approval reported by azamatbayramov on 2026-10-10; the approval's original date was not specified.
- **Made by:** Customer
- **Source:** [Contributor follow-up recorded with the Week 02 report](https://github.com/iteam7/gateway7/blob/main/reports/week-02/meeting-report.md#summary), separate from the supplied meeting transcript.
- **Why:** azamatbayramov confirmed that the Customer approved the candidate when asked specifically about the US-01–03 bundle. This settles the candidate's planning status on that reported evidence; it is not acceptance of implemented stories, proof that their criteria passed, or approval of every hook/architecture detail. The deterministic initial-validation boundary in [DEC-011](#dec-011) still applies.

## DEC-013

Use Python for the first Gateway7 implementation.

- **Status:** Active
- **Date:** 2026-10-15.
- **Made by:** Team
- **Source:** azamatbayramov's implementation discussion on 15 October, in which he explicitly selected Python and requested a runnable architecture prototype for the next customer call; the implementation is tracked in [task #52](https://github.com/iteam7/gateway7/issues/52).
- **Why:** Python makes the agreed extension boundary directly executable as imported, trusted modules with typed request and response contracts, keeping the first demonstration in one service process. FastAPI, Pydantic, PyYAML and HTTPX implement HTTP handling, validation, configuration and provider transport; uv locks the dependencies. This records the contributor's selection within the Team category, not a claim of unanimous review or customer approval. Restart-based installation remains governed by [DEC-010](#dec-010).

## DEC-014

Explain plugin execution, failure handling and diagnosis, and justify the chosen architecture against alternatives.

- **Status:** Active
- **Date:** 2026-10-16, derived from the supplied meeting record's date; not stated aloud.
- **Made by:** Customer
- **Source:** [Week 03 customer meeting report](https://github.com/iteam7/gateway7/blob/c68ef782af464f22e48f67d7728e429ea619f3b8/reports/week-03/meeting-report.md#summary).
- **Why:** the high-level diagrams hid the plugin runner's important behavior. An operator needs to identify a failing or hanging plugin and understand progress and timing through the chain. Customer requested a reasoned design, offering Django middleware and Twisted callbacks as examples to examine while leaving the choice to the team. This deepens the architecture validation requested in DEC-009; it does not approve a framework or accept an implemented story.

## DEC-015

Use three interacting plugins and a clear authoring/configuration walkthrough for the next usable demonstration.

- **Status:** Active
- **Date:** 2026-10-16, derived from the supplied meeting record's date; not stated aloud.
- **Made by:** Customer
- **Source:** [Week 03 customer meeting report](https://github.com/iteam7/gateway7/blob/c68ef782af464f22e48f67d7728e429ea619f3b8/reports/week-03/meeting-report.md#summary).
- **Why:** one phone-masking plugin did not demonstrate composition. Customer requested multiple different plugins working together and inspected how their settings, chain names and Python interfaces are supplied. The request strengthens the next demonstration of the existing plugin-host direction; it neither replaces the candidate's ACs nor establishes story acceptance, a capacity limit or a new delivery deadline.
