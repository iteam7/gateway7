# Gateway7 CLI

Use the CLI to start a gateway, send one message, or create and test middleware.
The examples below run from a [Python checkout](setup.md#install-from-a-checkout).
With an installed Gateway7 wheel, omit `uv run --locked`; `gateway7` also works outside the checkout.
`python -m gateway7` provides the same commands.

## Start a synthetic demo

```sh
uv run --locked gateway7 demo --host 127.0.0.1 --port 8000
```

The demo starts a gateway and a private local provider.
It needs no provider key and contacts no real model.
Its client token is the public value `gateway7-synthetic-client-token`, and its model is `fake`.

Send a request from a second terminal using [Send a message](#send-a-message).
The answer starts with `pong —` and echoes the transformed input.
The default chain masks phone numbers and emails, blocks `BLOCK-ME-TEST`, and replaces `SECRET-TEST` in responses.
Press Ctrl-C in the server terminal to stop both processes.

## Validate configuration

```sh
uv run --locked gateway7 validate --config config/openai.yaml
```

Expected output:

```text
Configuration valid: provider=openai; middleware=4
```

This checks YAML, the provider settings, plugin descriptors and middleware settings.
It needs no credentials and makes no provider call.
It imports trusted plugin factories, which may have their own side effects; it does not run plugin startup hooks.
Validation does not prove that credentials or a model will work.

## Run a configured server

First [supply the server credentials](setup.md#supply-server-credentials), then run:

```sh
uv run --locked gateway7 serve --config config/openai.yaml --host 127.0.0.1 --port 8000
```

Use `--config PATH` or set `GATEWAY_CONFIG` to the config path.
The default host is `127.0.0.1` and the default port is `8000`.
For local testing, `demo` provides a setup with no provider account.
The earlier `python -m gateway7 --config PATH --host HOST --port PORT` form still works.

## Send a message

With the demo running:

```sh
export GATEWAY7_TOKEN=gateway7-synthetic-client-token
uv run --locked gateway7 chat --message 'Contact synthetic@example.com' --max-tokens 1024
printf '%s' 'Contact synthetic@example.com' | uv run --locked gateway7 chat
```

Both commands return JSON with text `pong — Contact [EMAIL]` and synthetic usage counts.
Normal output goes to stdout; errors go to stderr.

| Option | Meaning |
| --- | --- |
| `--url` | Gateway origin; default `http://127.0.0.1:8000`. No credentials, path, query or fragment in the URL. |
| `--message` | One message. If omitted, read stdin. Input must be nonempty and at most 65,536 UTF-8 bytes. |
| `--max-tokens` | Output budget from 1 to 4,096; default 256. Some reasoning models need a larger budget. |
| `--token-env` | Environment variable holding the client token; default `GATEWAY7_TOKEN`. |
| `--model` | An allowed model ID. If omitted, use the server default, which must also be allowed for this client. |

For a real server, use your assigned gateway token, not a provider key or the demo token.
See [authentication](authentication.md) for client setup.
The server's HTTP body limit still applies.
Use the [HTTP API](api.md) when you need conversation history instead of a single message.

A non-200 response returns a nonzero exit without printing the server's arbitrary error body.
Ctrl-C while reading input or waiting for an answer returns exit 130.

## Generate and test middleware

```sh
uv run --locked gateway7 plugin init company_mask --directory .
uv run --locked gateway7 plugin test \
  --config company_mask/gateway.yaml --fixtures company_mask/fixtures.json
```

Expect `2/2 cases passed` from the generated example.
`init` creates a package under an existing directory and refuses to overwrite a target that already exists.
Use [the authoring guide](authoring.md) to edit and install the package.

For machine-readable results or a longer test run:

```sh
uv run --locked gateway7 plugin test \
  --config company_mask/gateway.yaml --fixtures company_mask/fixtures.json \
  --json --timeout 60
```

`--timeout` accepts 1–300 seconds; the default is 30 for the whole suite.
The report shows expected and actual values for each check.
The separate worker uses a synthetic provider, removes inherited credentials and blocks Python network and subprocess calls.
It is not an operating-system sandbox: test only trusted code and use synthetic fixtures.

## Exit codes and checks

| Exit | Meaning |
| --- | --- |
| `0` | Success, including an orderly Ctrl-C shutdown of `serve` or `demo` |
| `1` | Command/startup failure; for `plugin test`, an expected/actual mismatch |
| `2` | Invalid CLI arguments; for `plugin test`, invalid setup, worker failure, timeout or interruption |
| `130` | Interrupted `chat`, including while reading stdin |

Interrupting `plugin test` stops its worker and reports a failed run.
Use `uv run --locked gateway7 --help` or add `--help` to a subcommand for its options.
For project tests and package checks, follow [Checks and tests](setup.md#checks-and-tests).
The [middleware catalog](middleware-catalog.md) lists the reference policies and their detection limits.
