"""P22: assemble the GitHub Pages site in ``docs/`` (served from the main branch).

docs/index.html          the article (report/index.html, links rewritten)
docs/app/                the "How loud is my album?" app (app/ + app/data/)
docs/figures/final_*     the interactive charts linked from the article (+ PNGs)
docs/.nojekyll           serve files as-is

uv run python -m lw.app.site
"""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DOCS = ROOT / "docs"


def build() -> list[str]:
    if DOCS.exists():
        shutil.rmtree(DOCS)
    (DOCS / "figures").mkdir(parents=True)
    html = (ROOT / "report/index.html").read_text()
    for a, b in [('href="../app/', 'href="app/'), ('href="../figures/', 'href="figures/')]:
        html = html.replace(a, b)
    (DOCS / "index.html").write_text(html)
    shutil.copytree(ROOT / "app", DOCS / "app", ignore=shutil.ignore_patterns("tests", "*.md"))
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
