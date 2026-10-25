# Gateway7 CLI

The installed `gateway7` command works outside the source checkout.
During development, prefix it with `uv run --locked` from the repository root.
`python -m gateway7` exposes the same commands.

## Start a synthetic demo

```sh
gateway7 demo --host 127.0.0.1 --port 8000
```

This starts the gateway and a private loopback HTTP upstream with a temporary synthetic credential.
It does not require provider credentials, contact an external model or record prompts.
Chat/model access uses the public synthetic bearer token `gateway7-synthetic-client-token`; the allowed model is `fake`.
The fixture echoes `pong — <transformed message>`, with fixed synthetic token counts.
The default chain blocks `BLOCK-ME-TEST`, masks the documented phone/email formats in both directions, and redacts `SECRET-TEST` from responses.
Ctrl-C shuts down both processes.

## Validate configuration

```sh
gateway7 validate --config config/openai.yaml
```

Exit 0 means YAML, provider origin/model, module descriptors, settings and middleware references passed validation.
The command imports and constructs trusted plugins; it does not run lifecycle hooks or HTTP requests, and does not require credentials.
Arbitrary installed Python code is still trusted code and may have its own import/factory side effects.
Validation does not establish that credentials work or the selected model is available.

## Run a configured server

```sh
gateway7 serve --config config/openai.yaml --host 127.0.0.1 --port 8000
```

`--config` can instead come from `GATEWAY_CONFIG`.
Real credentials are read from the configured server environment variable during startup.
`serve` requires a configuration path; use `demo` for a zero-configuration start.
The original `python -m gateway7 --config PATH --host HOST --port PORT` syntax remains supported.

## Send a message

```sh
export GATEWAY7_TOKEN=gateway7-synthetic-client-token
gateway7 chat --message 'Reply with the word pong' --max-tokens 1024
printf '%s' 'Contact synthetic@example.com' | gateway7 chat
```

`--url` selects the running gateway origin and defaults to `http://127.0.0.1:8000`.
It accepts an HTTP(S) origin without credentials, path, fragment or query parameters.
`--token-env` reads a client bearer token from an environment variable, defaulting to `GATEWAY7_TOKEN`; no token is accepted directly as a command-line value.
`--model` selects an allowed model; omit it to use the server default, which must also be permitted.
See [authentication](authentication.md) for real client tokens.
Omit `--message` to read standard input; input must be nonempty and at most 65,536 UTF-8 bytes, and the configured HTTP body limit still applies.
`--max-tokens` defaults to 256 and accepts 1–4096; some reasoning models need a larger budget to produce a final answer.
The command prints one JSON object containing `text` and `usage` to standard output; diagnostics go to standard error.
A non-200 gateway response returns a nonzero exit without printing an arbitrary error body.
The CLI is a one-message convenience client; use `POST /chat` directly for conversation history.

## Generate and test middleware

```sh
gateway7 plugin init company_mask --directory .
gateway7 plugin test --config company_mask/gateway.yaml --fixtures company_mask/fixtures.json
gateway7 plugin test --config company_mask/gateway.yaml --fixtures company_mask/fixtures.json --json
```

`init` creates an installable package below an existing directory and refuses to overwrite an existing target.
`test` uses a separate worker with a deterministic fixture provider, no inherited credentials, blocked Python networking/subprocess creation and a default 30-second wall-clock limit.
Use `--timeout SECONDS` from 1 to 300 to change the whole-suite limit.
The human report shows expected and actual values; `--json` emits one machine-readable report.
Only use synthetic fixtures and trusted plugin code. The [authoring guide](authoring.md) explains the fixture schema, installation and trust boundary.

## Exit codes and checks

Exit 0 means success or an orderly Ctrl-C shutdown, exit 1 means a command/startup failure, and invalid CLI arguments return exit 2.
`plugin test` uses exit 0 for all checks passing, 1 for expected/actual mismatches and 2 for invalid setup, interruption or worker timeout.
Interrupting an offline test terminates its worker and never reports a successful fixture run.
Use `gateway7 --help` or `gateway7 COMMAND --help` for options.

For deterministic policy and adapter verification from a checkout:

```sh
uv run --locked pytest -q
uv run --locked python -m demo.run
```

The [middleware catalog](middleware-catalog.md) describes the actual detection coverage and test fixtures.
