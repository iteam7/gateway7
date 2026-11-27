# User acceptance tests

A user acceptance test checks whether the deployed product supports one end-to-end user journey the Customer expects to complete.
The record is public; the test account, the deployed address and its credential are in the private Moodle submission.
Exactly three tests are defined before the Sprint 9 review, and a run is added only after the Customer or the team ran it on a deployed build.

## The Tests

| Test              | Journey                                                                                  | Status | SPRINT-09   | SPRINT-10   |
| ----------------- | ---------------------------------------------------------------------------------------- | ------ | ----------- | ----------- |
| [UAT-01](#uat-01) | A developer sends one request and sees the team's masking and redaction applied          | Active | Not yet run | Not yet run |
| [UAT-02](#uat-02) | A request carrying a blocked term is stopped before the provider answers                 | Active | Not yet run | Not yet run |
| [UAT-03](#uat-03) | A client is refused a model it may not call and answered with a model it may use         | Active | Not yet run | Not yet run |

## UAT-01

A developer sends one request through the deployed gateway and receives an answer with the team's masking and redaction applied.

**Status:** Active

**Start state:** The test client `developer` holds its gateway token and may call `claude-haiku-5-5`.
The message uses only synthetic values; the deployed address and the token are in the private submission.

**Steps:**

1. Send `POST <production-url>/chat` with `Authorization: Bearer <test-client-token>` and `Content-Type: application/json`.
2. Use the body `{"messages":[{"role":"user","content":"Repeat this message exactly: Contact synthetic@example.com or +7 999 123-45-67; SECRET-TEST"}]}`.
3. Read `text` in the answer and the returned `request_id`.

**Expected result:** The gateway answers with HTTP 200.
The repeated message shows `[EMAIL]` and `[PHONE]` in place of the synthetic address and number and `[removed]` in place of `SECRET-TEST`; the original values are absent.
The answer carries a `request_id`.

| Sprint | Date | Runner | Build | Result | Evidence | DEC-nnn |
| ------ | ---- | ------ | ----- | ------ | -------- | ------- |

No run is recorded yet; the Sprint 9 review fills this table.

## UAT-02

A request that carries a blocked term is stopped before the provider answers.

**Status:** Active

**Start state:** The test client `developer` may call `claude-haiku-5-5`.
The deployed configuration blocks `BLOCK-ME-TEST` on the request phase.

**Steps:**

1. Send `POST <production-url>/chat` with the same headers as UAT-01.
2. Use the body `{"messages":[{"role":"user","content":"BLOCK-ME-TEST"}]}`.
3. Read the HTTP status and `error.code` in the body.

**Expected result:** The response is HTTP 403 with `error.code` equal to `policy_denied`, and the body carries no model answer.

| Sprint | Date | Runner | Build | Result | Evidence | DEC-nnn |
| ------ | ---- | ------ | ----- | ------ | -------- | ------- |

No run is recorded yet; the Sprint 9 review fills this table.

## UAT-03

A client is refused a model it may not call and is answered when it asks for one it may use.

**Status:** Active

**Start state:** The test client `developer` is allowed `claude-haiku-5-5` only.
No other model ID is in its permission list.

**Steps:**

1. Send `POST <production-url>/v1/chat/completions` with `Authorization: Bearer <test-client-token>` and `Content-Type: application/json`.
2. Use the body `{"model":"claude-sonnet-4-5","messages":[{"role":"user","content":"Hello"}]}`.
3. Read the HTTP status and `error.code`.
4. Repeat the request with `"model":"claude-haiku-5-5"` and read `choices[0].message.content`.

**Expected result:** The first request returns HTTP 403 with `error.code` equal to `model_forbidden` and no answer.
The second returns HTTP 200 with the allowed model's answer.

| Sprint | Date | Runner | Build | Result | Evidence | DEC-nnn |
| ------ | ---- | ------ | ----- | ------ | -------- | ------- |

No run is recorded yet; the Sprint 9 review fills this table.
