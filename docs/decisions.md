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
