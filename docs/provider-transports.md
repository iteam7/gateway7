# Provider transports and proxies

A provider transport controls how Gateway7 sends outbound HTTP requests to its configured LLM provider.
It does not change the provider, model permissions or middleware order.
Without `provider.transport`, the gateway connects directly.

## Configure the built-in proxy

Start with an existing [provider configuration](setup.md#real-providers).
For example, add `transport` to the `provider` section in `config/openai.yaml`, keeping its other sections:

```yaml
provider:
  kind: openai
  key_env: OPENAI_API_KEY
  model: gpt-4.1-mini
  timeout_seconds: 30
  transport:
    module: gateway7.transports.http_proxy
    settings:
      url_env: GATEWAY7_PROXY_URL
```

Only the environment variable's name belongs in YAML.
The complete proxy URL, including any username/password, stays in the server environment or secret manager.
The built-in accepts HTTP and HTTPS proxy endpoints; SOCKS is not supported.
Use at most 4096 ASCII characters, with a hostname or IP address, an optional port and percent-encoded user information when needed.
Whitespace and control characters are rejected.
Only an empty path or `/` is allowed; query strings and fragments are rejected.

With the [Gateway7 environment active](authoring.md#generate-a-project), validate the file:

```sh
gateway7 validate --config config/openai.yaml
```

Expect `Configuration valid: provider=openai; middleware=4` for the sample configuration.
Validation imports the trusted transport module and checks its descriptor and settings.
It does not call its factory, read the proxy variable, create an HTTP client or contact the proxy.
The built-in therefore validates even when the proxy variable is missing or contains an invalid URL.
Custom imports and settings validators still execute trusted Python code.

Supply the [provider key and gateway client token](setup.md#supply-server-credentials), then read the proxy URL without echoing it in a local Bash session:

```sh
read -r -s -p 'Provider proxy URL: ' GATEWAY7_PROXY_URL
printf '\n'
export GATEWAY7_PROXY_URL
gateway7 serve --config config/openai.yaml
```

Startup checks that the named variable contains a valid proxy URL and creates the transport.
It does not test proxy availability, credentials or provider access; the first provider request does that.
`/ready` reports local startup state, not successful proxy connectivity.
Use the [normal authenticated chat request](setup.md#start-the-server-and-send-a-request) to check access; a real model request can consume paid tokens.
Restart after changing the transport, settings or proxy credentials.
Remove `provider.transport` and restart to return to a direct connection.

The [live Compose override](https://github.com/iteam7/gateway7/blob/main/compose.live.yaml) forwards `GATEWAY7_PROXY_URL` from the host environment automatically.
For a custom variable name, set `GATEWAY_PROXY_ENV` to the same name used in `provider.transport.settings.url_env` before starting Compose.
Forwarding a variable does not enable proxy routing: the selected YAML must contain the explicit `provider.transport` configuration above.
Do not print the expanded live Compose config: it can contain injected credentials.

## HTTP proxy and TLS boundary

The URL scheme describes the connection to the proxy itself.
An HTTP proxy can reach an HTTPS LLM endpoint through an HTTP CONNECT tunnel; an HTTPS proxy also protects the connection to the proxy with TLS.
Choose the scheme your proxy supports, as described in the [HTTPX proxy guide](https://www.python-httpx.org/advanced/proxies/).

The direct transport and built-in proxy keep TLS verification enabled, connection retries disabled and redirects disabled.
Gateway7 does not infer a proxy from `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY` or `NO_PROXY`.
It also ignores `SSL_CERT_FILE` and `SSL_CERT_DIR`; those variables do not change its trust store.
The built-in has no setting to disable TLS verification or install a custom CA.

The built-in proxy uses a separate underlying HTTPX transport for each request and response stream, then closes it on completion, error or cancellation.
It does not reuse keepalive connections across requests; each HTTPS request needs a new CONNECT tunnel and TLS handshake.
This is a temporary resource-cleanup workaround for the pinned HTTP transport stack, described in [ADR-004](architecture/adr/ADR-004.md).
The direct connection mode is unchanged.

Use a proxy you trust and protect its credentials.
An HTTP proxy endpoint receives proxy authentication without TLS on that connection, even when the provider connection is an HTTPS tunnel.
The synthetic fake provider uses HTTP, so a forwarding proxy can see its fixture text and synthetic provider credential.
Keep that mode local and use synthetic data only.

Transport failures use the existing safe provider-error response and [provider diagnostics](observability.md#provider-failure-reasons).
Gateway diagnostics do not echo the proxy URL, credentials or arbitrary transport exception text.

## Write a transport extension

Install the module in the same Python environment as Gateway7 and name it under `provider.transport.module`.
It exports `TRANSPORT`, using API version 1 and a strict, frozen Pydantic settings model.
For example, this minimal module creates a direct HTTP transport:

```python
import httpx
from pydantic import BaseModel, ConfigDict

from gateway7.transport_api import TransportDescriptor


class Settings(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


def create(settings: Settings) -> httpx.AsyncBaseTransport:
    return httpx.AsyncHTTPTransport(verify=True, trust_env=False, retries=0)


TRANSPORT = TransportDescriptor(
    id="company_direct",
    api_version=1,
    settings_model=Settings,
    create=create,
)
```

The factory is synchronous and returns a fresh `httpx.AsyncBaseTransport` once per gateway startup.
Gateway7 owns that instance and calls its `aclose()` once through the provider client during cleanup; do not share it between application instances or close it from another owner.
A wrapper transport must close its own delegated resources in `aclose()`.
If a factory raises, it must release any resources it already created.
The [HTTPX transport contract](https://www.python-httpx.org/advanced/transports/#custom-transports) defines `handle_async_request()` and asynchronous response streams.

Transport API 1 is separate from [middleware API 2](plugins.md#descriptor-and-hooks): it has no `call_next` and is not placed in the middleware list.
A transport receives outbound HTTP requests, including provider credentials and message bodies.
Imports, settings validators and factories are trusted Python code with normal process permissions; they are not sandboxed.
Keep module imports and settings validation free of network and environment lookups so configuration validation stays offline.
Custom transports must preserve TLS verification and the no-retry policy themselves; the gateway cannot enforce those internals on arbitrary Python code.

## Offline middleware tests

`gateway7 plugin test` always uses its synthetic fixture provider.
It checks the configuration's structure but does not import, validate settings for, or initialize the selected provider transport.
The worker does not inherit proxy credentials, and its Python network guard remains active.
Passing middleware fixtures therefore says nothing about a transport's availability or behavior.
See the [offline execution boundary](authoring.md#offline-execution-boundary) before running trusted extensions.
