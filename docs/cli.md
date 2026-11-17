# Gateway7 CLI

Use the CLI to start and check a gateway, send one message, or create and test middleware.
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

After the one-time checkout installation and [private-file configuration](setup.md#supply-server-credentials), run:

```sh
uv run --locked gateway7 serve --config config/openai.yaml --secrets-file PATH
```

Use `--config PATH` or set `GATEWAY_CONFIG` to the config path.
The default host is `127.0.0.1` and the default port is `8000`.
Explicit `--host HOST` and `--port PORT` options remain available.
For local testing, `demo` provides a setup with no provider account.
The earlier `python -m gateway7 --config PATH --host HOST --port PORT` form still works.

`--secrets-file PATH` opts into one explicitly selected external file; omitting it preserves environment-only startup.
The file is a strict flat UTF-8 JSON object, at most 64 KiB, mapping configured environment-variable names to nonempty visible-ASCII strings without spaces.
Only names referenced by `provider.key_env`, configured client `token_env` settings, `auth.operator_token_env`, `auth.management_database_url_env` and the explicitly selected built-in HTTP proxy's `settings.url_env` are accepted.
On POSIX, the selected file must be a regular file owned by the current user with no group/other access; symlinks, FIFOs and devices are rejected.
Unknown keys, duplicate JSON members, wrong types and invalid credential, PostgreSQL connection or proxy values are errors; the whole file is validated before environment mutation, even when environment values shadow its entries.
Existing environment values take precedence, including empty strings; file-derived environment values are temporary and the original environment is restored before serving, including failed or cancelled startup paths.
The loader does not discover files or evaluate shell code; pass only the file path as an argument, and loader diagnostics never expose its values.
`validate`, plugin commands and offline execution do not read private startup files; no such file is required for their existing credential-free checks.

## Back up and restore managed state

Stop the gateway before either operation so its exclusive management owner has released the database.
Keep the PostgreSQL service running, and make its connection settings available to the command through the environment referenced by the selected YAML.
Compose `.env` files are not automatically read by a local Python invocation.

```sh
uv run --locked gateway7 backup --config config/admin-postgres.yaml \
  --output /private/gateway7-backup.json
uv run --locked gateway7 restore --config /private/empty-target.yaml \
  --input /private/gateway7-backup.json
```

The target YAML selects a separate empty management database of the same backend.
Restore rejects an existing nonempty target, invalid schema or checksum, unsupported backup version and cross-backend transfer.
This is backup recovery, and supplies no SQLite-to-PostgreSQL migration command.

The bounded, versioned backup contains profiles, credential digests, operators, encrypted provider settings, revisions, audit history, usage and reservations.
It contains no recoverable raw client/operator tokens or encryption key, but is still private access-control data.
The output is a new owner-only regular file; existing paths and symlinks are rejected rather than overwritten.
Keep `GATEWAY7_CONTROL_KEY` separately available when recovering encrypted provider credentials.
Verify a backup by restoring it into an isolated empty database and checking users, key revocations, operators, settings, usage and pending reservations before depending on it.

For Compose, run the installed command in a one-off gateway container after stopping the normal gateway, mounting a private backup directory writable by service UID/GID `10001:10001`.
Do not run a restore against the live production database or use `down --volumes` as a restart procedure.
The [managed deployment guide](authentication.md#persist-managed-state-with-compose) describes volume ownership and the operational boundary.

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

## Check a running gateway

With the [OpenAI `.env` Compose stack](setup.md#openai-with-a-env-file), check from inside the running container:

```sh
docker compose exec -T gateway gateway7 smoke --token-env GATEWAY7_CLIENT_TOKEN
```

This uses the gateway client token already passed to the container, so no local Python installation or second token variable is needed.

After [starting a real-provider server](setup.md#real-providers) and setting `GATEWAY7_TOKEN` in the client environment:

```sh
uv run --locked gateway7 smoke --model gpt-4.1-mini --max-tokens 256
```

This is an explicit live check: after successful prechecks it sends one short chat request, which can consume paid tokens.
It makes no automatic retries and sends no chat if a precheck fails.
A missing client token or invalid token format fails locally before any request.

The checks run in order: `/health` (HTTP 200, `status: ok`), `/ready` (HTTP 200, `status: ready`), anonymous `/v1/models` (HTTP 401), authenticated `/v1/models` (HTTP 200 with valid catalog shape), then authenticated `POST /chat`.
A valid empty catalog passes; requested-ID membership is not checked.
A catalog HTTP 503 fails smoke with `unexpected_status` and zero chat attempts; this smoke preflight rule does not block independently authorized direct generation.
A deadline reports `timeout`, with zero chat attempts before POST or one once the POST attempt has begun.
The command requires a gateway client token; a catalog result is never an authentication fallback.
`--model`, when supplied, is sent unchanged; the server still applies the effective provider/client restrictions.
Omit it to use the server's configured default, which is permission-checked rather than replaced with another model.
Readiness only checks local initialization, and the command does not independently identify which provider the server uses.

| Option | Meaning |
| --- | --- |
| `--url` | Gateway origin; default `http://127.0.0.1:8000`, with the same URL restrictions as `chat`. |
| `--token-env` | Client-token variable; default `GATEWAY7_TOKEN`. |
| `--model` | Optional allowed model ID. |
| `--max-tokens` | Chat output budget, 1–4,096; default 256. |
| `--timeout` | Whole-run deadline, 1–300 seconds; default 90. |

The JSON report contains `schema_version`, `passed`, `checks`, `chat_attempts` (0 or 1) and `duration_ms`.
Checks include their status, safe request IDs and, for a successful chat, validated usage counts or `null` when unknown.
It never prints model output, raw server error bodies, URLs or credentials.
Failure stops at the first unsuccessful check and returns exit 1; Ctrl-C returns 130.
Correlate a reported request ID with [safe server logs](observability.md#diagnose-a-failing-request) to investigate provider and middleware failures.
Passing smoke confirms the checked HTTP behavior, not complete privacy-policy coverage, billing accuracy or Customer acceptance.

## Generate and test middleware

Activate the environment containing the reviewed Gateway7 build, then work in a separate authoring folder:

```sh
gateway7 plugin init company_guard --template guard --directory .
gateway7 plugin inspect company_guard --json
gateway7 plugin test company_guard --json --timeout 60
gateway7 plugin dev company_guard --port 0
```

`init` creates an installable project and refuses an existing target.
The request-only `guard` starter has 12 cases across five profiles; the default `redact` starter has 10 cases and three positive profiles, with explicit early-mode refusals.
Both include strict settings, a public text helper, typed fixtures, unit tests, `CONTRACT.md` and `AGENTS.md`.
`test`, `inspect` and `dev` accept an optional project directory, defaulting to `.`.
They resolve module/config/fixtures/profiles from `[tool.gateway7.plugin]` in `pyproject.toml` and use explicit current project source.
Normal `validate`/`serve` load installed packages.

`test` emits schema-2 expected/actual reports and a per-profile evidence matrix.
`--timeout` accepts 1–300 seconds; the default is 30 for the whole suite.
`inspect` emits safe descriptor/settings-schema/hook information without startup hooks or provider calls; inspection does not verify behavior.
`dev` owns an IPv4-loopback gateway and synthetic upstream on automatic ports (`--port 0`), prints a platform-specific synthetic client command, and stops both after Ctrl-C.
A specified `--port` selects the gateway port only; there is no public-host option.
Dev uses the actual gateway HTTP pipeline, replaces credentials and management configuration in memory, and never changes project files.
Restart it after source edits.

The separate fixture worker removes inherited credentials and blocks Python networking and subprocess APIs.
Dev permits its owned local HTTP fixture and runs trusted source in a separate child with a minimal environment.
Neither path is an operating-system sandbox.
Use only trusted code and synthetic fixtures; reports include fixture values.
The authoring contract is Gateway7 `0.5.0.dev0`, project manifest 1 and fixture schema 2; the earlier explicit config/fixture flags and schema 1 are unsupported.
Follow [the first-plugin guide](authoring.md), [cookbook](plugin-cookbook.md) or [agent guide](plugin-agent-guide.md).

## Exit codes and checks

| Exit | Meaning |
| --- | --- |
| `0` | Success, including an orderly Ctrl-C shutdown of `serve`, `demo` or `plugin dev` |
| `1` | Command/startup failure; for `plugin test`, an expected/actual mismatch |
| `2` | Invalid CLI arguments; for plugin authoring, invalid setup, worker failure, timeout or interruption |
| `130` | Interrupted `chat` or `smoke`, including while reading chat input |

Interrupting `plugin test` stops its worker and reports a failed run.
Use `uv run --locked gateway7 --help` or add `--help` to a subcommand for its options.
For project tests and package checks, follow [Checks and tests](setup.md#checks-and-tests).
The [middleware catalog](middleware-catalog.md) lists the reference policies and their detection limits.
