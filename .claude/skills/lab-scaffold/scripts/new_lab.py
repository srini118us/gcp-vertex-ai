"""Scaffold a new lab folder with the project conventions.

Usage:
    python scripts/new_lab.py <lab-name> --title "Readable Title"

Creates <lab-name>/README.md from reference/readme-template.md, a GAPS.md, and a
local <lab-name>/docs/runbook/ folder. Run from the repo root.
"""
import argparse
import datetime
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "..", "reference", "readme-template.md")


def main():
    parser = argparse.ArgumentParser(description="Scaffold a new lab folder.")
    parser.add_argument("lab_name", help="folder name, e.g. rag-r1-naive")
    parser.add_argument("--title", default=None, help="readable README title")
    args = parser.parse_args()

    lab = args.lab_name.strip().strip("/")
    title = args.title or lab.replace("-", " ").title()
    today = datetime.date.today().isoformat()

    if os.path.exists(lab):
        sys.exit(f"refusing to overwrite existing folder: {lab}")

    with open(TEMPLATE, encoding="utf-8") as fh:
        readme = fh.read().replace("{{TITLE}}", title).replace("{{DATE}}", today)

    os.makedirs(lab, exist_ok=True)
    with open(os.path.join(lab, "README.md"), "w", encoding="utf-8") as fh:
        fh.write(readme)
    with open(os.path.join(lab, "GAPS.md"), "w", encoding="utf-8") as fh:
        fh.write(f"# {title}, open gaps\n\n- \n")

    runbook = os.path.join(lab, "docs", "runbook")
    os.makedirs(runbook, exist_ok=True)
    with open(os.path.join(runbook, ".gitkeep"), "w", encoding="utf-8") as fh:
        fh.write("")

    print(f"created {lab}/README.md")
    print(f"created {lab}/GAPS.md")
    print(f"created {runbook}/ (local runbook, gitignored by */docs/)")
    print("next: fill the architecture view and sections in the README")


if __name__ == "__main__":
    main()
