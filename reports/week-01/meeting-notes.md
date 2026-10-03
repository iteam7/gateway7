# Kickoff meeting notes

**Date:** 2026-10-02
**Duration:** approximately 49 minutes
**Participants:** azamatbayramov, Customer, Guest (a member of another course team on the same project)
**Prepared:** 2026-10-03 as sanitized summary notes from the existing automatic meeting record and participant corrections. These are not a verbatim transcript or notes taken live.

Publication permission for the verbatim transcript has not been confirmed. The participant does not recall asking the publication/private-sharing questions; the Customer initiated recording. The transcript has therefore been withheld from this revised public tree. Its previous public Git history is unchanged. Recording links and identity mappings remain outside the repository.

## Discussion in chronological order

The Customer first asked about research and the teams' project direction. Team 7 did not present its written value propositions; the session proceeded as a joint question-and-answer discussion. Only azamatbayramov attended for Team 7, and the team reports that partial attendance had been allowed.

The Customer described a modular system where a company's IT department can build or replace plugins for its own needs. Examples included access control, token usage, logging and code fingerprinting. Existing gateways and privacy tools were acknowledged. Personal-data filtering alone was not the intended product boundary.

The discussion then covered policy behavior. A plugin can block, log, flag, or permit and log according to the operator's needs. Both requests and responses should be inspectable. The stated priority was request hooks first, response hooks second, and routing third. Restarting the server to install a plugin was acceptable; hot loading was not required. Plugin authors can use coding agents, but the gateway cannot guarantee the correctness of their plugins.

On credentials, the preferred design was operator-managed provider keys with authenticated client access and potentially per-user model access. A simple server-side key configuration was discussed as an initial approach with an explicit security warning; an external secret-management integration remained an option. User-supplied provider keys were treated as a secondary, operator-disableable use case rather than the default.

The Customer said one or two provider API formats would be enough and accepted Claude and Gemini as initial targets. Python was preferred if practical; Python or Go was accepted for Team 7. Azamatbayramov explained that all team members knew Python, while Go was his personal preference. No final team implementation decision was demonstrated in the meeting record.

Focused plugin-authoring instructions and an example for coding agents were welcomed as a nice-to-have. The Customer then asked for the simplest runnable first milestone. Azamatbayramov proposed a proxy that adds a server-configured provider key, masks a simple synthetic phone-number pattern, forwards to one provider and returns the response. He estimated two to three weeks and wanted CI and linters first. This was an estimate, not a commitment to deliver a complete gateway for Assignment 1.

The final discussion covered AI-assisted development and architectural limits. The Customer welcomed responsible use of coding agents and asked the team to explain the limit of its plugin architecture rather than claim unlimited scale. No required numeric plugin count was agreed. A next-Friday meeting at the same time was discussed; individual attendance was not confirmed in this record.

## Evidence limits

The October 3 participant correction confirms that only azamatbayramov attended for Team 7 and that October 8 was not an agreed action deadline. No replacement deadline is invented here. The [meeting report](meeting-report.md) distinguishes meeting decisions, proposed follow-ups and unanswered questions. The [script](meeting-script.md) remains an honest retrospective question list, not claimed pre-meeting preparation.
