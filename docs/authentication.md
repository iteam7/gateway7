# Client authentication and model permissions

Gateway7 separates two credentials: a client bearer token authorizes calls to the gateway, and a provider API key is attached only by the server's provider adapter.
Each configured client has an explicit allowlist of models on the one selected provider.
A caller cannot choose a different provider, origin, plugin module or server credential.

## Configure clients

The real-provider examples enable authentication:

```yaml
provider:
  kind: openai
  model: gpt-4.1-mini
  key_env: OPENAI_API_KEY
auth:
  enabled: true
  clients:
    developer:
      token_env: GATEWAY7_CLIENT_TOKEN
      models: [gpt-4.1-mini]
```

Set `OPENAI_API_KEY` and `GATEWAY7_CLIENT_TOKEN` privately on the server.
The client sends the value of `GATEWAY7_CLIENT_TOKEN` as `Authorization: Bearer ...`; it never receives the provider key.
Client tokens must be distinct, 16–512 visible ASCII characters without spaces, and must not reuse the provider key.
Use independently generated random tokens for real users or applications.
Missing/invalid client variables, duplicate token values and provider-key reuse fail startup with a safe diagnostic.
`gateway7 validate` checks configuration structure without resolving secret values; actual startup performs these credential checks.

Add clients or change their model lists in YAML and restart the gateway.
`GET /v1/models` shows only the authenticated client's configured allowlist; it does not contact the provider or guarantee that the account has access to every configured ID.
A model outside the allowlist returns 403 before any middleware or upstream call.
An omitted native `/chat` model still has to be authorized: it uses `provider.model` as the default.

## Use the CLI

On the client, put its gateway credential in `GATEWAY7_TOKEN` and run:

```sh
gateway7 chat --model gpt-4.1-mini --message 'Reply with the word pong'
```

Use `--token-env ANOTHER_VARIABLE` to select another client-side environment variable.
There is no token command-line argument, so the credential need not appear in shell history or process arguments.
The server's `token_env` and CLI's `--token-env` may have different names; they must resolve to the same client token value.

## Synthetic demo

`gateway7 demo` enables authentication with the public fixture token `gateway7-synthetic-client-token` and allows model `fake`.
Use it only with the synthetic local demo:

```sh
export GATEWAY7_TOKEN=gateway7-synthetic-client-token
gateway7 chat --model fake --message 'Reply pong'
```

`config/demo.yaml` and `config/reference.yaml` explicitly disable authentication for legacy/offline synthetic fixtures.
Disabling authentication is permitted only for the fake provider; real providers require configured clients.
The Compose default uses the authenticated packaged demo, not those unauthenticated fixture configurations.

## Deployment boundary

The live Compose override forwards one selected provider environment variable and `GATEWAY7_CLIENT_TOKEN` to the gateway container.
It does not inject all provider keys available in the host shell.
Select the provider variable with `GATEWAY_KEY_ENV`, as shown in [setup](setup.md#real-providers).
Rotate client tokens by replacing the server environment value and restarting; there is no token-management API or persistent user database.

The local stack binds its published ports to localhost.
A shared deployment still needs HTTPS and a trusted network boundary around `/metrics`, `/health`, `/ready`, Prometheus and Grafana.
This authentication layer does not implement billing, quotas, rate limits, user registration or refresh tokens.
Tokens, client names and model IDs are omitted from metric labels; gateway logs record request IDs and fixed diagnostic codes without credentials or message text.
Installed Python middleware remains trusted code with access to the process environment; it is not isolated from server credentials by a security sandbox.
