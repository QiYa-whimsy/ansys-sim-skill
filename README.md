# ansys-sim

A Claude Code / Claude Agent skill for automating ANSYS Workbench structural
simulation via PyAnsys (`ansys-mechanical-core` / PyMechanical,
`ansys-mapdl-core` / PyMAPDL, `ansys-dpf-post` / PyDPF-Post).

## What it covers

- Writing/debugging PyMechanical (object-model) or PyMAPDL (command-level)
  Python against a real ANSYS install.
- Static structural, modal, harmonic response, random vibration, transient
  structural, Explicit Dynamics (drop/impact tests), and fatigue analyses.
- Batch parameter sweeps / DOE studies across load, material, or geometry
  variants.
- Extracting results with PyDPF-Post and turning them into tables, charts,
  contour images, or Word/Excel/PDF reports.

## Install

```bash
npx skills add <owner>/ansys-sim-skill
```

Or clone directly into your skills directory (e.g.
`~/.claude/skills/ansys-sim`).

## Layout

- `SKILL.md` — dispatcher: when to use this skill, default assumptions,
  required workflow, non-negotiables, and pointers into `references/`.
- `references/` — deep procedural detail per topic (environment setup,
  static structural, dynamics analyses, Explicit Dynamics/impact, fatigue
  and sweeps, post-processing/reporting, troubleshooting), each loaded only
  when its trigger applies.
- `scripts/` — reusable CLI tooling: license/session diagnostics
  (`session_check.py`), pre-solve sanity checks for contact/impact analyses
  (`preflight_check.py`), a parameter-sweep orchestrator (`sweep_runner.py`),
  and a report builder (`report_builder.py`).

## Notable lessons baked into this skill

- A solve that completes cleanly (`Solved`/`Done`, no exception) with every
  result exactly zero is not proof of a valid result — it's the signature of
  a load/contact that never acted on the model. `preflight_check.py` exists
  specifically to catch this before a full multi-hour solve, not after.
- Several embedded/batch-mode Mechanical API gotchas (unit-system lookup,
  geometry bounding box, material assignment casting, contour image export
  defaults) that aren't obvious from the API surface are documented with the
  real errors they produce.

This skill's guidance is grounded in an actual PyAnsys automation project
(a 6.8J impact test against a sheet-metal enclosure) rather than written
speculatively from documentation alone.
