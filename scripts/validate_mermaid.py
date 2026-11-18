"""Render every Mermaid code block in docs/architecture with Mermaid CLI."""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path


def main() -> None:
    architecture_dir = Path("docs/architecture")
    diagrams = sorted(architecture_dir.glob("*.md"))
    rendered = 0
    with tempfile.TemporaryDirectory(prefix="clos-mermaid-") as temp_dir:
        temp_path = Path(temp_dir)
        for markdown_path in diagrams:
            source = markdown_path.read_text(encoding="utf-8")
            blocks = re.findall(r"```mermaid\s*\n(.*?)\n```", source, re.DOTALL)
            for index, block in enumerate(blocks):
                mermaid_path = temp_path / f"{markdown_path.stem}-{index}.mmd"
                output_path = temp_path / f"{markdown_path.stem}-{index}.svg"
                mermaid_path.write_text(block, encoding="utf-8")
                subprocess.run(
                    ["mmdc", "-i", str(mermaid_path), "-o", str(output_path)],
                    check=True,
                )
                rendered += 1
    if rendered == 0:
        raise SystemExit("No Mermaid diagrams found under docs/architecture")
    print(f"Rendered {rendered} Mermaid diagrams")


if __name__ == "__main__":
    main()
