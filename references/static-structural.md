# Static structural

Read this file when building or editing a static structural
PyMechanical/PyMAPDL script.

## Object-model walk (PyMechanical)

```python
from ansys.mechanical.core import App

app = App()
model = app.Model
geom_import = model.GeometryImportGroup.AddGeometryImport()
geom_import.Import(r"C:\path\to\part.stp")

mats = model.Materials
mats.Import(r"C:\path\to\material.xml")  # MatML-XML, must include a <Metadata> block
# (a MatML file with <Material> but no <Metadata> ParameterDetails/PropertyDetails
#  block has been observed to hang Materials.Import() indefinitely instead of
#  erroring — always include Metadata even for a single hand-authored material)

body = model.Geometry.Children[0].Children[0]
geobody = body.GetGeoBody()  # MaterialAssignment.Location needs the low-level
                              # IGeoEntity, not the Body wrapper directly

sel = app.ExtAPI.SelectionManager.CreateSelectionInfo(
    SelectionTypeEnum.GeometryEntities
)  # from Ansys.ACT.Interfaces.Common import SelectionTypeEnum
sel.Entities = [geobody]

ma = mats.AddMaterialAssignment()
ma.Material = "DC03 (EN10130, nominal)"  # must match a name already in Engineering
                                          # Data — setting an unknown name throws
                                          # COMException 0x80004005 (E_FAIL)
ma.Location = sel

mesh = model.Mesh
mesh.ElementSize = 5e-3  # meters, or the unit the active unit system uses — verify
mesh.GenerateMesh()

static = model.AddStaticStructuralAnalysis()
support = static.AddFixedSupport()
support.Location = model.Geometry.Children[0].Faces[0]  # or a named selection

load = static.AddForce()
load.Location = model.Geometry.Children[0].Faces[1]
load.DefineBy = "Components"
load.XComponent.Output.SetDiscreteValue(0, 1000)  # verify units before trusting this number

static.Solve()

stress = static.Solution.AddEquivalentStress()
stress.EvaluateAllResults()
```

Every one of `.Material`, `.ElementSize`, load component values, and result
objects above should be treated as a template shape, not literal values —
adapt names/locations to the actual model and always confirm named selections
exist before referencing them by name.

## Multi-body geometry import (applies to any analysis type)

Importing two separate STEP files (e.g. a target part plus a separate
impactor/tooling body) via two `AddGeometryImport()` calls produces two
entries under `model.Geometry.Children`, each with its own body underneath —
`model.Geometry.Children[0].Children[0]` and `[1].Children[0]`. `Body`/
`GeoBodyWrapper` objects have **no** `.BoundingBox`/`.MinX`/`.MinY`-style
convenience property; compute extents or centroids yourself by iterating
`body.GetGeoBody().Vertices` and reducing over `.X`/`.Y`/`.Z`. Always print
each body's real extent before assuming two bodies are positioned/oriented
the way a script intended — a silent few-mm gap or an inverted axis is easy
to introduce when geometry comes from two independently-authored STEP files.

## `MaterialAssignment.Location` needs the low-level geometry entity

`ma.Location = <SelectionInfo with Entities=[some_body_wrapper]>` throws
`InvalidCastException: ... Body value cannot be converted to
Ansys.ACT.Interfaces.Geometry.IGeoEntity` if you pass the `Body`
automation-wrapper object directly. Always call `body.GetGeoBody()` first and
put *that* into `Entities` — this applies to any `SelectionInfo.Entities`
assignment (material assignment, fixed supports, loads, contact scoping),
not just materials.

## Mesh element order for the type of analysis you're running

`mesh.ElementOrder` defaults to `ProgramControlled`. That's fine for most
static-structural work, but some analysis types (Explicit Dynamics — see
`explicit-dynamics-impact.md`) require a specific order and will fail late,
during solve setup rather than at mesh-generation time, if left on
`ProgramControlled`. Set it explicitly (`ElementOrder.Linear` /
`.Quadratic`) whenever the analysis type has a known requirement, and
generate the mesh only after that's set.

## Equivalent APDL command-block shape (PyMAPDL)

For engineers who think in classic APDL, PyMAPDL exposes the same command
verbs as method calls:

```python
from ansys.mapdl.core import launch_mapdl

mapdl = launch_mapdl()
try:
    mapdl.prep7()
    mapdl.et(1, "SOLID186")
    mapdl.mp("EX", 1, 2e11)   # Pa — confirm unit system
    mapdl.mp("PRXY", 1, 0.3)
    mapdl.cdread("db", "geometry.cdb")  # or build geometry directly
    mapdl.esize(5e-3)
    mapdl.vmesh("ALL")

    mapdl.slashsolu()
    mapdl.antype("STATIC")
    mapdl.d("FIXED_SUPPORT_NODES", "ALL", 0)
    mapdl.f("LOAD_NODES", "FX", 1000)
    mapdl.solve()
    mapdl.finish()

    mapdl.post1()
    mapdl.set(1, 1)
    result = mapdl.post_processing.nodal_eqv_stress()
finally:
    mapdl.exit()
```

Named node/element groups referenced above (`"FIXED_SUPPORT_NODES"`,
`"LOAD_NODES"`) must be defined via `mapdl.nsel`/component grouping
(`mapdl.cm`) before use — do not invent selection names that were never
created.

## Mesh quality checks to run before trusting results

Report these alongside any static structural result:

- Element and node count.
- Worst element skewness / aspect ratio (PyMechanical: `mesh.MeshMetricType`
  + `mesh.MeshMetricMinimum/Maximum/Average`; PyMAPDL: `mapdl.get(...)` mesh
  quality items, or the classic `CHECK` command output).
- Whether the solve converged without warnings — treat any solver warning as
  something to surface, not to suppress.

## Unit system check

`model.Project` does not exist on the embedded `App`'s `Model` object
(`AttributeError: 'Model' object has no attribute 'Project'`) — that call
looks plausible by analogy to the GUI but is not a real API. Read the active
unit system from the application object instead:

```python
app.ExtAPI.Application.ActiveUnitSystem
```

State the active unit system explicitly whenever a load magnitude, material
property, or result value is reported. A result off by exactly 1000x is a
strong signal of an mm/m mismatch — see `troubleshooting.md`.
