# Client authentication and model permissions

Give each application its own gateway token and optionally restrict the models it may use.
Gateway7 checks authentication and the effective provider/client permissions before it runs middleware or generates an answer.

| Credential | Who holds it | What it authorizes |
| --- | --- | --- |
| Gateway client token | The calling application and gateway server | Calls to `/chat`, `/v1/chat/completions`, `/v1/responses` and `/v1/models` |
| Provider API key | The gateway server | Outbound calls to the selected LLM provider |

The application sends its gateway token in `Authorization: Bearer ...`.

## Synthetic demo

Start the packaged demo with the [setup guide](setup.md#install-from-a-checkout), then set these public test values in the client terminal:

```sh
export GATEWAY7_URL=http://127.0.0.1:8000
export GATEWAY7_TOKEN=gateway7-synthetic-client-token
```

### Check allowed and denied requests

Send an allowed request:

```sh
curl --silent --show-error --write-out '\nHTTP %{http_code}\n' \
  "$GATEWAY7_URL/v1/chat/completions" \
  -H "Authorization: Bearer $GATEWAY7_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"model":"fake","messages":[{"role":"user","content":"Hello"}]}'
```

Expect HTTP 200 and `pong — Hello` in `choices[0].message.content`.
Now use a model that this client is not allowed to call:

```sh
curl --silent --show-error --write-out '\nHTTP %{http_code}\n' \
  "$GATEWAY7_URL/v1/chat/completions" \
  -H "Authorization: Bearer $GATEWAY7_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"model":"not-allowed","messages":[{"role":"user","content":"Hello"}]}'
```

Expect HTTP 403 with `error.code` equal to `model_forbidden`.
No middleware or provider call runs for that request.
Authenticated `GET /v1/models` lists the allowed IDs; this demo allows only `fake`.

Check missing and wrong credentials:

```sh
curl --silent --show-error --write-out '\nHTTP %{http_code}\n' \
  "$GATEWAY7_URL/v1/models"

curl --silent --show-error --write-out '\nHTTP %{http_code}\n' \
  "$GATEWAY7_URL/v1/models" \
  -H 'Authorization: Bearer gateway7-synthetic-wrong-token'
```

Both return HTTP 401 with `error.code` equal to `unauthorized`.
The same token and model checks protect native `/chat`.
Malformed, duplicated or unknown bearer credentials also fail with 401.
See [API examples](api.md) for complete native, curl and Python SDK requests.

Add `--fail-with-body` when scripts should stop on HTTP errors.

## Configure clients

Keep the provider and middleware settings from an [OpenAI provider configuration](setup.md#real-providers).
Replace its `auth` section, for example with these two applications:

```yaml
auth:
  enabled: true
  clients:
    chat_app:
      token_env: GATEWAY7_APP_TOKEN
      models: [gpt-4.1-mini]
    worker:
      token_env: GATEWAY7_WORKER_TOKEN
      models: [gpt-4.1-mini, gpt-4.1]
```

`provider.allowed_models` is an optional provider-wide restriction, and each client's `models` is an optional additional restriction; effective permissions are their intersection.
The same rules apply independently at both levels:

| Setting | Meaning |
| --- | --- |
| Omitted | No restriction at that level |
| Explicit nonempty list | Permit only its distinct entries, at most 64 IDs |
| `[]` | Deny every model |
| Explicit `null`, wrong types or duplicate IDs | Configuration error, not unrestricted access |

`provider.model` is the default, not a whitelist; a forbidden default is denied rather than replaced with another model.
Use model IDs your provider account can access; permission at the gateway does not prove that the provider will accept a request.
OpenAI IDs are opaque literal strings of at most 1024 UTF-8 bytes: colon and slash are supported, while whitespace, control, format and surrogate characters are rejected.
Non-OpenAI providers retain their existing URL-safe ID validation.
Permitted IDs are forwarded unchanged through the supported text Chat/Responses contracts; no endpoint, modality or parameter adaptation is inferred from the ID.
The [authenticated catalog](api.md#model-catalog-and-permission-filtering) is permission-filtered, but missing catalog membership is not an authorization denial and discovery failure never broadens permissions.

Supply both client tokens and the provider key through the server environment, secret manager or [explicit private startup file](setup.md#supply-server-credentials); YAML holds variable names only.
Clients can store their own token as `GATEWAY7_TOKEN`.

Client tokens must be distinct, 16–512 visible ASCII characters without spaces, and different from the provider key.
Generate random tokens for real applications.
Missing/invalid values, duplicates and provider-key reuse prevent startup.

Validate the edited file and restart as shown in [setup](setup.md#real-providers).
Validation needs no credentials and makes no provider call; startup checks credential values.
Both commands load trusted middleware code, as described in [setup](setup.md#select-and-validate-a-config).

Authentication may be disabled only for the fake provider, as in legacy `config/demo.yaml` and `config/reference.yaml` fixtures.
Only the configured default may be used anonymously, and it must also pass `provider.allowed_models`; omitted restrictions do not enable anonymous real-provider access.
The packaged demo and default Compose stack enable it.

## Use the CLI

From the checkout, using the demo variables above:

```sh
uv run --locked gateway7 chat \
  --url "$GATEWAY7_URL" \
  --model fake \
  --message 'Hello'
```

Expect `pong — Hello` in `text`.
The CLI reads `GATEWAY7_TOKEN`; use `--token-env ANOTHER_VARIABLE` to select a different variable.
See the [CLI reference](cli.md) for other options.

## Deployment boundary

Change clients, permissions or tokens through server configuration/environment and restart.
There is no token-management API, user database, billing or per-client quota/rate limit.

The supplied live Compose override forwards the provider key and `GATEWAY7_CLIENT_TOKEN` for the single-client samples.
Using the two-client section above with Compose also requires forwarding `GATEWAY7_APP_TOKEN` and `GATEWAY7_WORKER_TOKEN`; see [setup](setup.md#real-providers).

A shared deployment needs HTTPS and restricted access to anonymous `/health`, `/ready` and `/metrics` endpoints, Prometheus and Grafana.
Installed Python middleware is trusted code with access to server credentials.
