# Fatigue and parameter sweeps

Read this file when setting up the Fatigue Tool, or designing/running a
parameter sweep or DOE.

## Fatigue Tool

Supported upstream analyses: Static Structural, Transient Structural,
Harmonic Response, and Random Vibration (spectral fatigue). It is not
available standalone — it always attaches to a solved upstream analysis.

```python
fatigue_tool = static.Solution.AddFatigueTool()
fatigue_tool.Materials = "1"  # material S-N curve source, verify assigned
fatigue_tool.MeanStressTheory = "None"  # or Goodman/Soderberg/Gerber, etc.

life = fatigue_tool.AddLife()
damage = fatigue_tool.AddDamage()
sf = fatigue_tool.AddSafetyFactor()
```

Report explicitly: which upstream analysis the tool attaches to, the S-N/
fatigue material data source (must be assigned per-material, not assumed
default), the mean-stress-correction theory in effect, and whether the loading
is fully-reversed or has a nonzero mean (affects which correction theory is
appropriate).

## Designing a parameter sweep

Decide what varies per run: material properties, load magnitude/direction,
named geometry dimensions (parametrized in the CAD source, re-imported per
row), or boundary condition choices. Each row is one independent case; keep
non-swept settings fixed and stated.

`scripts/sweep_runner.py` expects a `params.csv` (or `.yaml`) with one column
per parameter and one row per case, e.g.:

```csv
case_id,load_n,wall_thickness_mm,material
case_01,500,3.0,Structural Steel
case_02,1000,3.0,Structural Steel
case_03,500,4.5,Structural Steel
```

and a **template script** (`run_case.py`) that:
- accepts each column as a CLI flag or env var (Claude writes this script;
  `sweep_runner.py` only invokes it per row),
- opens and closes its own ANSYS session per invocation,
- prints exactly one JSON line of extracted results as its last stdout line,
  e.g. `{"case_id": "case_01", "max_eqv_stress_pa": 1.2e8, "max_deformation_m": 3.1e-4}`.

`sweep_runner.py plan` parses the parameter matrix and prints the resulting
case list and count without opening any ANSYS session — always run `plan`
before `run --execute` and review the case count and expected license time.

## License-seat-aware concurrency

Each concurrent sweep case holds its own license seat for its full solve
duration. Set `--max-parallel` no higher than the seats actually available
(confirm with `session_check.py check` and the user's license entitlement) —
oversubscribing seats causes some cases to fail at launch with a license
checkout error rather than a modeling error, which is easy to misdiagnose.
