# Quality requirements

The priority matrix lists every quality requirement once, sorted by status, then business importance, then technical risk.
Each file under [`qr/`](qr/QR-01.md) carries the requirement's outcome, its ISO/IEC 25010:2023 pair and its six-part scenario.

| QR | Outcome | Business importance | Technical risk | Characteristic | Sub-characteristic | Status |
| --- | --- | --- | --- | --- | --- | --- |
| [QR-01](qr/QR-01.md) | When a request-side middleware raises, denies or overruns its time budget, the provider receives no call for that request on any supported operating system. | High | High | Reliability | Fault Tolerance | Active |
| [QR-02](qr/QR-02.md) | A developer runs the checks covering the gateway's critical modules from a clean checkout without any provider account, and a change that breaks their contract fails those checks. | High | Medium | Maintainability | Testability | Active |
| [QR-03](qr/QR-03.md) | No provider key, client token or message text appears in the gateway's logs, metrics or error responses. | High | Medium | Security | Confidentiality | Active |
| [QR-04](qr/QR-04.md) | An application using the official OpenAI Python SDK completes a non-streaming chat request through the gateway by changing only its base URL and API key. | Medium | Low | Compatibility | Interoperability | Active |

The course rule's examples for the mandated testability requirement name a frontend entry point and a payment module.
Gateway7 is a server-side gateway with neither, so [QR-02](qr/QR-02.md) names the gateway's own critical modules by repository path instead.

The tests and their results are in [the testing plan](../project-plan.md#quality-requirement-testing-plan).
