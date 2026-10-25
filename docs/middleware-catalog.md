# Reference middleware

These modules use the same API v2 contract as company-authored middleware.
They are deterministic reference implementations with synthetic regression fixtures, not a universal personal-data detector or a semantic safety classifier.
Start from [config/reference.yaml](https://github.com/iteam7/gateway7/blob/main/config/reference.yaml), or copy its plugin declarations into a real-provider configuration.
The [plugin guide](plugins.md) explains installation and the runner's failure and timeout behavior.

## Catalog

| Module | Behavior | Default direction |
| --- | --- | --- |
| `gateway7.plugins.phone_mask` | Replace the three documented Russian phone shapes with `[PHONE]` | Request, preserving existing empty-settings behavior |
| `gateway7.plugins.email_mask` | Replace conventional ASCII email addresses with `[EMAIL]` | Request and response |
| `gateway7.plugins.content_policy` | Match configured literal terms and block, log or redact | Request and response |

`phase` accepts `request`, `response` or `both` in every module.
Request processing includes **all history roles**, including system and assistant messages.
Masking/redaction preserves roles, message order and `max_tokens`; response processing preserves the original provider usage.
Original text is neither retained in plugin state nor logged, and replacement is irreversible.
Each instance stores immutable configuration only and can serve concurrent requests.

## Phone and email masking

```yaml
plugins:
  phones:
    module: gateway7.plugins.phone_mask
    required: true
    settings:
      phase: both
      replacement: "[PHONE]"
  emails:
    module: gateway7.plugins.email_mask
    required: true
    settings:
      phase: both
      replacement: "[EMAIL]"
middleware: [phones, emails]
```

`replacement` must be a nonempty string of at most 128 characters.
Replacement values are inserted literally: backslashes are not regex substitutions.
Use non-sensitive markers that do not themselves match the detector.

The phone detector recognizes exactly these shapes using ASCII digits and literal spaces:

- `+7 900 000-00-00`
- `8 (900) 000-00-00`
- `+79000000000`

Word/digit boundaries prevent masking inside longer identifiers.
Dates, order numbers, other country codes, other separators and Unicode digits are outside this detector's coverage.

The email detector covers ASCII dot-atom local parts, plus addressing, subdomains and hyphenated domain labels.
It enforces a 64-character local-part limit, 63-character domain-label limit and 254-character total limit.
Single-label domains, IP-address domains, quoted local parts, Unicode mailbox names/domains and punycode top-level domains are outside its coverage.
An ASCII address next to a Unicode word character is left unchanged to avoid masking only part of a larger identifier.
These boundaries deliberately favor a clear, testable contract; extend the fixtures before broadening production policy.

## Literal content policy

```yaml
plugins:
  guard:
    module: gateway7.plugins.content_policy
    required: true
    settings:
      terms: [BLOCK-ME-TEST]
      phase: request
      action: block
  output_redaction:
    module: gateway7.plugins.content_policy
    required: true
    settings:
      terms: [SECRET-TEST]
      phase: response
      action: redact
      replacement: "[removed]"
middleware: [guard, output_redaction]
```

| Setting | Contract |
| --- | --- |
| `terms` | Required: 1–32 distinct, nonblank literal strings, each 1–256 characters |
| `action` | `block` (default), `log` or `redact` |
| `phase` | `request`, `response` or `both` (default) |
| `case_sensitive` | Boolean, default `true`; `false` uses Python Unicode case-insensitive matching |
| `replacement` | Nonempty string, up to 128 characters; default `[removed]`; used for `redact` |

Terms are **substrings**, not words or regular expressions.
For example, `SECRET` also matches `SECRET-TEST`, while `A+B` matches literal `A+B`.
At the same position, the longest matching term wins; matches do not overlap.
Redaction makes one pass and does not rescan replacement text.
A caller can evade a literal rule by changing spelling or encoding; this module makes no prompt-injection prevention claim.

- `block` returns a core policy denial. A request hit makes zero provider calls. A response hit prevents delivery after one provider call; it cannot undo provider work.
- `log` passes the original request and response unchanged. A hit records only request ID, configured instance, direction, action and match count.
- `redact` replaces matching substrings and continues processing. It can be applied to requests, responses or both.

The policy logs never include matched terms or message text, for any action.
The HTTP denial is the core's safe `policy_denied` error; the configured instance is available in logs, not in the public error body.
Invalid actions, unknown settings, empty/oversized/duplicate terms and incorrectly typed values abort startup with the instance name and a sanitized diagnostic.

## Ordering and verification

The reference chain is `guard → phone → email → redact` on requests and the reverse on responses.
The guard sees the original input; response redaction runs before email and phone masking.
Changing this order changes which transformed text later middleware observes.
Mandatory instances use `required: true`, so accidentally disabling or omitting one fails startup.

Run the offline fixtures without credentials or network access:

```bash
uv run --locked pytest -q tests/test_plugins.py tests/test_reference_middleware.py
```

The fixtures cover positive and negative matches, full history, both directions, literal replacements, overlapping terms, case sensitivity, unchanged benign content, immutable configuration and payloads, usage preservation, safe logs, invalid settings, and provider-call counts for denials.
The fake provider and fixtures are synthetic. They do not establish Customer acceptance or detection quality against a company's real data.
