# ADR-nnn: {short decision title}

- **Status:** Proposed
- **Created:** {YYYY-MM-DD}
- **Updated:** {YYYY-MM-DD}
- **Containers:** {names from the container view}
- **Addresses:** {one or more existing FR-nnn or QR-nn links}

Use the actual creation date; do not reconstruct an undocumented decision date.
Use Accepted only for a choice in force, citing its actual decision or implementation evidence; a retrospective record does not invent a new meeting or review.
Add `Decision` only when an existing Customer `DEC-nnn` is documented by this record.
Add `Superseded by` or `Dropped` only when that status requires it.
Keep this template unfilled; create a numbered file and an index row for each actual record.

## Context

{Describe the problem, genuine requirement/constraint links and implementation or discussion evidence. Distinguish a retrospective comparison from a recorded historical evaluation.}

## Considered Options

- **{Option name}.** {Describe it; for each rejected option explain why it loses.}
- **{Option name}.** {Describe it and its tradeoffs.}

## Decision Outcome

Chosen option: {name and reasoning}.

{State what is decided, its scope and its evidence. Keep review of this record separate from earlier acceptance of the implementation.}

## Consequences

- **{Quality attribute}.** {Explain the accepted effect and link the actual QR-nn that covers it.}
- **{Cost or limitation}.** {Explain the observable tradeoff.}

{Do not mark Accepted while a quality consequence lacks its QR coverage. Update the architecture index in the same change.}
{Distinguish the design's support for a QR from evidence that its response measure passed. Add an ADR link to Traces to in each FR this choice constrains; QR files name no ADR.}
