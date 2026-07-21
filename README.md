# ansys-sim

[中文说明](README.zh-CN.md)

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

Every example below comes from a real Explicit Dynamics (AUTODYN) impact-
test project this skill was built from. Filenames and specific numeric
results are genericized here to avoid disclosing the underlying product;
the pitfalls and error messages themselves are exactly as encountered.

- **A solve that completes cleanly is not proof of a valid result.** The
  impactor's `Velocity` was initially set to `-Z` based on a stale geometry
  assumption, while the impactor's actual bounding box sat on the wrong side
  of the target along Z — it needed to travel `+Z` to close the gap.
  `ed.Solve(True)` returned with `Solution.ObjectState == Solved`, `Status
  == Done`, no exception — and every result (`TotalDeformation`,
  `EquivalentStress`, `EquivalentPlasticStrain`) evaluated to exactly
  `Maximum = 0`. Two full solves (each over an hour of real license time)
  ran to completion before this was caught. `preflight_check.py` exists
  specifically to catch this in seconds, before a full solve:

  ```bash
  python scripts/preflight_check.py direction \
    --target target.stp --mover impactor.stp --velocity 0 0 1
  # Dot product: 0.9998
  # PREFLIGHT PASS: velocity points toward the target (dot=0.9998 > 0.05).
  ```

- **Explicit Dynamics requires linear elements explicitly.**
  `mesh.ElementOrder` defaults to `ProgramControlled`, which silently picked
  quadratic elements in this project and failed late in solve setup
  (`Too many nodes per element`) rather than at mesh time. Set
  `mesh.ElementOrder = ElementOrder.Linear` before `GenerateMesh()`.

- **Velocity load components are not writable directly** — the pattern that
  actually works is `vel.ZComponent.Output.DiscreteValues = [Quantity(v,
  unit_str)]` (a list), not direct assignment or `.SetDiscreteValue(...)`.

- **Multi-body geometry has no `.BoundingBox` property** — `Body`/
  `GeoBodyWrapper` objects require iterating `.GetGeoBody().Vertices` to
  compute extents/centroids, which is exactly how the direction check above
  works.

- **Contour image export can silently render garbage.**
  `GraphicsImageExportSettings.CurrentGraphicsDisplay` defaults to `True`,
  which produces a "successful" PNG export (correct legend/min/max) that's
  actually just sparse speckled pixels on a near-black panel in an
  embedded/batch session with no real display buffer. Diagnostic: the
  defective export sat at a suspiciously consistent file size regardless of
  other settings tried; the fixed export (`CurrentGraphicsDisplay = False` +
  explicit `Width`/`Height`/`Resolution`) jumped several times larger and
  scaled with actual content.

- **Order of magnitude, for scale** (not this project's actual numbers):
  tens of thousands of nodes / linear elements, a millisecond-scale step
  end time, and a 1-3 hour real solve — treat every full Explicit Dynamics
  solve as expensive and worth a preflight check first.

See [README.zh-CN.md](README.zh-CN.md) for the fuller Chinese write-up of
these and other gotchas (`MaterialAssignment.Location` casting,
`FeatureSuppress` mesh-defeaturing failures, the nonexistent
`model.Project.UnitSystem`, DPF-Post's inability to load AUTODYN's
`.adres` format) documented in `references/`.
