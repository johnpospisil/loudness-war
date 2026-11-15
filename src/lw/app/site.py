"""P22: assemble the GitHub Pages site in ``docs/`` (served from the main branch).

docs/index.html          the article (report/index.html, links rewritten)
docs/app/                the "How loud is my album?" app (app/ + app/data/)
docs/figures/final_*     the interactive charts linked from the article (+ PNGs)
docs/.nojekyll           serve files as-is

Asset URLs in docs/app get a ?v=<content hash> so browsers never mix old and new files.

uv run python -m lw.app.site
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DOCS = ROOT / "docs"


def _v(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:10]


def fingerprint(app: Path) -> None:
    """Add ``?v=<content hash>`` to every asset URL, so a changed file gets a new URL.

    GitHub Pages lets browsers cache files for 10 minutes; without this a normal reload
    can keep running an old app.js against new data."""
    js = app / "app.js"
    s = js.read_text()
    for name in ["data/dist.json", "data/albums.parquet"]:
        assert f'fetch("{name}")' in s, name
        s = s.replace(f'fetch("{name}")', f'fetch("{name}?v={_v(app / name)}")')
    js.write_text(s)  # data hashes first: they are part of app.js's own hash
    html = app / "index.html"
    h = html.read_text()
    for name, attr in [("style.css", "href"), ("app.js", "src")]:
        assert f'{attr}="{name}"' in h, name
        h = h.replace(f'{attr}="{name}"', f'{attr}="{name}?v={_v(app / name)}"')
    html.write_text(h)


def build() -> list[str]:
    if DOCS.exists():
        shutil.rmtree(DOCS)
    (DOCS / "figures").mkdir(parents=True)
    html = (ROOT / "report/index.html").read_text()
    for a, b in [('href="../app/', 'href="app/'), ('href="../figures/', 'href="figures/')]:
        html = html.replace(a, b)
    (DOCS / "index.html").write_text(html)
    shutil.copytree(ROOT / "app", DOCS / "app", ignore=shutil.ignore_patterns("tests", "*.md"))
    fingerprint(DOCS / "app")
    for f in sorted((ROOT / "figures").glob("final_*")):
        shutil.copy(f, DOCS / "figures" / f.name)
    (DOCS / ".nojekyll").write_text("")
    return sorted(str(p.relative_to(DOCS)) for p in DOCS.rglob("*") if p.is_file())


def main() -> None:
    files = build()
    size = sum((DOCS / f).stat().st_size for f in files) / 1e6
    print(f"docs/: {len(files)} files, {size:.1f} MB")
    for f in files:
        print(" ", f)


if __name__ == "__main__":
    main()
