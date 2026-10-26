"""Generate the numbered chat sequence with the Python standard library.

Run: python docs/architecture/sequence-chat.py [--check]
An absolute script path works from any working directory.
The adjacent container.py supplies the shared SVG style helpers.
Behavior follows gateway7/app.py, pipeline.py, providers.py and auth.py.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from container import BLUE, BLUE_PALE, EDGE, MUTED, rect, text

WIDTH = 1280
HEIGHT = 1740
CLIENT = 138
GATEWAY = 620
PROVIDER = 1106
AMBER = "#81570c"
AMBER_PALE = "#fff5d8"


def arrow(start: int, end: int, y: int, label: str, *, reply: bool = False) -> list[str]:
    dash = ' stroke-dasharray="8 5"' if reply else ""
    label_width = len(label) * 11 + 20
    return [
        f'<path d="M {start} {y} H {end}" fill="none" stroke="{EDGE}" '
        f'stroke-width="2.5"{dash} marker-end="url(#arrow)"/>',
        rect((start + end - label_width) // 2, y - 39, label_width, 29, fill="#ffffff", radius=3),
        text((start + end) // 2, y - 17, label, size=18, weight=700, anchor="middle"),
    ]


def checkpoint(y: int, title: str, detail: str, *, height: int = 88) -> list[str]:
    return [
        rect(357, y, 526, height, fill=BLUE_PALE, stroke="#a9c5eb", radius=8),
        text(GATEWAY, y + 33, title, size=22, fill=BLUE, weight=700, anchor="middle"),
        text(GATEWAY, y + 62, detail, size=16, fill=MUTED, anchor="middle"),
    ]


def note(x: int, y: int, width: int, title: str, lines: list[str]) -> list[str]:
    elements = [
        rect(x, y, width, 66 + 27 * len(lines), fill=AMBER_PALE, stroke="#e6bf62", radius=8),
        text(x + 18, y + 30, title, size=15, fill=AMBER, weight=700),
    ]
    elements.extend(
        text(x + 18, y + 62 + 27 * index, line, size=16, fill="#634c1d")
        for index, line in enumerate(lines)
    )
    return elements


def build_svg() -> str:
    elements = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" '
        f'viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-labelledby="title description">',
        '<title id="title">Gateway7 chat request sequence</title>',
        '<desc id="description">The client sends a chat request to gateway. Gateway checks '
        "authentication, model permission and process capacity, then runs request middleware. "
        "If adapter mapping succeeds it sends one HTTPS request to the configured external LLM. "
        "Gateway bounds and validates the response, snapshots usage and finish reason, runs "
        "response middleware in reverse order, and delivers a safe response. Alternatives show "
        "rejection before HTTP, failures with possible token consumption, and cancellation that "
        "holds capacity until the pipeline task finishes. Prometheus scrapes independently.</desc>",
        '<defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="9" refY="5" '
        'orient="auto" markerUnits="userSpaceOnUse">'
        f'<path d="M 0 0 L 10 5 L 0 10 Z" fill="{EDGE}"/></marker></defs>',
        '<g font-family="DejaVu Sans, Arial, sans-serif">',
        rect(0, 0, WIDTH, HEIGHT, fill="#ffffff", radius=0),
        rect(48, 48, 48, 5, fill=BLUE, radius=2),
        text(48, 99, "Gateway7 — chat request sequence", size=34, weight=700),
        text(
            48,
            136,
            "Read top to bottom · numbered success path; alternatives stop delivery",
            size=18,
            fill=MUTED,
        ),
        rect(332, 164, 576, 1250, fill="#fafcff", stroke="#93a6bd", radius=16, dash="9 7"),
    ]

    for x in (CLIENT, GATEWAY, PROVIDER):
        elements.append(
            f'<path d="M {x} 258 V 1408" stroke="#aebdce" stroke-width="2" stroke-dasharray="5 7"/>'
        )
    for x, width, name, detail, fill, stroke in (
        (48, 180, "Client", "Application / user", "#f1f3f6", "#677487"),
        (348, 544, "gateway", "Container · Python / FastAPI", BLUE_PALE, BLUE),
        (980, 252, "LLM provider", "External system · one selected", "#f1f3f6", "#677487"),
    ):
        center = x + width // 2
        elements.extend(
            [
                rect(x, 182, width, 76, fill=fill, stroke=stroke, radius=10),
                text(center, 214, name, size=25, weight=700, anchor="middle"),
                text(center, 240, detail, size=14, fill=MUTED, anchor="middle"),
            ]
        )

    elements.extend(arrow(CLIENT, GATEWAY, 298, "1. POST /chat or /v1/chat/completions"))
    elements.append(
        text(379, 325, "Bearer token + model + text messages", size=16, fill=MUTED, anchor="middle")
    )
    elements.extend(
        checkpoint(
            345, "2. Authenticate and pin model", "Validate payload; select an allowed model."
        )
    )
    elements.extend(
        checkpoint(460, "3. Admit one pipeline", "Default: 64 active slots per process; no queue.")
    )
    elements.extend(
        checkpoint(
            575, "4. Request middleware A → B → C", "Successful middleware awaits next once."
        )
    )
    elements.extend(
        checkpoint(
            690, "5. Adapter maps provider payload", "Continue to HTTP only if mapping succeeds."
        )
    )
    elements.extend(arrow(GATEWAY, PROVIDER, 825, "6. One HTTPS request"))
    elements.append(
        text(
            863,
            852,
            "Server key in header · no retry or redirect",
            size=16,
            fill=MUTED,
            anchor="middle",
        )
    )
    elements.extend(arrow(PROVIDER, GATEWAY, 910, "7. Provider response", reply=True))
    elements.extend(
        checkpoint(
            950, "8. Bound, decode, validate", "Parse valid usage before checking the answer."
        )
    )
    elements.extend(
        checkpoint(
            1055, "9. Snapshot usage + finish reason", "Gateway records provider metrics once."
        )
    )
    elements.extend(
        checkpoint(
            1160, "10. Response middleware C → B → A", "Mask, redact or deny before delivery."
        )
    )
    elements.extend(
        checkpoint(
            1265, "11. Pipeline task finishes", "Release its slot only when the task is done."
        )
    )
    elements.extend(
        arrow(GATEWAY, CLIENT, 1400, "12. HTTP 200 · filtered answer + usage", reply=True)
    )

    elements.extend(
        note(
            48,
            374,
            260,
            "ALT A · BEFORE HTTP",
            [
                "Invalid token → 401",
                "Model forbidden → 403",
                "Capacity full → 503",
                "Request policy deny → 403",
                "Return a safe error to client.",
                "No outbound HTTP call.",
            ],
        )
    )
    elements.extend(
        note(
            936,
            1000,
            296,
            "ALT B · NO ANSWER DELIVERED",
            [
                "Provider failure → 502",
                "Can be local at step 5,",
                "or during steps 6–8.",
                "Response policy deny → 403",
                "Middleware failure → 500",
                "After HTTP, tokens may",
                "already be consumed.",
                "Retain valid known usage;",
                "unknown stays unknown.",
                "Return a safe error + ID.",
            ],
        )
    )
    elements.extend(
        note(
            48,
            1442,
            1184,
            "ALT C · DEADLINE / CALLER CANCELLATION",
            [
                "Deadline expires → 504 if the caller is connected; a disconnected caller gets no delivered answer.",
                "Cancel owned work; keep the slot until the pipeline task actually finishes, including cooperative cleanup.",
            ],
        )
    )
    elements.extend(
        [
            text(
                48,
                1600,
                "Capacity is per process, not a client quota. A → B → C illustrates the configured middleware order.",
                size=16,
                fill=MUTED,
            ),
            text(
                48,
                1627,
                "Independent monitoring: prometheus scrapes gateway via HTTP GET /metrics; chat never waits for it.",
                size=16,
                fill=MUTED,
            ),
            text(
                48,
                1654,
                "Demo mode replaces the external LLM with a private loopback child process inside the gateway container.",
                size=16,
                fill=MUTED,
            ),
            rect(48, 1685, 20, 16, fill=BLUE_PALE, stroke=BLUE, radius=3),
            text(80, 1698, "Gateway checkpoint", size=14, fill=MUTED),
            rect(278, 1685, 20, 16, fill=AMBER_PALE, stroke="#e6bf62", radius=3),
            text(310, 1698, "Alternative / safe exit", size=14, fill=MUTED),
            f'<path d="M 520 1693 H 566" stroke="{EDGE}" stroke-width="2" marker-end="url(#arrow)"/>',
            text(580, 1698, "Request", size=14, fill=MUTED),
            f'<path d="M 680 1693 H 726" stroke="{EDGE}" stroke-width="2" stroke-dasharray="6 4" marker-end="url(#arrow)"/>',
            text(740, 1698, "Response", size=14, fill=MUTED),
            text(870, 1698, "Vertical dotted line: time / participant", size=14, fill=MUTED),
            "</g></svg>",
        ]
    )
    return "\n".join(elements) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail when the SVG is stale")
    args = parser.parse_args()
    target = Path(__file__).with_suffix(".svg")
    content = build_svg()
    if args.check:
        if not target.is_file() or target.read_text(encoding="utf-8") != content:
            print("Chat sequence SVG is stale; regenerate it with sequence-chat.py")
            return 1
        print("Chat sequence SVG matches its source")
    else:
        target.write_text(content, encoding="utf-8", newline="\n")
        print(f"Generated {target.name}: {WIDTH} × {HEIGHT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
