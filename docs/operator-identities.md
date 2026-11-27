# Operator identities and client keys

The managed console separates application access from administrative access.
Create a client for each developer or service, then issue named keys for its applications.
Create named operators for people who manage or inspect the gateway.
Configure the persistent backend as described in [authentication](authentication.md#manage-users-in-the-operator-console).

## Client profiles

A profile contains a stable client ID, enabled state, model allowlist, optional default model, concurrent-request limit and request-rate limit.
Its ordered additional middleware follows the shared baseline.
The owner label and tags help identify service accounts and teams without putting personal information in telemetry.
Use pseudonymous labels where possible: profiles and their changes appear in the protected audit history.

Search the directory by client ID, owner or tag, filter its status and page through matching accounts.
The server supports up to 128 current clients and pages of up to 100 accounts.
Deleting a client preserves its history and reserves its ID against reuse.

An explicit client default must use a canonical model ID permitted by both the profile and the gateway.
Aliases are resolved before the canonical access check.
If a later gateway restriction excludes a previously selected default, the profile reports `default_denied`; choose another permitted default.
An omitted client default uses the gateway default and does not choose another model automatically after a denial.

## Named application keys

Use separate keys for an IDE, CI job and deployed service when they need independent revocation.
Issuing another named key retains the existing keys.
Rotating a selected key immediately invalidates that key and returns its replacement once.
Revoking a selected key leaves the other application keys active.
The compatibility account-level token actions replace or revoke every key for that account.

New keys expire after 90 days unless an explicit timezone-aware expiry is supplied.
The expiry must be in the future and within 365 days.
Imported configuration-only credentials retain their existing non-expiring behavior and are labelled `legacy`; replace them with expiring keys when practical.
Each account can have up to 16 currently active keys.

Save a returned token in the application's secret store immediately.
Neither later API reads nor the database can recover its raw value.
The console shows the key's label, creation time, expiry, revocation state and last authenticated use, while the database retains its digest.
Last-use updates do not change the management revision.
An expired key is rejected on every protected client API, including model discovery and streaming requests.

Suspension disables all keys for the client.
Re-enabling a client does not restore revoked keys.
Requests already admitted continue under their original policy; revocation prevents subsequent requests rather than retracting a response already in progress.

## Named operators and recovery

Use named password accounts for people and separately generated bearer credentials for automation when needed.
The operator ID is the login username; the display label does not change it.
The `admin` role can change profiles, keys, operators and operational configuration.
The `viewer` role can inspect protected state, usage, key metadata and audit history, but cannot perform mutations, preview policies or run provider connection tests.
An administrator provisions accounts; there is no public registration endpoint.
The [first-sign-in walkthrough](admin-controls.md#first-sign-in) shows how the recovery administrator creates the first password account.

A password contains 12–128 characters and at most 512 UTF-8 bytes.
The server stores a salted password hash and never returns the password in account metadata or audit output.
Use **Reset password** to set a replacement; all existing sessions for that operator become invalid.
Changing your own password therefore requires a fresh sign-in on subsequent requests.
Passwords and client application keys are independent credentials.

Optional named automation credentials are generated and shown only when created or rotated.
Rotation preserves the operator ID and role, replaces the bearer credential and sets its expiry.
Reissuing a revoked automation credential restores that named identity without assigning its earlier secret again.
Rotating an automation bearer does not end independently authenticated password sessions.
Role changes and revocations invalidate those sessions and apply to subsequent requests, including a mutation whose request body was still arriving when access changed.

The reserved `bootstrap` administrator uses the separately configured environment credential.
It remains available for recovery when named operators expire or lose administrative access and does not support password login.
The console cannot revoke or edit it; change that server-managed secret through the deployment's secret mechanism.
Keep this recovery credential separate from ordinary passwords, operator automation credentials and provider or client keys.
A token-mode connection retains its bearer credential only in page memory and clears it on disconnect.

## Password sign-in and lasting sessions

The server issues an opaque session cookie after a valid username/password sign-in.
The cookie is HttpOnly, SameSite=Strict, scoped to `/operator` and Secure by default; normal application APIs still use client keys.
Page scripts receive a separate session CSRF token for administrative writes, not the cookie's raw credential.
The console adds the write marker, CSRF proof and current configuration revision automatically.

An ordinary sign-in expires after the configured absolute 12-hour default and has no persistent-cookie Max-Age.
Selecting **Remember me on this device** opts into a persistent cookie and an absolute server lifetime of seven days by default.
Both settings are bounded to seven days and capped by the operator's own expiration.
New named password accounts retain the existing 90-day default operator expiration; account renewal and browser-session renewal are separate actions.
Refreshing a page or restarting the gateway does not revoke a valid durable session.
There is no automatic lifetime extension on each request.
At most 16 active sessions per operator and 1024 overall are retained; a further login can evict an oldest session.

Signing out revokes the current session and clears its cookie.
Password reset, role change or operator revocation invalidates every session for that operator; current roles are checked again when requests authenticate and before administrative commits.
A restored logical backup requires fresh password sign-in because it excludes browser sessions, although it retains operator password hashes.
For HTTPS and explicit loopback development settings, see [session deployment](authentication.md#password-sessions-and-https).

## Concurrent changes and audit history

Every managed mutation carries the current global revision in its `If-Match` header.
The revision is returned by state and directory reads.
Any successful account, key, operator or operational-policy change advances it.
If another operator changes state first, the stale request receives HTTP 409 without changing access.
Refresh and review the current profile before resubmitting; an old editor cannot silently restore permissions that another operator removed.

Successful mutations append an audit event in the same database transaction as the saved change.
Events identify the named actor, action, target, revision, request ID and safe changed fields.
Filter the protected history by actor, action, target or UTC interval to investigate access changes.
Raw credentials, credential digests, provider ciphertext and conversation content do not appear in audit projections.

## Offline backup and recovery

Stop the gateway before opening the store with the installed maintenance commands:

```sh
gateway7 backup --config config/admin-postgres.yaml --output /private/gateway7-backup.json
gateway7 restore --config /private/empty-target.yaml --input /private/gateway7-backup.json
```

The output is a new private file with a version and checksum; an existing output is never overwritten.
Restore accepts only an empty offline database of the same backend.
It preserves profiles, keys, operator password hashes, managed policy definitions and assignments, audit history, accounting events, outstanding budget reservations and encrypted provider configuration.
Browser sessions are excluded, so operators sign in again after restoration.
YAML seed clients do not replace the restored registry.

The backup contains private credential digests and encrypted provider material, so keep it outside the repository with restricted access.
Keep `GATEWAY7_CONTROL_KEY` separately through the deployment's secret-recovery mechanism: the tool never includes environment secrets in the backup.
Restore that key before starting a gateway whose saved provider credential requires decryption.
