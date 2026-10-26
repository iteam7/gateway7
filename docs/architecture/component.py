"""Generate the C4 component view using only the Python standard library.

Run this file from any directory; --check verifies the adjacent committed SVG.
The view groups responsibilities in gateway7/, not deployment containers.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from container import BLUE, BLUE_PALE, MUTED, rect, text

WIDTH = 1440
HEIGHT = 1370
STARTUP = "#75529a"
OBSERVE = "#16736b"
OFFLINE = "#966619"


def edge(path: str, kind: str = "request") -> str:
    color, dash = {
        "request": (BLUE, ""),
        "startup": (STARTUP, ' stroke-dasharray="9 6"'),
        "observation": (OBSERVE, ' stroke-dasharray="2 6"'),
        "offline": (OFFLINE, ' stroke-dasharray="12 5 2 5"'),
    }[kind]
    return (
        f'<path d="{path}" fill="none" stroke="{color}" stroke-width="2.5"'
        f'{dash} marker-end="url(#{kind})"/>'
    )


def component(
    x: int,
    y: int,
    width: int,
    height: int,
    title: str,
    code: str,
    lines: list[str],
    *,
    offline: bool = False,
    title_size: int = 23,
) -> list[str]:
    color = OFFLINE if offline else BLUE
    fill = "#fff7e7" if offline else BLUE_PALE
    titles = title.split("\n")
    extra = 28 * (len(titles) - 1)
    result = [rect(x, y, width, height, fill=fill, stroke=color)]
    for index, value in enumerate(titles):
        result.append(
            text(x + 20, y + 36 + index * 28, value, size=title_size, fill=color, weight=700)
        )
    result.extend(
        [
            text(x + 20, y + 62 + extra, code, size=13, fill=MUTED),
            f'<path d="M {x + 20} {y + 78 + extra} H {x + width - 20}" stroke="#c7d9f1"/>',
        ]
    )
    for index, value in enumerate(lines):
        result.append(text(x + 20, y + 104 + extra + index * 24, value, size=15))
    return result


def build_svg() -> str:
    elements = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" '
        f'viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-labelledby="title description">',
        '<title id="title">Gateway7 C4 component view</title>',
        '<desc id="description">One gateway application is expanded into startup and configuration, '
        "HTTP boundary and access, middleware pipeline, provider adapter, metrics and diagnostics, "
        "and plugin authoring and offline tests. HTTP chat enters the middleware pipeline and "
        "calls one configured external LLM provider. Startup configures these components. "
        "HTTP and pipeline work produce safe observations. Offline CLI tests reuse the pipeline "
        "in a separate worker with fixture replies, without the HTTP provider adapter. "
        "Components group Python responsibilities, not independently deployed services.</desc>",
        "<defs>",
    ]
    for name, color in (
        ("request", BLUE),
        ("startup", STARTUP),
        ("observation", OBSERVE),
        ("offline", OFFLINE),
    ):
        elements.append(
            f'<marker id="{name}" markerWidth="10" markerHeight="10" refX="9" refY="5" '
            'orient="auto" markerUnits="userSpaceOnUse">'
            f'<path d="M 0 0 L 10 5 L 0 10 Z" fill="{color}"/></marker>'
        )
    elements.extend(
        [
            '</defs><g font-family="DejaVu Sans, Arial, sans-serif">',
            rect(0, 0, WIDTH, HEIGHT, fill="#ffffff", radius=0),
            rect(48, 48, 48, 5, fill=BLUE, radius=2),
            text(48, 99, "Gateway7 — component view", size=36, weight=700),
            text(
                48,
                136,
                "C4 • Inside the gateway application; one request path, shared support code",
                size=19,
                fill=MUTED,
            ),
            rect(48, 200, 1020, 1000, fill="#fafcff", stroke="#93a6bd", radius=18, dash="9 7"),
            text(80, 242, "gateway", size=27, weight=700),
            text(
                80, 270, "Application container · Python / FastAPI / Uvicorn", size=16, fill=MUTED
            ),
            text(
                810,
                181,
                "HTTP caller · native client / OpenAI SDK",
                size=17,
                anchor="middle",
                weight=700,
            ),
            edge("M 810 204 V 325"),
            text(832, 245, "JSON + bearer token", size=14, fill=BLUE),
            text(832, 267, "answer / safe error", size=14, fill=BLUE),
            edge("M 810 560 V 650"),
            text(830, 585, "Pipeline.run(...)", size=14, fill=BLUE),
            text(830, 607, "request + pinned model", size=14, fill=BLUE),
            text(830, 629, "ChatResponse / error", size=14, fill=BLUE),
            edge("M 810 860 V 950"),
            text(830, 895, "complete(..., model=...)", size=14, fill=BLUE),
            text(830, 917, "text / usage / finish", size=14, fill=BLUE),
            edge("M 1020 1040 H 1175"),
            text(1115, 1001, "HTTPS · live", size=14, fill=BLUE, anchor="middle"),
            text(1115, 1023, "text / usage", size=14, fill=BLUE, anchor="middle"),
            edge("M 430 435 H 500 V 1020 H 600", "startup"),
            edge("M 500 435 H 600", "startup"),
            edge("M 500 730 H 600", "startup"),
            text(515, 412, "access / limits", size=12, fill=STARTUP),
            text(510, 712, "loaded plugins", size=12, fill=STARTUP),
            text(510, 1048, "session / key", size=12, fill=STARTUP),
            edge("M 600 510 H 555 V 600 H 255 V 650", "observation"),
            text(273, 582, "HTTP counts / timings", size=14, fill=OBSERVE),
            edge("M 600 800 H 430", "observation"),
            text(548, 779, "timing / usage", size=12, fill=OBSERVE, anchor="middle"),
            edge("M 430 1000 H 560 V 835 H 600", "offline"),
            text(480, 890, "Fixture run()", size=13, fill=OFFLINE, anchor="end"),
            text(480, 912, "same pipeline code", size=13, fill=OFFLINE, anchor="end"),
        ]
    )
    elements.extend(
        component(
            80,
            325,
            350,
            215,
            "Startup and configuration",
            "cli.py · config.py · loader.py · app lifespan",
            [
                "CLI: gateway7 serve / demo / validate",
                "Validates YAML; resolves server secrets.",
                "Creates access, plugins and adapter.",
                "Owns startup and reverse cleanup.",
            ],
            title_size=21,
        )
    )
    elements.extend(
        component(
            600,
            325,
            420,
            235,
            "HTTP boundary and access",
            "app.py · openai_api.py · auth.py",
            [
                "POST /chat · /v1/chat/completions",
                "GET /v1/models",
                "GET /health · /ready · /metrics",
                "Token / model checks; bounded request bodies.",
                "Only admitted chat enters the pipeline.",
            ],
        )
    )
    elements.extend(
        component(
            600,
            650,
            420,
            210,
            "Middleware pipeline",
            "pipeline.py · plugin_api.py · models.py · plugins/",
            [
                "handle(request, context, call_next)",
                "Request order → provider → reverse return.",
                "Deadlines; at most one provider invocation.",
                "Trusted built-ins and installed plugins.",
            ],
        )
    )
    elements.extend(
        component(
            600,
            950,
            420,
            185,
            "Provider adapter",
            "providers.py · httpx AsyncClient",
            [
                "Maps messages to one provider's HTTP API.",
                "Keeps server credentials in request headers.",
                "Normalizes text, usage, finish and failures.",
            ],
        )
    )
    elements.extend(
        component(
            80,
            650,
            350,
            210,
            "Metrics and diagnostics",
            "metrics.py · errors.py · app / pipeline logs",
            [
                "Owns the application's metric registry.",
                "Provides samples for GET /metrics.",
                "Safe error codes and correlated events.",
                "No prompt or credential in core logs.",
            ],
        )
    )
    elements.extend(
        component(
            80,
            925,
            350,
            210,
            "Plugin authoring\nand offline tests",
            "scaffold.py · offline.py · _offline_worker.py",
            [
                "CLI: gateway7 plugin init / test",
                "Separate test worker; synthetic replies.",
                "Reuses loader, lifecycle and pipeline.",
            ],
            offline=True,
        )
    )
    elements.extend(
        [
            rect(1175, 950, 217, 185, fill="#f1f3f6", stroke="#677487"),
            text(1193, 985, "LLM provider", size=23, weight=700),
            text(1193, 1009, "External software system", size=13, fill=MUTED),
            text(1193, 1041, "OpenAI /", size=15),
            text(1193, 1064, "Anthropic Claude /", size=15),
            text(1193, 1087, "Google Gemini", size=15),
            text(1193, 1117, "One configured provider", size=13, fill=MUTED),
            text(
                80,
                1167,
                "Amber is CLI-only work, not a service in the HTTP path; its worker uses fixture replies, not HTTPProvider.",
                size=14,
                fill=MUTED,
            ),
            rect(48, 1236, 20, 16, fill=BLUE_PALE, stroke=BLUE, radius=4),
            text(80, 1250, "Python component", size=14, fill=MUTED),
            rect(280, 1236, 20, 16, fill="#fff7e7", stroke=OFFLINE, radius=4),
            text(312, 1250, "CLI activity / worker", size=14, fill=MUTED),
            rect(550, 1236, 20, 16, fill="#f1f3f6", stroke="#677487", radius=4),
            text(582, 1250, "External system", size=14, fill=MUTED),
            rect(795, 1236, 20, 16, fill="#fafcff", stroke="#93a6bd", radius=4, dash="4 3"),
            text(827, 1250, "Expanded gateway boundary", size=14, fill=MUTED),
            edge("M 48 1293 H 95"),
            text(109, 1298, "Request / response contract", size=14, fill=MUTED),
            edge("M 375 1293 H 422", "startup"),
            text(436, 1298, "Startup configuration", size=14, fill=MUTED),
            edge("M 670 1293 H 717", "observation"),
            text(731, 1298, "Observations", size=14, fill=MUTED),
            edge("M 935 1293 H 982", "offline"),
            text(996, 1298, "Offline code reuse", size=14, fill=MUTED),
            text(
                48,
                1343,
                "Arrows point from caller to dependency; replies return on the same path. Components are not deployment containers.",
                size=14,
                fill=MUTED,
            ),
            "</g></svg>",
        ]
    )
    return "\n".join(elements) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail when the committed SVG is stale")
    args = parser.parse_args()
    target = Path(__file__).with_suffix(".svg")
    content = build_svg()
    if args.check:
        if not target.is_file() or target.read_text(encoding="utf-8") != content:
            print("Component SVG is stale; regenerate it with component.py")
            return 1
        print("Component SVG matches its source")
    else:
        target.write_text(content, encoding="utf-8", newline="\n")
        print(f"Generated {target.name}: {WIDTH} × {HEIGHT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
