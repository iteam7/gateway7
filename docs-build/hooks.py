"""Publish local diagram assets and keep weekly evidence out of site links."""

import re
import shutil
from html import unescape
from pathlib import Path
from urllib.parse import unquote, urlsplit

from mkdocs.exceptions import PluginError

SUPPORT = Path(__file__).resolve().parent
# MkDocs emits quoted hrefs and no nested anchors. Keep the inline label markup.
LINK = re.compile(r'<a\b[^>]*\bhref="([^"]*)"[^>]*>(.*?)</a>', re.DOTALL)


def on_page_markdown(markdown, *, config, **kwargs):
    """Match GitHub links for our headings, including repeated hyphens/titles."""
    used = set()

    def slugify(value, separator):
        # A removed slash between two spaces must leave two hyphens (ALT-03).
        base = re.sub(r"[^\w\- ]", "", value.lower()).replace(" ", separator)
        slug = base
        suffix = 0
        while slug in used:
            suffix += 1
            slug = f"{base}-{suffix}"
        used.add(slug)
        return slug

    config.mdx_configs["toc"]["slugify"] = slugify
    return markdown


def on_page_content(html, **kwargs):
    """Keep citation text while the repository retains its evidence hyperlinks."""
    def citation(match):
        path = unquote(urlsplit(unescape(match[1])).path)
        if "reports" in path.split("/"):
            return f'<span class="report-citation">{match[2]}</span>'
        return match[0]

    return LINK.sub(citation, html)


def on_post_build(config, **kwargs):
    """Copy only the locked browser bundle, never node_modules or report files."""
    mermaid = SUPPORT / "node_modules/mermaid"
    if not (mermaid / "dist/mermaid.min.js").is_file():
        raise PluginError("Install diagram assets first: npm ci --prefix docs-build --ignore-scripts")
    assets = Path(config.site_dir) / "assets"
    assets.mkdir(exist_ok=True)
    for source, name in (
        (mermaid / "dist/mermaid.min.js", "mermaid.min.js"),
        (mermaid / "LICENSE", "mermaid-LICENSE"),
        (SUPPORT / "mermaid-init.js", "mermaid-init.js"),
        (SUPPORT / "diagrams.css", "diagrams.css"),
    ):
        shutil.copyfile(source, assets / name)
