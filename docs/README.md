# Gateway7

<!-- Preserve links to the previous page heading. -->
<!-- markdownlint-disable MD033 -->
<div id="documentation"></div>
<!-- markdownlint-enable MD033 -->

**Your application. Your policies. One route to an LLM.**

Put Gateway7 between your application and OpenAI, Claude or Gemini.
Keep the provider key on the server, choose which models each client can use, and apply your team's rules to messages and answers.
Start with a local demo that needs no provider account.

**Understand the design:** [what runs](architecture/README.md#container-view), [where the code lives](architecture/README.md#code-map), and [how a request is handled](architecture/README.md#sequence-view).

## Choose your path

<!-- markdownlint-disable MD033 -->
<div class="guide-grid" markdown="1">

<div class="guide-card" markdown="1">

01 · Try it

[Send your first request](quickstart.md)

Run the demo with Docker Compose, see masked text, and open the Grafana dashboard.

</div>

<div class="guide-card" markdown="1">

02 · Connect your app

[Use curl or the OpenAI SDK](api.md)

Keep your text-chat client and point it at the gateway's HTTP API.

</div>

<div class="guide-card" markdown="1">

03 · Control access

[Set client tokens and model access](authentication.md)

Give each client its own gateway credential and a list of allowed models.

</div>

<div class="guide-card" markdown="1">

04 · Apply your policies

[Mask, block and redact](middleware-catalog.md)

Try phone and email masking, literal content rules, and response redaction.

</div>

<div class="guide-card" markdown="1">

05 · Write a middleware

[Generate, test and install](authoring.md)

Create a Python package and check it with synthetic fixtures before deployment.

</div>

<div class="guide-card" markdown="1">

06 · Run the service

[Configure a provider](setup.md#real-providers) · [Monitor requests](observability.md)

Move from the demo to a real provider, then follow outcomes, usage and failures.
Use a [provider transport](provider-transports.md) when the gateway must connect through a proxy.

</div>

</div>
<!-- markdownlint-enable MD033 -->

## How it works

The gateway checks the client token and model before running middleware.
One ordered chain wraps the configured provider: request processing follows the list, and response processing runs in reverse.
A denied request never reaches the provider; a denied answer is not delivered to the client.
Follow the [numbered request view](architecture/README.md#sequence-view), then open the [component and code map](architecture/README.md#component-view) to find the implementation.

## What to expect

This is a local pilot for **nonstreaming, text-only chat** with one configured provider per instance.
Python middleware is trusted code in the gateway process; installing or changing it requires a restart.
The demo proves the local workflow with synthetic answers, while real-provider access depends on your account and model permissions.

Use the [CLI reference](cli.md) for commands and exit codes, or the [middleware API reference](plugins.md) for lifecycle, ordering and failure behavior.
The [demonstration guide](demo.md) keeps the longer walkthrough and acceptance evidence separate from this getting-started path.

## Project documentation

- **Product:** [vision](product-vision.md), [threshold of success](threshold-of-success.md), [threshold review proposal](threshold-review.md), [plan](project-plan.md), [risks](risks.md), [glossary](glossary.md).
- **Requirements:** [functional requirements](functional-requirements/README.md), [quality requirements and priority matrix](quality-requirements/README.md).
- **Architecture decisions:** [ADR-001](architecture/adr/ADR-001.md), [ADR-002](architecture/adr/ADR-002.md), [ADR-003](architecture/adr/ADR-003.md), [ADR-004](architecture/adr/ADR-004.md), [ADR template](architecture/adr/TEMPLATE.md), [container source](architecture/container.py), [context source](architecture/context.mmd).
- **Project records:** [decisions](decisions.md), [assumptions](assumptions.md), [Definition of Done](definition-of-done.md).
- **Research:** [alternatives](research/alternatives.md), [comparison](research/comparison.md), [gap analysis](research/gap-analysis.md), [value proposition](research/value-proposition.md).

[Source repository](https://github.com/iteam7/gateway7) · [User stories](https://github.com/iteam7/gateway7/issues?q=type%3A%22User+Story%22)
