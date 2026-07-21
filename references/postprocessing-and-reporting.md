# Post-processing and reporting

Read this file when extracting results with PyDPF-Post or generating a
report.

## PyDPF-Post patterns

```python
from ansys.dpf import post

solution = post.load_solution(r"C:\path\to\file.rst")

stress = solution.stress()
eqv = stress.eqv                     # von Mises equivalent stress
eqv_max = eqv.max_data                # scalar or per-node/element array

disp = solution.displacement()
disp_norm = disp.norm

strain = solution.elastic_strain()
```

Or with the newer `ansys.dpf.post` simulation API (preferred for new code):

```python
from ansys.dpf import post

simulation = post.load_simulation(r"C:\path\to\file.rst")
stress_result = simulation.stress_eqv_von_mises(set_ids=[1])
disp_result = simulation.displacement(set_ids=[1])
```

Always specify nodal vs elemental location explicitly (`location="Nodal"` /
`"Elemental"`) — the two give different values at the same point and
silently defaulting is a common source of confused comparisons.

For modal results, extract frequencies and mode shapes per mode index; for
transient/harmonic, extract per time step or per frequency point — never
report a single aggregate number for a time- or frequency-varying result
without stating which step/frequency it's from.

## Aggregating into a DataFrame

```python
import pandas as pd

rows = []
for case in cases:
    rows.append({
        "case_id": case.id,
        "max_eqv_stress_pa": case.max_eqv_stress,
        "max_deformation_m": case.max_deformation,
    })
df = pd.DataFrame(rows)
```

This is the shape `sweep_runner.py` writes to `runs/manifest.csv`
automatically from each case's printed JSON line — reuse that manifest
directly rather than re-deriving it by hand.

## Contour images vs summary charts

- Contour screenshots (stress/displacement field on the geometry) are useful
  for one or a few cases; export via the app's plotting (`eqv.plot_contour()`
  in classic DPF-Post, or Mechanical's own image export) to PNG for embedding.
- Summary charts (bar/line comparing a metric across sweep cases) are better
  built directly from the manifest DataFrame with matplotlib, not by
  screenshotting each case individually.

## DPF-Post cannot load every result format

`ansys.dpf.core.DataSources`/`Model` cannot load AUTODYN's native Explicit
Dynamics result format (`.adres`) — attempting to raises `DPFServerException:
Data sources not defined`, even though the local DPF server itself starts
fine. For an AUTODYN-solved analysis, do contour/result export through
Mechanical's own `graphics.ExportImage()` (see below), not DPF-Post/PyVista.

## Exporting a contour image from an embedded/batch Mechanical session

`GraphicsImageExportSettings.CurrentGraphicsDisplay` defaults to `True`,
which tries to screenshot the "current display buffer." An embedded
`App()`/batch-mode session has no real display buffer, so the export
silently "succeeds" (returns a file, no exception) but the image shows only
sparse, scattered vertex-color specks on an otherwise dark/near-black panel
instead of a smooth interpolated contour — a rendering defect that is easy
to miss if you only check "did a file get written," and easy to mistake for
a results problem rather than an export-settings problem. The legend,
min/max values, and units in the (defective) image are still correct; only
the rendered field itself is broken.

**Fix**: force real offscreen rendering by disabling
`CurrentGraphicsDisplay` and giving explicit dimensions:

```python
from Ansys.Mechanical.DataModel.Enums import GraphicsImageExportFormat, GraphicsResolutionType
from Ansys.Mechanical.Graphics import GraphicsImageExportSettings

settings = GraphicsImageExportSettings()
settings.CurrentGraphicsDisplay = False   # the actual fix
settings.Width = 1920
settings.Height = 1080
settings.Resolution = GraphicsResolutionType.HighResolution

graphics = app.ExtAPI.Graphics
graphics.ViewOptions.ShowMesh = False
for result_obj, out_path in [(td, "deformation.png"), (es, "stress.png")]:
    result_obj.Activate()
    graphics.Camera.SetFit()
    graphics.ExportImage(out_path, GraphicsImageExportFormat.PNG, settings)
```

Diagnostic shortcut: compare file sizes before opening images. The defective
(speckled) export on a typical panel comes out to a suspiciously *consistent*
size regardless of what else you change (~170KB in this project, unchanged
across `ShowMesh`, `AcceleratedGraphics` variants); the corrected export
jumps ~4-5x larger (~700-900KB) and stays proportional to actual image
content. A cluster of same-size exports across otherwise-different settings
is itself a signal something upstream (not the setting you're varying) is
the real cause — don't only vary settings that seem intuitively related to
color/contour; also check the display/capture pipeline itself.

Other export paths tried and ruled out for this defect:
- `graphics.AcceleratedGraphics` (real property, an `AccGraphicsPreference`
  enum — not a bool; `System.Enum.Parse(enum_type, name)` to set it) — all
  three values (`No`/`YesIfPossible`/`ProgramControlled`) produced the same
  defective output. Not the cause.
- `graphics.ViewOptions.ShowMesh` — no effect on the defect.
- `graphics.ExportViewportImage(path)` — real method, but does not accept a
  bare path string; the working signature wasn't pinned down, and wasn't
  needed once `ExportImage` was fixed via settings.
- `graphics.ExportScreenToImage(path)` — executes without error but silently
  produces no file. Dead end.
- `App(project_path, interactive=True)` (a real GUI-backed embedded session)
  — only supported starting ANSYS 2026 R1 (version 261+); raises
  `RuntimeError: Interactive mode is only supported starting with version
  261` on earlier installs. Not available as a workaround on 2025 R2 or
  earlier.

If a fresh install/version reproduces a similar-looking rendering defect and
none of the above matches, see the open, related (but distinct) upstream bug
`ansys/pymechanical#1374` — batch-mode `ResultPreference.GeometryView =
CappedIsosurface` (or `.CappingType`) can also cause an export to show only
the legend with no contour at all. That symptom (empty plot vs speckled
plot) is different from the one fixed above, but confirms embedded/batch-mode
Mechanical has more than one unresolved graphics-export bug — don't assume a
single settings change fixes every rendering-export issue you hit.

## Report manifest shape

`scripts/report_builder.py build --manifest runs/manifest.csv --out report.docx`
expects a CSV with a `case_id` column plus one column per reported metric —
exactly what `sweep_runner.py run` produces, or a hand-built single-row CSV
for a one-off case. It renders every number directly from manifest columns;
it does not compute or infer values not present in the file.

This manifest-driven builder is the right tool for a sweep comparison table
(many cases, a handful of numeric columns, optional bar charts). It is the
*wrong* tool for a single, richly-narrated engineering report — methodology
section, multiple embedded contour images with captions, a hedged
pass/fail-style engineering conclusion — because that content doesn't fit a
flat case_id×metric CSV. For that shape, hand-author a `python-docx` script
directly (headings, tables via `doc.add_table`, images via
`doc.add_picture`), pulling every number from the same real, solved sources
(solve log, material XML, geometry report JSON) rather than from a manifest.
Whichever path you use, the same discipline applies: every number must trace
to an actual solved/extracted value, and every assumption (impactor mass,
material data provenance, etc.) must be stated in the report itself, not just
in chat.

## Tagging discipline

Every reported number must be traceable to its source: case id, time step,
frequency point, or mode index. A number with no such tag should not appear
in a final report or summary — restate it with its source or drop it.
