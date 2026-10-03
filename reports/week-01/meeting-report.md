# Kickoff meeting report

## Metadata

**Date:** 2026-10-02
**Duration:** 49 minutes
**Attended:** azamatbayramov, Customer, and one member of another course team working on the same project (shown as `Guest` in the notes)
**Presented:** nothing prepared; the session was a question-and-answer round, and our `VP-01`/`VP-02` direction was not shown
**Recording:** initiated by the Customer; the participant does not recall asking the separate permission questions. On October 3 azamatbayramov clarified that the Customer supplied only a transcript and conversation overview, with no recording or recording link; instructor access cannot be verified
**Transcript publication:** unconfirmed after participant clarification on October 3; see [sanitized summary notes](meeting-notes.md) instead. The previous transcript remains in Git history
**Transcript shared privately:** unconfirmed; obtain permission before sharing a verbatim transcript
**Script:** [meeting-script.md](meeting-script.md)

## Summary

- The Customer sees the product as a plugin host, not a PII filter: filtering personal data is one plugin among access control, token accounting, logging, and code fingerprinting, which narrows our `VP-01` framing.
- Plugins must see both the request and the response; routing between models comes third, and installing a plugin may require a restart.
- The gateway holds the provider keys and authenticates clients with per-user model access; users' own keys are acceptable only as an optional feature the operator can turn off.
- One or two provider API formats are enough, and covering Claude and Gemini is acceptable; Python or Go is approved for the gateway.
- The Customer asked the architecture to state an explicit upper limit on running plugins; azamatbayramov estimated MVP-0 at two to three weeks, after CI and linter setup.

## Decisions

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

## Action points

October 3 post-kickoff clarification by azamatbayramov: repository infrastructure is his next task; he assigned base-architecture planning to ExFuseMe. These assignments were made after the kickoff. October 8 was not agreed. The current architecture target is proposed for October 12, outside the assignment's required Week 2 window (October 2–8); it is not a kickoff commitment. The infrastructure date remains unagreed.

| Action | Owner | Due |
| ------ | ----- | --- |
| Prepare the repository infrastructure for development, including CI and linters | azamatbayramov (assigned October 3) | Week 2 proposed; date to agree |
| Propose the architecture for MVP-0: core/plugin contract, request and response flow, one provider, and the upper limit of running plugins | ExFuseMe (assigned October 3) | Proposed: 2026-10-12; not confirmed, outside Week 2 |

## Open questions

| Question | What it would change | Follow-up |
| -------- | -------------------- | --------- |
| What is the upper limit of plugins running at once in our architecture, and what slows down past it? | How plugins pass a request between each other, and whether the core needs more than a simple chain | ExFuseMe, architecture proposal (assigned after kickoff on October 3) |
| Python or Go for the gateway? | The plugin-authoring experience for agents and the performance ceiling | Team decision, Week 2 planning |
| Do provider keys live in the gateway's configuration or in an external secret manager? | Deployment and security scope of MVP-0 | Week 2 planning |
| Does `VP-01` stay a privacy-preflight proposition, or become one plugin under a plugin-host proposition? | The framing of `VP-01` and `GAP-01`, and what MVP-0 demonstrates | Week 2 research update |

## Disagreements

| Your position | Customer's position | What you changed |
| ------------- | ------------------- | ---------------- |
| Users should be able to send requests through the gateway with their own provider keys, as in azamatbayramov's workplace | It is a poor practice; the gateway should hold a key pool, and building the option in encourages it | Kept only as an optional feature an operator can turn off; gateway-held keys are the default path |
| `VP-01` frames the product as a privacy preflight that masks or blocks text before forwarding (written direction, not presented) | Filtering personal data alone is a solved problem; the value is a plugin host where each company plugs in its own policy | The October 3 [VP clarification](../../docs/research/value-proposition.md) retains privacy as one use case inside the plugin host; the detailed proposal still needs validation |
