# Glossary

The words Gateway7 uses in one way only.

## Request Flow

### Client

An application or developer that calls Gateway7 with its own bearer token and may use only the models in its configured allowlist.

**Defined by:** [client authentication and model permissions](authentication.md#configure-clients).

### Provider

The one LLM service, OpenAI, Claude or Gemini, that a running gateway is configured at startup to forward allowed requests to.

**Defined by:** [CON-01](product-vision.md#con-01).

### Provider Adapter

The gateway component that translates a normalized request for the configured provider, attaches the server-held provider key and normalizes the provider's response or error.

**Defined by:** [the architecture](architecture/README.md).

### Model Allowlist

The list of model identifiers on the configured provider that one client may request, checked before any middleware or provider call.

**Defined by:** [client authentication and model permissions](authentication.md#configure-clients).

## Plugins

### Middleware

A trusted, company-authored Python module that can change or deny a chat request before it reaches the provider and the response on its way back.
In the middleware configuration and guide, "plugin" means this middleware, using the `PLUGIN` descriptor and API version 2.

**Defined by:** [DEC-016](decisions.md#dec-016) and [the plugin guide](plugins.md#descriptor-and-hooks).

### Middleware Chain

The single ordered list of enabled middleware instances in the configuration, run in that order on the request and in reverse order on the response.

**Defined by:** [the plugin guide](plugins.md#order-enable-and-required).

### Deny

The result a middleware returns to stop a request or response, which the client receives as the gateway's safe `policy_denied` error.

**Defined by:** [the plugin guide](plugins.md#descriptor-and-hooks).

### Own-Work Budget

The time one middleware instance may spend on its own request and response work, excluding the time it waits for the next handler, set by `limits.hook_timeout_seconds`.

**Defined by:** [the plugin guide](plugins.md#deadlines-and-diagnosis).

### Provider Transport

A trusted networking extension that supplies the provider adapter's outbound HTTP transport.
Its `TRANSPORT` descriptor uses API version 1 and creates one transport at startup; it is separate from the middleware chain and has no `call_next`.
The built-in proxy transport is one such extension.

**Defined by:** [the transport guide](provider-transports.md) and [ADR-004](architecture/adr/ADR-004.md).

## Demonstration

### Synthetic Provider

The deterministic local stand-in for a real provider that the demo and tests use, which checks plugin behavior but proves nothing about a real provider.

**Defined by:** [DEC-011](decisions.md#dec-011).
