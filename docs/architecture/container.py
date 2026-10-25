"""Regenerate the C4 container view with only the Python standard library.

Run from the repository root: python docs/architecture/container.py
An absolute script path also works from any other directory.
Use --check to verify that the committed SVG matches this source.
The topology follows compose.yaml, compose.live.yaml and monitoring/*.yml.
"""

from __future__ import annotations

import argparse
from html import escape
from pathlib import Path

WIDTH = 1600
HEIGHT = 1060
INK = "#14253d"
MUTED = "#52657c"
BLUE = "#215baf"
BLUE_PALE = "#eff6ff"
EDGE = "#52657c"


def text(
    x: int,
    y: int,
    value: str,
    *,
    size: int = 16,
    fill: str = INK,
    weight: int = 400,
    anchor: str = "start",
) -> str:
    return (
        f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill}" '
        f'font-weight="{weight}" text-anchor="{anchor}">{escape(value)}</text>'
    )


def rect(
    x: int,
    y: int,
    width: int,
    height: int,
    *,
    fill: str,
    stroke: str = "none",
    radius: int = 12,
    dash: str | None = None,
) -> str:
    dashed = f' stroke-dasharray="{dash}"' if dash else ""
    return (
        f'<rect x="{x}" y="{y}" width="{width}" height="{height}" '
        f'rx="{radius}" fill="{fill}" stroke="{stroke}" stroke-width="2"{dashed}/>'
    )


def container(x: int, y: int, width: int, height: int, name: str, technology: str) -> list[str]:
    return [
        rect(x, y, width, height, fill=BLUE_PALE, stroke=BLUE),
        text(x + 24, y + 40, name, size=27, fill=BLUE, weight=700),
        text(x + 24, y + 66, technology, size=15, fill=MUTED),
        f'<path d="M {x + 24} {y + 86} H {x + width - 24}" stroke="#c7d9f1"/>',
    ]


def build_svg() -> str:
    elements = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" '
        f'viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-labelledby="title description">',
        '<title id="title">Gateway7 C4 container view</title>',
        '<desc id="description">The Gateway7 system contains gateway, prometheus and grafana. '
        'The gateway calls one configured external LLM provider over HTTPS in live mode. '
        'Prometheus scrapes gateway metrics over HTTP. Grafana queries Prometheus over HTTP using PromQL. '
        'In demo mode a synthetic upstream child process runs inside the gateway Docker container '
        'over loopback HTTP, instead of calling the external provider. Arrows point from initiator to dependency.</desc>',
        '<defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="9" refY="5" '
        'orient="auto" markerUnits="userSpaceOnUse">'
        f'<path d="M 0 0 L 10 5 L 0 10 Z" fill="{EDGE}"/></marker></defs>',
        '<g font-family="DejaVu Sans, Arial, sans-serif">',
        rect(0, 0, WIDTH, HEIGHT, fill="#ffffff", radius=0),
        rect(48, 48, 48, 5, fill=BLUE, radius=2),
        text(48, 99, "Gateway7 — container view", size=36, weight=700),
        text(48, 136, "C4 • Running applications and their operational dependencies", size=19, fill=MUTED),
        rect(48, 184, 1120, 768, fill="#fafcff", stroke="#93a6bd", radius=18, dash="9 7"),
        text(78, 224, "Gateway7", size=25, weight=700),
        text(78, 252, "System boundary · Compose deployment", size=16, fill=MUTED),
    ]

    elements.extend(container(96, 286, 520, 314, "gateway", "Container · Python / FastAPI / Uvicorn"))
    elements.extend(
        [
            text(120, 400, "Authenticates callers; checks model permissions."),
            text(120, 424, "Runs request and response middleware."),
            text(120, 448, "Uses one configured LLM provider."),
            rect(120, 472, 472, 104, fill="#fff5d8", stroke="#e6bf62", radius=6),
            text(136, 493, "DEMO ONLY", size=12, fill="#81570c", weight=700),
            text(136, 515, "Private synthetic upstream child process", size=14, fill="#634c1d"),
            text(136, 536, "inside this Docker container · loopback HTTP.", size=14, fill="#634c1d"),
            text(136, 557, "No external provider call in demo mode.", size=14, fill="#634c1d"),
        ]
    )

    elements.extend(container(96, 732, 520, 184, "prometheus", "Container · Prometheus + local TSDB"))
    elements.extend(
        [
            text(120, 850, "Scrapes and stores gateway metric samples."),
            text(120, 880, "Time-series volume: prometheus-data", size=15, fill=MUTED),
        ]
    )
    elements.extend(container(700, 732, 420, 184, "grafana", "Container · Grafana"))
    elements.extend(
        [
            text(724, 850, "Queries metrics for provisioned dashboards."),
            text(724, 880, "State volume: grafana-data", size=15, fill=MUTED),
        ]
    )

    elements.extend(
        [
            rect(1258, 320, 294, 222, fill="#f1f3f6", stroke="#677487"),
            text(1282, 360, "LLM provider", size=25, weight=700),
            text(1282, 387, "External software system", size=14, fill=MUTED),
            '<path d="M 1282 407 H 1528" stroke="#c9d0da"/>',
            text(1282, 437, "OpenAI / Anthropic Claude /", size=15),
            text(1282, 462, "Google Gemini", size=15),
            text(1282, 505, "One selected provider at runtime", size=14, fill=MUTED),
            f'<path d="M 616 400 H 1258" fill="none" stroke="{EDGE}" '
            'stroke-width="2.5" marker-end="url(#arrow)"/>',
            text(936, 351, "HTTPS · live mode", size=17, weight=700, anchor="middle"),
            text(936, 376, "text messages / answer + usage", size=16, fill=MUTED, anchor="middle"),
            f'<path d="M 356 732 V 600" fill="none" stroke="{EDGE}" '
            'stroke-width="2.5" marker-end="url(#arrow)"/>',
            text(96, 651, "HTTP GET /metrics", size=17, weight=700),
            text(96, 677, "Prometheus samples", size=16, fill=MUTED),
            f'<path d="M 910 732 V 684 H 500 V 732" fill="none" stroke="{EDGE}" '
            'stroke-width="2.5" marker-end="url(#arrow)"/>',
            text(705, 638, "HTTP · PromQL", size=17, weight=700, anchor="middle"),
            text(705, 664, "queries / metric results", size=16, fill=MUTED, anchor="middle"),
        ]
    )

    elements.extend(
        [
            rect(48, 990, 22, 17, fill=BLUE_PALE, stroke=BLUE, radius=4),
            text(82, 1004, "Application container", size=14, fill=MUTED),
            rect(348, 990, 22, 17, fill="#f1f3f6", stroke="#677487", radius=4),
            text(382, 1004, "External system", size=14, fill=MUTED),
            rect(614, 990, 22, 17, fill="#fafcff", stroke="#93a6bd", radius=4, dash="4 3"),
            text(648, 1004, "System boundary", size=14, fill=MUTED),
            rect(898, 990, 22, 17, fill="#fff5d8", stroke="#e6bf62", radius=3),
            text(932, 1004, "Demo-only note", size=14, fill=MUTED),
            f'<path d="M 1200 998 H 1240" stroke="{EDGE}" stroke-width="2" marker-end="url(#arrow)"/>',
            text(1254, 1004, "Initiator → dependency", size=14, fill=MUTED),
            text(48, 1042, "Arrows name the protocol and exchanged data; response data returns along the same connection.", size=14, fill=MUTED),
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
            print("Container SVG is stale; regenerate it with container.py")
            return 1
        print("Container SVG matches its source")
    else:
        target.write_text(content, encoding="utf-8", newline="\n")
        print(f"Generated {target.name}: {WIDTH} × {HEIGHT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
