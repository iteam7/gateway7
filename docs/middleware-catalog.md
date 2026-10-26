# Reference middleware

Mask supported phone numbers and email addresses, block selected terms, or remove text from an answer.
Try the demo, then copy the policy into your gateway configuration.
For a new company rule, follow [Generate, test and install a middleware](authoring.md).

## Catalog

| Module | What it does | Default direction |
| --- | --- | --- |
| `gateway7.plugins.phone_mask` | Replaces three phone formats with `[PHONE]` | Request |
| `gateway7.plugins.email_mask` | Replaces supported email addresses with `[EMAIL]` | Request and response |
| `gateway7.plugins.content_policy` | Blocks, logs or replaces configured text | Request and response |

### Try masking and response redaction

From a checkout prepared with the [setup guide](setup.md), start the demo:

```sh
uv run --locked gateway7 demo
```

With an installed Gateway7 environment, use `gateway7 demo` instead.
The demo uses all three modules and a local fake provider; it makes no paid API calls.
In another terminal, send this synthetic conversation:

```sh
export GATEWAY7_TOKEN=gateway7-synthetic-client-token
curl --silent --show-error --fail-with-body http://127.0.0.1:8000/chat \
  -H "Authorization: Bearer $GATEWAY7_TOKEN" \
  -H 'Content-Type: application/json' \
  --data '{
    "messages": [
      {"role": "user", "content": "Earlier: first@example.com."},
      {"role": "assistant", "content": "Saved phone: +7 900 000-00-00."},
      {"role": "user", "content": "Send +79000000000 to user@example.com. SECRET-TEST"}
    ]
  }'
```

This token is public and **only for the local demo**.
Expect HTTP 200 with these `text` and `usage` fields:

```json
{
  "text": "pong — Send [PHONE] to [EMAIL]. [removed]",
  "usage": {"input_tokens": 12, "output_tokens": 4}
}
```

The response also includes a new `request_id` for each call.
Phone and email masking runs on every history message before the provider call.
For example, the earlier messages become `Earlier: [EMAIL].` and `Saved phone: [PHONE].`.
The fake provider echoes the last message, then the response policy replaces `SECRET-TEST` with `[removed]`.
Phone and email masking also runs on the returned answer.

To try a request block in the same terminal:

```sh
uv run --locked gateway7 chat --message 'BLOCK-ME-TEST'
```

The CLI reports HTTP 403 and exits with code 1; the gateway makes no provider call for this request.
Omit `uv run --locked` when using an installed CLI.

## Phone and email masking

Both modules accept these settings:

| Setting | Values |
| --- | --- |
| `phase` | `request`, `response` or `both` |
| `replacement` | A nonempty string of at most 128 characters |

Set `phase: both` to cover input and output.
The phone module keeps its original request-only default when settings are empty.
Replacement text is inserted as written, including backslashes; use a marker that does not itself match the detector.

The phone detector recognizes exactly these shapes, with ASCII digits and the shown spaces:

- `+7 900 000-00-00`
- `8 (900) 000-00-00`
- `+79000000000`

Boundaries prevent partial matches such as `ID+79000000000` and `+790000000001`.
`ORDER-2026-1001` and `2026-10-25` stay unchanged; a value that matches a phone pattern is masked regardless of its meaning.
Other country codes, separators and Unicode digits are outside its coverage.

The email detector supports addresses such as `first.last+tag@sub.example.org` and `user@my-domain.example`.
It allows at most 64 characters before `@`, 63 per domain part between dots, and 254 in the whole address.
It does not cover names in quotes before `@`, domains without a dot, IP-address domains, Unicode addresses, or `xn--...` domain endings.
It also avoids partial matches next to Unicode word characters.
These are specific text patterns, not a complete personal-data detector; test your company's formats before use.

## Literal content policy

| Action | On a match |
| --- | --- |
| `block` | Return `policy_denied` (HTTP 403). A request block prevents the provider call; a response block stops delivery after that call. |
| `log` | Pass the text unchanged and log the instance, direction, action and match count with the request ID. |
| `redact` | Replace matching text and continue. The default replacement is `[removed]`. |

The default action is `block`, in both directions.
Set `phase` to `request`, `response` or `both` for each instance.
`terms` is required: use 1–32 distinct, nonblank strings, each at most 256 characters.
`replacement` has the same 1–128 character limit as the maskers.

Terms match literal **substrings**: `SECRET` also matches `SECRET-TEST`, and `A+B` matches the written plus sign.
They are not regular expressions.
Matching is case-sensitive unless `case_sensitive: false` enables Python's Unicode case-insensitive matching.
At one position, the longest matching term wins; matches do not overlap.
Redaction makes one pass and does not check the replacement again.
A change of spelling or encoding can avoid a literal rule; this module does not detect the meaning of a prompt.

Policy logs contain no matched terms or message text.
The public denial names the safe error code; the configured instance name is available in logs.

## Ordering and verification

To combine the recipe in your YAML, keep its `provider`, `auth` and `limits` sections and use:

```yaml
plugins:
  guard:
    module: gateway7.plugins.content_policy
    required: true
    settings:
      terms: [BLOCK-ME-TEST]
      phase: request
      action: block
  phone:
    module: gateway7.plugins.phone_mask
    required: true
    settings: {phase: both}
  email:
    module: gateway7.plugins.email_mask
    required: true
    settings: {phase: both}
  redact:
    module: gateway7.plugins.content_policy
    required: true
    settings:
      terms: [SECRET-TEST]
      phase: response
      action: redact
middleware: [guard, phone, email, redact]
```

The request enters `guard`, `phone`, `email`, then `redact`; the response returns in reverse order.
The guard sees the original request, while redaction sees the provider's answer before the maskers do.
Changing the order changes which text each instance checks.
A complete synthetic configuration is in [config/reference.yaml](https://github.com/iteam7/gateway7/blob/main/config/reference.yaml).

A `required: true` instance cannot be disabled or left out of the chain.
Invalid settings stop startup; middleware errors and timeouts stop processing rather than skip a filter.
The built-ins do not retain original text in instance state or logs.
They preserve message roles, order, generation limits and provider usage.
Installed plugins are trusted Python code in the gateway process: blocking or cancellation-resistant code cannot be forcibly stopped there.
See the [middleware API and failure rules](plugins.md) for the full contract.

From a checkout, run the synthetic regression fixtures:

```sh
uv run --locked pytest -q tests/test_plugins.py tests/test_reference_middleware.py
```

These tests cover history and responses, unchanged benign text, safe logs, invalid settings and provider-call counts.
Use [offline fixtures](authoring.md#fixture-schema) to add your company's synthetic examples before changing a policy.
