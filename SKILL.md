---
name: ansys-sim
description: Automate ANSYS Workbench structural simulation via PyAnsys (PyMechanical, PyMAPDL, PyDPF-Post). Use for static structural, modal, harmonic response, random vibration, transient structural, Explicit Dynamics (drop/impact tests), and fatigue analyses; for writing or debugging Python that drives Mechanical's object model or MAPDL command-level solving; for batch parameter sweeps or multi-load-case studies; and for extracting stress, strain, displacement, frequency, or mode-shape results and turning them into charts, tables, contour images, or Word/Excel/PDF simulation reports. Do not use for CAD geometry authoring (use `$cad`), CFD/thermal-only/electromagnetics workflows, or non-ANSYS FEA tools.
---

# ANSYS Workbench simulation automation (PyAnsys)

## Purpose

Automate ANSYS Workbench structural analyses through PyAnsys instead of manual
GUI operation. Write or debug PyMechanical (object-model, mirrors Mechanical's
own scripting/ACT Python interface) or PyMAPDL (command-level APDL control)
code, orchestrate batch parameter sweeps across many load-case/material/
geometry variants, and turn PyDPF-Post-extracted results into aggregated
tables, charts, and simulation reports.

## Use this skill when

- Writing or debugging PyMechanical (`ansys-mechanical-core`) or PyMAPDL
  (`ansys-mapdl-core`) Python.
- Setting up or diagnosing the Mechanical/MAPDL Python connection or ANSYS
  licensing.
- Static structural, modal, harmonic response, random vibration, transient
  structural, Explicit Dynamics (drop tests, impact tests, other short-
  duration high-rate events), or fatigue analyses.
- Running a parameter sweep or DOE across geometry, material, or load
  variants on the same model.
- Extracting stress, strain, displacement, frequency, or mode-shape results
  with PyDPF-Post (`ansys-dpf-post`).
- Producing a Word/Excel/PDF simulation report from solved results.

Do not use this skill for CAD geometry creation — defer to `$cad` (or source a
catalog part via `$step-parts`) and import the resulting STEP/Parasolid file
into the analysis. Do not use it for CFD, thermal-only, or electromagnetics
Workbench systems, or non-ANSYS FEA tools. A completed `.solve()` call is never
by itself proof of a correct result — mesh quality, convergence, and boundary
condition review are still required; see Non-negotiables.

## Default assumptions

- Never assume a unit system. Read and report the model's active unit system
  before writing loads or materials (a common Workbench default template is
  `mm, kg, N, s, mV, mA, °C`), and flag any mismatch between geometry,
  material, and load units — this is the most common silent correctness bug
  in this domain.
- Geometry is imported (STEP/Parasolid) from an existing CAD source; this
  skill does not author geometry from scratch.
- Connection mode: use the embedded, in-process `ansys.mechanical.core.App`
  (or in-process `launch_mapdl`) for interactive/dev scripting; use gRPC
  launch (`launch_mechanical`, `launch_mapdl` as a server process) for
  headless/CI/batch sweep runs, since it isolates each run's process and
  session.
- Every ANSYS session consumes a shared, exhaustible license seat. Always
  close sessions (`app.close()`, `mapdl.exit()`) in a `finally` block, on
  every code path including failures.
- Never overwrite an existing `.mechdb`/`.dat`/`.rst` file implicitly; sweep
  runs write to a new, explicitly named output directory per run.

## Tools and paths

```bash
python scripts/session_check.py check
python scripts/preflight_check.py direction --target part.stp --mover impactor.stp --velocity 0 0 1
python scripts/preflight_check.py pilot --template run_case.py --full-end-time-s 0.02
python scripts/sweep_runner.py plan  --params params.csv --template run_case.py
python scripts/sweep_runner.py run   --params params.csv --template run_case.py --execute
python scripts/report_builder.py build --manifest runs/manifest.csv --out report.docx
```

Treat `python` in examples as an interpreter placeholder for the active
project environment. Target and output paths resolve from the command's
current working directory, not the skill directory; run these from the
workspace that owns the project files.

## Required workflow

1. **Classify the task.** New single analysis, parameter sweep, post-process-
   only, script debugging, or report generation.
2. **Check the environment.** Run `session_check.py check` before any real
   solve work to confirm ANSYS install(s), license reachability, and that no
   orphaned sessions are already holding seats.
3. **Load only the needed references.** Use the triggers in Progressive
   references below instead of reading the whole reference set.
4. **Write or adapt the script.** State connection mode, unit system, and
   geometry source explicitly in the script or its docstring. For any
   analysis where a body moves toward/into another (impact, drop test,
   moving contact), give the pipeline script an `--end-time-s` CLI override
   from the start — it costs nothing to add up front and is required to use
   the pilot-solve preflight cheaply later.
5. **Preflight before a full solve — mandatory for contact/impact analyses,
   recommended generally.** Before spending real license time on a full
   solve:
   - Run `preflight_check.py direction` for any analysis with a body moving
     toward a target, confirming the configured velocity/motion actually
     points at it. This is geometry-import-only (seconds), not a real solve.
   - For long solves (Explicit Dynamics, large nonlinear transients), run
     `preflight_check.py pilot` at a small fraction (e.g. 5%) of the intended
     duration and confirm the results are already nonzero before committing
     to the full duration.
   - A solve that completes cleanly (`Solved`/`Done`, no exception) with
     every result exactly zero is not a valid "no response" result for a
     contact/impact analysis — it is the signature of a setup that never
     made contact. Treat an all-zero outcome as a red flag to investigate,
     not a result to report. See `explicit-dynamics-impact.md` and
     `troubleshooting.md`.
6. **State a solve plan before solving.** Before calling `.solve()` (or
   launching a sweep), report mesh stats (node/element count, worst
   skewness/aspect ratio if available), a boundary-condition and load
   summary, the analysis settings actually in effect, and — for sweeps — the
   run count and expected license time. Do not solve past this checkpoint
   without stating it.
7. **Solve.** A single case directly, or a sweep via `sweep_runner.py run
   --execute` (itself dry-run/`plan`-only by default without `--execute`).
8. **Post-process.** Extract only the results the user's spec calls for,
   each tagged with the load case, time step, or mode it came from — via
   PyDPF-Post where the result format supports it, or Mechanical's own
   `graphics.ExportImage()` for contour images (PyDPF-Post cannot load every
   native result format, e.g. AUTODYN's `.adres` — see
   `postprocessing-and-reporting.md`). If exporting contour images from an
   embedded/batch session, verify one image visually before exporting the
   full set — a wrong `GraphicsImageExportSettings` default can produce a
   file that "succeeds" but renders incorrectly (see
   `postprocessing-and-reporting.md`).
9. **Report.** Build the report via `report_builder.py` for a manifest-
   shaped sweep/comparison, or hand-author a `python-docx` script directly
   for a single richly-narrated report (methodology, embedded contour
   images, hedged engineering conclusion) — see
   `postprocessing-and-reporting.md` for when each fits. State which checks
   ran, which were skipped, and all assumptions in the report itself,
   including the *direction* of bias each simplification introduces (e.g.
   rigid boundary conditions overstate local stiffness, a rate-independent
   material curve overstates deformation under high-rate loading) and, for
   impact/drop analyses, the impactor's contact geometry and whether a
   reported deformation is a transient peak or a permanent residual set.
10. **Always release sessions.** Close every open Mechanical/MAPDL session,
    including on early failure paths.

## Non-negotiables

- Never silently change solver, analysis, or meshing defaults; always report
  the exact settings used.
- A completed solve is not validation — always report mesh quality and
  convergence status alongside results.
- Verify and state the unit system in effect before trusting any number.
- For contact/impact analyses, run the direction preflight check (and a
  pilot solve for long ones) before committing to a full-duration solve — a
  clean `Solved`/`Done` status never confirms the load actually acted on the
  model; an all-zero result after a full solve is a wasted license-hours
  mistake this project made twice, not a rare edge case.
- Get an explicit solve-plan checkpoint (workflow step 6) before consuming a
  license seat on a real `.solve()` call, especially for sweeps.
- Always release sessions; never leave an orphaned Mechanical/MAPDL process
  holding a license seat.
- Report only values actually extracted via DPF-Post; never fabricate or
  interpolate results beyond what was solved.

## Progressive references

Load these files only when their trigger applies:

- `references/environment-setup.md` — setting up or debugging the
  Mechanical/MAPDL Python connection, launch mode, or ANSYS licensing.
- `references/static-structural.md` — building or editing a static
  structural PyMechanical/PyMAPDL script.
- `references/dynamics-analyses.md` — modal, harmonic response, random
  vibration, or transient structural analysis.
- `references/explicit-dynamics-impact.md` — Explicit Dynamics (AUTODYN)
  drop/impact analysis: element order, rigid-body impactor setup, velocity
  loads, the direction/pilot-solve preflight checks, and result-evaluation
  gotchas.
- `references/fatigue-and-sweeps.md` — setting up the Fatigue Tool, or
  designing/running a parameter sweep or DOE.
- `references/postprocessing-and-reporting.md` — extracting results with
  PyDPF-Post or generating a report.
- `references/troubleshooting.md` — a PyAnsys call errors, hangs, times out,
  or a session/process looks orphaned.

Final responses should include the settings actually used, checks run versus
skipped, extracted results with their source tags, and explicit assumptions
and caveats — never present a solve as validated without the mesh/convergence/
unit checks called for above.
