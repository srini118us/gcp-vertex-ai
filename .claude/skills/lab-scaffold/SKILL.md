---
name: lab-scaffold
description: Scaffold a new GCP agent lab folder with the project README, architecture view placeholder, and gaps list. Use when starting a new lab in the gcp-vertex-ai repo so every lab follows the same structure.
---

# Lab scaffold

Stand up a new lab in the gcp-vertex-ai repo with the conventions every lab here
follows: an architecture view, a README, and a gaps list, with the runbook kept
local and gitignored.

## When to use

Use this when starting a new lab, for example a new RAG pattern lab or an end to
end use case. Do not use it to edit an existing lab.

## How to run

Run the bundled script with the lab name and an optional title:

    python scripts/new_lab.py <lab-name> --title "<Readable Title>"

The script creates:
- `<lab-name>/README.md` from the template, with the title and today date filled
- `<lab-name>/GAPS.md`, the open gaps list
- `<lab-name>/docs/runbook/`, the local runbook folder with a .gitkeep

Run the script rather than writing these files by hand, so the structure stays
identical across labs and the step is repeatable.

## Conventions to preserve

- Only the README is pushed to GitHub. The runbook, screenshots, and raw output
  stay local under <lab-name>/docs/, which the root .gitignore excludes with */docs/.
- Every lab README carries an architecture view, the build and decisions, and a
  link to the gaps list.
- Write prose without hyphens or dashes, and avoid second person possessives, to
  match the repo style.

## After scaffolding

Fill the README architecture view and sections. The exact README skeleton and the
section order live in `reference/readme-template.md`; read that only when writing
the README, not before.
