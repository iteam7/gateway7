# Functional requirements

Each requirement states one behavior of Gateway7, the containers it runs in and its own acceptance criteria; the records are under [`fr/`](fr/FR-001.md).

| FR | Title | Containers | Status |
| --- | --- | --- | --- |
| [FR-001](fr/FR-001.md) | Answer With The Server-Held Provider Key | `gateway` | Active |
| [FR-002](fr/FR-002.md) | Mask Phone Numbers Throughout The Conversation | `gateway` | Active |
| [FR-003](fr/FR-003.md) | Run Company Middleware From Configuration | `gateway` | Active |
| [FR-004](fr/FR-004.md) | Block Or Log A Flagged Request | `gateway` | Active |
| [FR-005](fr/FR-005.md) | Check The Answer Before Delivery | `gateway` | Active |
| [FR-006](fr/FR-006.md) | Restrict Each Client To Its Allowed Models | `gateway` | Active |
| [FR-007](fr/FR-007.md) | Check A Middleware Against Synthetic Fixtures Offline | `gateway` | Active |
| [FR-008](fr/FR-008.md) | Generate A Middleware Starter Package | `gateway` | Active |
| [FR-009](fr/FR-009.md) | Expose Request And Middleware Metrics | `gateway` | Active |
| [FR-010](fr/FR-010.md) | Show Gateway Operations On The Overview Dashboard | `prometheus`, `grafana` | Active |
| [FR-011](fr/FR-011.md) | Name The Middleware That Failed Or Slowed A Request | `gateway` | Active |
