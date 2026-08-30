#!/usr/bin/env python3
"""Validate the repository-level textbook-writing skill package."""

from __future__ import annotations

import argparse
from pathlib import Path
import re


REQUIRED_RESOURCES = (
    "references/acceptance.md",
    "scripts/check_textbook_contract.py",
    "scripts/browser_acceptance.py",
    "tests/test_textbook_contract.py",
    "VERSION",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, default=Path.cwd())
    args = parser.parse_args()
    root = args.root.expanduser().resolve()
    errors: list[str] = []
    skill = root / "SKILL.md"
    if not skill.is_file() or skill.is_symlink():
        errors.append("SKILL.md must be an ordinary file")
        text = ""
    else:
        text = skill.read_text(encoding="utf-8")
    if not re.match(r"^---\n(?s:.*?)\n---\n", text):
        errors.append("SKILL.md frontmatter is missing or malformed")
    if not re.search(r'^name:\s*["\']?textbook-writing["\']?\s*$', text, flags=re.M):
        errors.append("frontmatter name must be textbook-writing")
    description = re.search(r'^description:\s*["\']?(.*?)["\']?\s*$', text, flags=re.M)
    if description is None or len(description.group(1).strip()) < 40:
        errors.append("frontmatter description is missing or too short")
    for relative in REQUIRED_RESOURCES:
        path = root / relative
        if not path.is_file() or path.is_symlink():
            errors.append(f"required resource is missing or not ordinary: {relative}")
    version_path = root / "VERSION"
    if version_path.is_file() and version_path.read_text(encoding="utf-8").strip() != "2.2.0":
        errors.append("VERSION must be 2.2.0")
    linked_paths = re.findall(r"\]\((references/[^)#]+|scripts/[^)#]+)\)", text)
    for relative in linked_paths:
        if not (root / relative).is_file():
            errors.append(f"SKILL.md links to a missing resource: {relative}")
    print(
        {
            "status": "PASS" if not errors else "FAIL",
            "skill": str(skill),
            "required_resource_count": len(REQUIRED_RESOURCES),
            "linked_resource_count": len(linked_paths),
            "errors": errors,
        }
    )
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
