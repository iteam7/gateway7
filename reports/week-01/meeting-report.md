# Kickoff meeting report

## Metadata

**Date:** 2026-10-02
**Duration:** 49 minutes
**Attended:** azamatbayramov, Customer, and one member of another course team working on the same project (shown as `Guest` in the notes)
**Presented:** nothing prepared; the session was a question-and-answer round, and our `VP-01`/`VP-02` direction was not shown
**Recording:** the Customer initiated recording; the participant does not recall asking the separate permission questions. The recording link remains private
**Transcript publication:** unconfirmed; the participant does not remember asking. The verbatim transcript is withheld from this revised public tree
**Transcript shared privately:** unconfirmed; obtain permission before any private transcript sharing
**Evidence:** [sanitized summary notes](meeting-notes.md), prepared on October 3 from the existing record; not a verbatim transcript. The previous published transcript remains in Git history, which this change does not rewrite
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

The meeting supports the following planning follow-ups. On October 3, azamatbayramov confirmed that October 8 was not an agreed deadline. Owners and exact dates must be agreed during Week 2 planning; the rows below do not assert a meeting commitment to an invented date.

| Action | Owner | Due |
| ------ | ----- | --- |
| Write the MVP-0 plan: proxy, provider key from `.env`, one provider, phone-number masking plugin | azamatbayramov (proposed owner) | Not agreed; schedule during Week 2 planning |
| Plan the development infrastructure for the codebase: CI and linters | azamatbayramov (proposed owner) | Not agreed; schedule during Week 2 planning |

## Open questions

| Question | What it would change | Follow-up |
| -------- | -------------------- | --------- |
| What is the upper limit of plugins running at once in our architecture, and what slows down past it? | How plugins pass a request between each other, and whether the core needs more than a simple chain | Not assigned at the meeting; carried into Week 2 architecture |
| Python or Go for the gateway? | The plugin-authoring experience for agents and the performance ceiling | Team decision, Week 2 planning |
| Do provider keys live in the gateway's configuration or in an external secret manager? | Deployment and security scope of MVP-0 | Week 2 planning |
| Does `VP-01` stay a privacy-preflight proposition, or become one plugin under a plugin-host proposition? | The framing of `VP-01` and `GAP-01`, and what MVP-0 demonstrates | Week 2 research update |

## Disagreements

| Your position | Customer's position | What you changed |
| ------------- | ------------------- | ---------------- |
| Users should be able to send requests through the gateway with their own provider keys, as in azamatbayramov's workplace | It is a poor practice; the gateway should hold a key pool, and building the option in encourages it | Kept only as an optional feature an operator can turn off; gateway-held keys are the default path |
| `VP-01` frames the product as a privacy preflight that masks or blocks text before forwarding (written direction, not presented) | Filtering personal data alone is a solved problem; the value is a plugin host where each company plugs in its own policy | At the meeting, the written proposition had not been revised. The subsequent October 3 [research revision](../../docs/research/value-proposition.md) now places privacy filtering inside the plugin-host direction; it is not presented as a decision made during the call |
