# Operate the administration console

Open `/operator/console` on your gateway and sign in with your operator username and password.
The [PostgreSQL administration setup](authentication.md#manage-users-in-the-operator-console) remains the normal deployment path; SQLite is available for a local installation.
An administrator can change accounts, provider settings, policies, pricing and budgets without restarting the gateway.
A viewer can inspect the workspace and download reports, but cannot change configuration, issue credentials, preview a policy or run a provider connection test.

## First sign-in

The deployment operator enables managed administration and supplies the separate recovery credential once.
If this is a new installation, create the first ordinary administrator through that recovery path:

1. Open the console and select **Use a recovery or automation token**.
2. Enter the server's recovery operator token and select **Connect**.
3. Open **Operators** and fill the operator form.
   Set **Username**, **Display name**, **Role** to **Administrator**, and **Sign-in method** to **Password account**.
   Choose a private password containing 12–128 characters and at most 512 UTF-8 bytes.
4. Select **Create operator**, then sign out of the recovery connection.
5. Sign in with that username and password.
   Select **Remember me on this device** only when the browser should retain the login after closing.

There is no public signup.
An existing administrator creates additional administrator or viewer accounts through the same **Operators** view.
The username is the operator's stable ID; a display name is a separate label.
Password account creation returns safe account metadata, not a bearer token to copy.
Keep the recovery token in the deployment's secret store for recovery and automation.

## Find the right workspace

Use the sidebar to choose one task at a time:

| View | Use it for |
| --- | --- |
| **Overview** | Check setup status and choose the next operational task |
| **Users & keys** | Create application clients, set their model permissions and issue client keys |
| **Models** | Review the provider, defaults, aliases and effective model access |
| **Policies** | Build, preview and activate shared or client-specific text policies |
| **Plugins** | Build a draft global chain, preview each step and activate a saved version |
| **Usage** | Filter usage and download reports |
| **Budgets & pricing** | Set prices and UTC usage allowances |
| **Operators** | Create sign-in accounts, assign roles, reset passwords and manage automation credentials |
| **Activity** | Review administrative changes and safe request diagnostics |

A user/client in **Users & keys** calls model APIs with an application key.
An operator signs in to administer or inspect the gateway.
Creating an operator does not grant that person a client key or model access.

## Stay signed in and sign out

By default, an ordinary login has a 12-hour absolute server lifetime and uses a browser-session cookie.
**Remember me on this device** uses a persistent cookie with a seven-day default lifetime.
The deployment can configure each lifetime between one minute and seven days, and neither option extends the operator's own expiration.
Refreshing the page or restarting the gateway preserves a valid stored session; ordinary browser-session cookies may be discarded when the browser closes.
Use **Sign out** to end the current session immediately.
Resetting an operator's password, changing its role or revoking that operator invalidates all of its sessions, including one open in another browser.
After resetting your own password, sign in again on the next request.

The browser keeps the opaque session credential in an HttpOnly, SameSite=Strict cookie rather than exposing it to page scripts or local storage.
Shared deployments require HTTPS; see the [session deployment settings](authentication.md#password-sessions-and-https).
Recovery and automation tokens remain an explicit alternative and are held only in page memory.

## If a step does not work

| What you see | Next step |
| --- | --- |
| Sign-in fails | Check the username/password with an administrator; use a password reset rather than creating a second identity |
| Sign-in is temporarily rate-limited | Wait before retrying; repeated guesses consume the bounded login allowance |
| Sign-in returns to the login form | Check HTTPS and cookie settings before replacing credentials |
| A saved edit conflicts with another change | Refresh, inspect the latest values and apply your intended edit again |
| A preview passes but an application request is denied | Check the configured baseline and the full request's selected phase; preview covers only plain text |

## Users and named keys

Search users by ID or owner, filter by state, owner or tag, and use the page controls for larger directories.
A user has an owner, tags, enabled state, canonical model permissions, an optional default model, request-rate and concurrency limits, and ordered additional middleware.
The table distinguishes configured model permissions from their effective intersection with the gateway-wide policy.
A warning identifies a default model that the user cannot call.
An explicit user default must belong to that user's effective permissions.

Use **Keys** on a user row to inspect its named credentials.
Issuing another named key preserves existing keys, so separate applications can rotate or revoke their credentials independently.
New named credentials expire after 90 days by default and may expire at most one year after issuance.
Expiration inputs are UTC even when the browser uses another time zone.
Only imported legacy client keys can lack an expiration.

Creation and rotation show the raw credential once in the temporary credential panel.
Save it securely before dismissing the panel.
Disconnecting, navigating away or losing authentication clears the displayed credential; browser storage is not used.
Revoking a key denies subsequent requests using that key while leaving the user's other active keys available.
Suspending or deleting the user denies all its credentials on subsequent requests.
Already admitted work retains its original policy snapshot and can finish.

## Individual operators and audit

Create an individual password account with the administrator or viewer role rather than sharing the server's recovery credential.
Use **Reset password** on an operator to replace its password and invalidate its browser sessions.
Named operators retain an expiration; renew it through the account controls before it expires.
The recovery operator is shown as `bootstrap` and cannot be edited in the console.
An optional automation sign-in method issues an expiring bearer credential with explicit rotation and revocation controls.
Password login and application client keys are independent of that automation credential.
The server enforces the current role, expiration and revocation, including requests waiting before a configuration commit.

The audit panel filters changes by actor, action, target and UTC interval.
Records contain the attributed operator, changed configuration fields, timestamp and request identifier.
Raw credentials, encrypted credential values and conversation content do not appear in audit output.

Configuration edits carry the revision of the state that was edited.
If another administrator changes that state first, the server returns HTTP 409 rather than overwriting the newer state.
Refresh the workspace, review the current values and apply the intended change again.

## Provider and model controls

The provider panel manages one active provider: OpenAI, Anthropic Claude, Google Gemini or the synthetic fixture.
It edits the default canonical model, gateway-wide model permissions, approved provider origin, timeout, concurrency cap and aliases.
Custom provider origins and multiple simultaneous upstreams remain outside this interface.

Aliases map a client-facing name directly to one canonical model ID.
Alias chains and cycles are rejected.
Permissions and user defaults use canonical IDs; an incoming alias is resolved before model authorization and is pinned outside middleware.

The model registry identifies configured models, aliases, global permissions and the current default.
OpenAI's account catalog can be refreshed explicitly.
Other adapters show the configured registry with availability marked as unverified.
Catalog membership does not establish that every generation request will succeed, and catalog failure never broadens authorization.

Saving provider settings validates a candidate connection before committing the change.
Existing admitted requests keep their previous provider instance until their work and delivery drain.
The displayed connection status records an explicit check and its timestamp; it is not a continuous provider health guarantee.
OpenAI checks its account catalog, while the other supported adapters send a small synthetic generation request.
Those checks can incur provider charges and do not represent a user's ordinary gateway usage.

### Store a new provider credential

Provider credentials supplied in the console are write-only and encrypted at rest with Fernet.
Configure `GATEWAY7_CONTROL_KEY` privately on the server before saving a new credential:

```bash
python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

Store the generated key in the deployment's secret manager or private environment configuration, including the administration Compose deployment.
Keep the same key available after a restart or a backup restore.
A missing, incorrect or corrupted key prevents loading an encrypted provider credential rather than silently falling back to an environment credential.
Changing the encryption key requires separately re-encrypting the stored provider credential; replacing the environment value alone is not a rotation procedure.

Leaving the provider credential field empty retains the current credential.
Changing provider kind requires supplying its new credential explicitly.
Credentials must differ from client and operator credentials.
The console reports whether a credential is configured and never returns its value.

## Test and activate a plugin chain

1. Open **Plugins** at `/operator/console#plugins` as an administrator.
   Enter a **Plugin ID** and **Name**, choose **Mask phone numbers**, keep **Requests**, then select **Add to draft**.
2. Use **Up**, **Down**, **Disable** or **Enable** on a row to edit the draft.
   Requests run server-configured instances first, followed by globally assigned policies and then the new template plugins.
   Within the server-configured group, required steps stay enabled in fixed positions.
   A disabled custom module requires deployment configuration before it can run.
3. Choose **Load phone examples**, then **Test draft chain**.
   With only the new phone mask enabled, `Fictional contact: +7 000 000-00-00.` becomes `Fictional contact: [PHONE].`.
   The text without a number and the incomplete `+7 000 000-00-0` pass through unchanged.
   Each case is editable and shows the input, output and any error for each step.
   Preview uses synthetic text and makes zero provider calls.
   An unsupported step stops the preview and identifies the remaining steps as unrun.
4. Choose **Save draft** to retain the chain across sessions.
   Review it and select **Activate saved chain**, then confirm to apply it to gateway traffic.

## Generate an editable policy or test cases

To enable these optional controls, run Ollama on the gateway's loopback interface at port 11434 and set `GATEWAY7_DRAFT_OLLAMA_MODEL` to an installed model that supports structured output before starting the gateway.
For a containerized gateway, the model server must share its network namespace.
Leave the variable unset to use the manual editor without a model.

Enter a short description containing synthetic data only.
The draft generator sends that description to the local model and validates its JSON against the four built-in policy templates.
The separate case generator sends only the template name and uses the model's choices to assemble editable positive, negative and boundary examples.
A literal policy uses the supplied synthetic term for its positive example.
Review generated values and run the draft chain before explicitly activating changes.
An unavailable model or invalid response leaves the editor and live configuration intact.

## Create a policy without code

Open **Policies**, enter a stable **Policy ID** and descriptive **Policy name**, choose a **Template**, and select incoming requests, outgoing responses or both under **Apply to**.
No Python, regular expression or module path is needed or accepted.

| Template | Result |
| --- | --- |
| **Block matching text** | Deny when any configured literal term matches in the selected phase |
| **Redact matching text** | Replace matching literal terms with the replacement text |
| **Mask email addresses** | Mask email-like text with `[EMAIL]` unless another replacement is configured |
| **Mask phone numbers** | Mask supported phone-number text with `[PHONE]` unless another replacement is configured |

Literal terms are case-sensitive text, not patterns; characters such as `.` or `*` have their literal meaning.
Enter one literal term per line under **Text to match**: 1–32 distinct nonblank terms of at most 128 characters each.
Masking templates use the existing detectors and do not accept a literal term list.
Replacement text is bounded to 128 characters; literal redaction defaults to `[REDACTED]`.
The directory supports up to 64 definitions, with stable ASCII policy IDs of at most 56 characters and labels of at most 64 characters.

1. Enter a synthetic example under **Sample text** and select **Test policy** before saving.
   Preview accepts at most 8192 characters of plain text and shows the match, replacement or denial without a provider call.
   Its text is not saved to state, audit history or logs.
2. Select **Create policy**, then choose **Every user (gateway baseline)** or **One user (after the baseline)** under **Apply policies to**.
   For one user, enter its exact **User ID**.
3. Add the policy to the selected order, review it with **Move up** and **Move down**, and select **Save assignments**.
   New requests use the saved policy without restarting the gateway.
4. Test an actual synthetic application request using the client's key.
   A request-phase guard denies a matching request before provider work; response-phase checks occur after provider work.

Managed global policies follow the configured global middleware, and managed client policies follow that client's configured additions.
Required configured policies remain in place; the editor cannot remove or replace that baseline.
A policy cannot be assigned globally and again to the same client, and duplicate assignments are rejected.
Unassign an in-use definition before deleting it.
Removing a managed assignment removes only that managed policy, not the configured baseline.

Preview checks plain text rather than conversation history, typed tools or a complete pipeline.
In real requests, matches in protected tool arguments, call IDs or other executable fields are denied instead of rewriting those fields.
The existing masking [detector limits](middleware-catalog.md) still apply.
A response or both-phase policy refuses incompatible early delivery before provider work; adding a request-only policy does not bypass another response policy in the chain.
Installing a different Python plugin or changing startup YAML middleware still follows the server deployment workflow.

## Pricing and budgets

Enter input and output prices in USD per million tokens for each canonical model.
Amounts accept up to six decimal places and are converted to exact integer microdollars.
Changing a price affects new attempts; existing attempts retain their recorded pricing revision.
Known estimated cost and attempts with unknown cost are reported separately.
These estimates do not replace the provider's invoice.

A budget rule can cover every user and model, one user, one model, or their intersection.
Rules use UTC calendar days or months and can limit combined input/output tokens, estimated USD cost, or both.
**Warn** rules report the limit condition without blocking work.
**Hard** rules reserve allowance before contacting the provider and reject requests that cannot fit the remaining allowance.
Concurrent attempts therefore cannot each spend the same remaining allowance.

Hard cost budgets require model pricing and sufficiently known usage.
Unknown accounting is not treated as free usage.
Provider-reported usage settles reservations; unknown usage remains explicit and retains conservative accounting where possible.
The status table shows used allowance, pending reservations, warnings and exhaustion.

## Reports, diagnostics and retention

Filter usage by user, model and UTC dates, and select hourly or daily time buckets.
Date controls include both selected calendar days; the API uses an explicit UTC interval with an exclusive end.
The report includes known input/output tokens, provider outcomes, unknown usage, estimated costs, pending attempts and a time series.
Historical daily aggregates remain visible with their lower precision identified rather than being fabricated into hourly events.
Export CSV to download the selected interval and filters.

Request diagnostics show safe request outcomes, policy denials, latency, activity and key last use without prompts or answers.
The monitoring stack continues to expose [metrics and Grafana dashboards](deployment.md) for gateway operations.

Retention is configurable between 32 and 3650 days.
The minimum preserves current monthly budget accounting.
After confirmation, cleanup removes settled usage and audit events older than the selected period; pending attempts are retained.
Back up durable state and keep the encryption key separately before destructive maintenance or a restore.
