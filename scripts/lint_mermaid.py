"""Mermaid diagram lint: parse every fenced ```mermaid block under docs/ and CLAUDE.md headlessly.

Fails on any parse error -- guards against diagram-syntax pitfalls (an unquoted `;` or `(`/`)`
inside a node/state/sequence label) that render blank rather than erroring in many viewers.
See docs/v3_specification/16_Engineering_Standards/08_CICD_AND_PACKAGING.md Section 4 (Lint).

Requires `@mermaid-js/mermaid-cli` reachable via `npx` (Node.js on PATH).
"""

from __future__ import annotations

from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

REPO_ROOT = Path(__file__).resolve().parent.parent
MERMAID_FENCE = re.compile(r"```mermaid\n(.*?)```", re.DOTALL)
SEARCH_ROOTS = [REPO_ROOT / "docs", REPO_ROOT / "CLAUDE.md"]
# The vendored spec and reference planning docs are read-only content, but their diagrams still
# ship to readers -- they are linted, never modified.


def find_markdown_files() -> list[Path]:
    files: list[Path] = []
    for root in SEARCH_ROOTS:
        if root.is_file():
            files.append(root)
        elif root.is_dir():
            files.extend(sorted(root.rglob("*.md")))
    return files


def extract_blocks(markdown_path: Path) -> list[str]:
    text = markdown_path.read_text(encoding="utf-8")
    return MERMAID_FENCE.findall(text)


def validate_block(block: str, tmp_dir: Path, label: str, npx_path: str) -> str | None:
    mmd_path = tmp_dir / "diagram.mmd"
    svg_path = tmp_dir / "diagram.svg"
    mmd_path.write_text(block, encoding="utf-8")
    result = subprocess.run(  # noqa: S603  # npx_path resolved via shutil.which; args are fixed/local paths
        [
            npx_path,
            "--yes",
            "@mermaid-js/mermaid-cli",
            "-i",
            str(mmd_path),
            "-o",
            str(svg_path),
            "--puppeteerConfigFile",
            "-",
        ],
        input='{"args": ["--no-sandbox"]}',
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return f"{label}: {result.stderr.strip() or result.stdout.strip()}"
    return None


def main() -> int:
    npx_path = shutil.which("npx")
    if npx_path is None:
        sys.stderr.write("npx not found on PATH -- Node.js is required to run the Mermaid lint.\n")
        return 1

    failures: list[str] = []
    block_count = 0
    markdown_files = find_markdown_files()
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        for markdown_path in markdown_files:
            blocks = extract_blocks(markdown_path)
            for index, block in enumerate(blocks, start=1):
                block_count += 1
                label = f"{markdown_path.relative_to(REPO_ROOT)}#mermaid-block-{index}"
                error = validate_block(block, tmp_dir, label, npx_path)
                if error is not None:
                    failures.append(error)

    sys.stdout.write(
        f"Checked {block_count} Mermaid block(s) across {len(markdown_files)} file(s).\n"
    )
    if failures:
        sys.stderr.write("Mermaid lint FAILED:\n")
        for failure in failures:
            sys.stderr.write(f"  - {failure}\n")
        return 1
    sys.stdout.write("Mermaid lint OK.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
