"""Check the generated site without network access: links, anchors and assets."""

import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = yaml.safe_load((ROOT / "mkdocs.yml").read_text())
SITE = ROOT / CONFIG["site_dir"]
DOCS = ROOT / CONFIG["docs_dir"]
BASE = CONFIG["site_url"]
BASE_URL = urlsplit(BASE)


class Page(HTMLParser):
    def __init__(self, content):
        super().__init__()
        self.ids = set()
        self.links = []
        self.feed(content)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.add(attrs["id"])
        for attribute in ("href", "src"):
            if attrs.get(attribute):
                asset = attribute == "src" or (
                    tag == "link" and attrs.get("rel") in {"stylesheet", "icon"}
                )
                self.links.append((attrs[attribute], asset))


def main():
    errors = []
    pages = {
        path.relative_to(SITE).as_posix(): Page(path.read_text())
        for path in SITE.rglob("*.html")
    }
    sources = list(DOCS.rglob("*.md"))
    for source in sources:
        relative = source.relative_to(DOCS)
        output = (
            relative.parent / "index.html"
            if relative.name in {"README.md", "index.md"}
            else relative.with_suffix("") / "index.html"
        )
        if output.as_posix() not in pages:
            errors.append(f"{relative}: missing generated page {output}")

    def check_link(owner, link, asset=False):
        if link == "#" or link.startswith(("data:", "mailto:", "tel:")):
            return
        url = urlsplit(urljoin(urljoin(BASE, owner), link))
        path = unquote(url.path)
        if "reports" in path.split("/"):
            errors.append(f"{owner}: weekly report link {link}")
            return
        if url.netloc != BASE_URL.netloc:
            if asset:
                errors.append(f"{owner}: external browser asset {link}")
            return
        if not path.startswith(BASE_URL.path):
            errors.append(f"{owner}: link escapes {BASE_URL.path}: {link}")
            return
        target = path[len(BASE_URL.path):]
        if not target or target.endswith("/"):
            target += "index.html"
        destination = (SITE / target).resolve()
        if not destination.is_relative_to(SITE.resolve()) or not destination.is_file():
            errors.append(f"{owner}: missing local target {link}")
        elif url.fragment and target in pages and unquote(url.fragment) not in pages[target].ids:
            errors.append(f"{owner}: missing anchor {link}")

    links = 0
    for name, page in pages.items():
        for link, asset in page.links:
            links += 1
            check_link(name, link, asset)
    for css in SITE.rglob("*.css"):
        for link in re.findall(r"url\([\"']?([^\)\"']+)", css.read_text()):
            check_link(css.relative_to(SITE).as_posix(), link, asset=True)
    for path in SITE.rglob("*"):
        if "reports" in path.relative_to(SITE).parts:
            errors.append(f"Weekly evidence copied into site: {path.relative_to(SITE)}")
    for name in ("mermaid.min.js", "mermaid-init.js", "mermaid-LICENSE", "diagrams.css"):
        if not (SITE / "assets" / name).is_file():
            errors.append(f"Missing local diagram asset: {name}")
    if errors:
        raise SystemExit("\n".join(errors))
    print(f"PASS: {len(sources)} maintained pages, {links} links/assets, local anchors and report exclusion")


if __name__ == "__main__":
    main()
