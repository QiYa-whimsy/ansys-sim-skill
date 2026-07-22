# Explicit Dynamics (drop tests, impact tests)

Read this file when building or debugging an Explicit Dynamics (AUTODYN
solver) PyMechanical script for a drop test, impact test, or other short-
duration high-rate event.

A real Explicit Dynamics solve on a moderate 3D shell+impactor mesh
(tens of thousands of elements) commonly runs for **1-3 hours of wall-clock/
license time**, not minutes. Treat every full-duration solve as an expensive,
hard-to-cancel-cleanly operation — this file exists because a wrong setup
that still "solves successfully" with all-zero results is easy to produce and
expensive to discover late. Always run the preflight check in this file
before committing to a full solve.

## Object-model shape

```python
ed = model.AddExplicitDynamicsAnalysis()

mesh = model.Mesh
mesh.ElementSize = Quantity(5.0, "mm")
mesh.ElementOrder = ElementOrder.Linear  # REQUIRED -- see "Element order" below
mesh.GenerateMesh()

conns = model.Connections
bi = conns.AddBodyInteraction()   # NOT conns.AddContactRegion() -- that's the
                                   # static-structural/implicit contact object
                                   # and is not the right one for Explicit
                                   # Dynamics.
bi.Location = sel_both             # SelectionInfo scoped to BOTH bodies
bi.ContactType = ContactType.Frictional   # default is Frictionless -- state
bi.FrictionCoefficient = 0.2              # explicitly which one is in effect

fs = ed.AddFixedSupport()
fs.Location = sel_mount_edges

vel = ed.AddVelocity()
vel.Location = sel_impactor
# See "Setting a Velocity load" below -- do not assign vel.XComponent directly.

asettings = ed.AnalysisSettings
asettings.NumberOfSteps = 1
asettings.SetStepEndTime(1, Quantity(END_TIME_S, "sec"))
# EXDAnalysisSettings has no .Steps / .StepEndTime property -- use
# SetStepEndTime(step_index, Quantity)/GetStepEndTime(step_index).

ed.Solve(True)
```

## Element order: force Linear

Explicit Dynamics/AUTODYN requires linear (no midside-node) elements.
`mesh.ElementOrder` defaults to `ProgramControlled`, which can select
quadratic elements depending on the mesh — this produces a real solver
failure late in the pre-solve stage (`Too many nodes per element. Error
reading in the CAERep from Simulation. Failed.`), after mesh generation
already succeeded and looked fine. Set it explicitly every time:

```python
from Ansys.Mechanical.DataModel.Enums import ElementOrder
mesh.ElementOrder = ElementOrder.Linear
```

## Rigid-body impactor

If the impactor is a stand-in proxy (not a real, deformable test object),
mark it rigid rather than meshing it as a flexible body:

```python
impactor_body.StiffnessBehavior = StiffnessBehavior.Rigid
```

Then assign a density-tuned material to hit a target mass if the real
impactor mass is known/assumed — check `impactor_body.Mass` after material
assignment to confirm it landed on the intended value (density is often
easier to tune than an exact volume match).

**State the impactor's contact geometry in the report, not just its mass.**
Mass alone does not determine contact area or local stress/dent
concentration — a sphere/hemisphere radius, flat punch diameter, or edge
profile does. If the real impactor is a stand-in proxy rather than a
standard test-spec geometry (e.g. a fixed-diameter steel ball called out by
an impact-test standard), say so explicitly, and confirm whether the chosen
shape/size roughly matches the applicable standard's impactor — this is a
report-writing gap, not a solve gap, but it reads to a reviewer as "geometry
undefined" if left out.

## Transient peak deformation vs. permanent residual set

`TotalDeformation.Maximum` from a solve that ends shortly after peak contact
is the **instantaneous elastic+plastic deformation at that time step**, not
the permanent dent/residual set left after the impactor rebounds and elastic
strain recovers. Reporting the peak number as "the dent depth" overstates it
whenever there's meaningful elastic recovery — which is the normal case for
a short, low-plastic-strain impact.

To report a permanent residual deformation:
- Extend `END_TIME_S` well past the initial contact pulse so the impactor
  fully separates and the shell's elastic ringing has time to settle, and
  read the deformation once it stabilizes rather than at the raw solve-end
  step; or
- Map the Explicit Dynamics end state into a linked static structural
  (implicit) "unload" step and read the residual deformation with all
  contact/velocity loads removed.

State explicitly in the report which of these was done — or, if neither was
done, state plainly that the reported maximum is a transient peak, not a
predicted permanent dent depth.

## Setting a Velocity load (do not assign the component properties directly)

`vel.XComponent = <anything>` raises `TypeError: property is read-only`, and
`vel.XComponent.Output.SetDiscreteValue(0, value)` raises either a wrong-
overload `TypeError` (a bare Python float doesn't auto-convert to
`Quantity`) or a `NullReferenceException` even when a `Quantity` is passed
correctly, because the `Field`/`Variable` object underneath isn't ready to
accept a single discrete-value write that way. The pattern that actually
works is assigning a **list** to `.Output.DiscreteValues`:

```python
unit_str = str(vel.ZComponent.Output.Unit)   # read the load's own unit, don't assume
vel.XComponent.Output.DiscreteValues = [Quantity(0.0, unit_str)]
vel.YComponent.Output.DiscreteValues = [Quantity(0.0, unit_str)]
vel.ZComponent.Output.DiscreteValues = [Quantity(v_mm_s, unit_str)]
```

## The single most expensive mistake in this domain: velocity direction

A `Velocity` load pointed away from (or tangent to) the target body is a
**silent, "successful" failure**: `ed.Solve(True)` completes, `Solution.
ObjectState` reports `Solved`, `Solution.Status` reports `Done`, and every
result object evaluates cleanly to `Maximum = 0`, `Minimum = 0` across
deformation, stress, and strain — because the impactor genuinely never
touched the target. Nothing in the object model raises an error or a
warning for this. It reads exactly like a valid "no significant response"
result unless you know to be suspicious of an all-zero outcome after a
multi-hour real solve.

This happened in this project: the initial `Velocity` was set toward `-Z`
based on a stale assumption about geometry orientation, while the impactor's
actual bounding box sat *below* the shell's bottom face along Z — the
impactor needed to travel `+Z` to close that ~1mm gap and strike the target.
Two full-duration solves (each well over an hour of real license/compute
time) ran to a clean "Done" with all-zero results before the direction bug
was found.

**Always run this check before a full-duration solve**, and treat it as
non-optional whenever the impactor and target were positioned/oriented by
script rather than hand-verified in the GUI:

```python
def centroid(geo):
    xs, ys, zs = [], [], []
    for v in geo.Vertices:
        xs.append(v.X); ys.append(v.Y); zs.append(v.Z)
    return (sum(xs) / len(xs), sum(ys) / len(ys), sum(zs) / len(zs))

shell_c = centroid(shell_body.GetGeoBody())
imp_c = centroid(impactor_body.GetGeoBody())
to_target = tuple(s - i for s, i in zip(shell_c, imp_c))
mag = sum(c ** 2 for c in to_target) ** 0.5
to_target_unit = tuple(c / mag for c in to_target)

dot = sum(a * b for a, b in zip(VELOCITY_DIR, to_target_unit))
assert dot > 0.05, (
    f"Velocity direction {VELOCITY_DIR} does not point toward the target "
    f"(dot={dot:.4f}). Fix the Velocity load before solving."
)
```

`scripts/preflight_check.py direction` runs exactly this check as a
standalone CLI command against the real STEP files, before any mesh/BC/solve
work — it only imports geometry (seconds of license time), so run it before
every full solve on a new or edited setup. Note that `Body`/`GeoBodyWrapper`
objects have no `.BoundingBox`/`.MinX`-style property directly; compute
extents/centroids by iterating `.Vertices`, as above.

## Pilot solve: catch "no contact" even earlier than a full run

The direction check above only catches a purely geometric misalignment. A
correctly-aimed impactor can still fail to make contact for other reasons
(gap too large for the mesh/contact detection settings, wrong body pair
scoped into `BodyInteraction`, timestep too coarse to catch a fast impactor
before the step ends). Before committing to the full `END_TIME_S`, solve a
short pilot at a small fraction of it (for example 2-5%) and check that
`BodyInteraction`'s contact tracker or the solved deformation/stress fields
are already showing a nonzero response:

```python
PILOT_TIME_S = END_TIME_S * 0.05
asettings.SetStepEndTime(1, Quantity(PILOT_TIME_S, "sec"))
ed.Solve(True)
td.EvaluateAllResults()
assert td.Maximum > 0, "Pilot solve shows no contact yet -- do not proceed to the full run."
```

Structure the real pipeline script so `END_TIME_S` can be overridden from
the command line or an environment variable, so the exact same script serves
as both the pilot run and the full run without hand-editing constants between
them.

## Result evaluation

Result objects (`TotalDeformation`, `EquivalentStress`,
`EquivalentPlasticStrain`, ...) read `Maximum`/`Minimum` as `0` until you
call `.EvaluateAllResults()` — either on each result object, or once on
`Solution` via `sol.EvaluateAllResults()`. Do this immediately after
`Solve()` returns and before reporting any number.

`Solution.Children` also includes a `SolutionInformation` object — it has no
`Maximum`/`Minimum`/`Status` properties; don't iterate `Solution.Children`
and treat every entry as a result object interchangeably. Its `.Text`
property does hold the raw solver log tail, useful for debugging a solve
failure (see `troubleshooting.md`).

A benign, ignorable warning that shows up around material import and
sometimes around solve on this stack: `Warning at File: myxml, line 1, col
40, encoding 'utf-16' from XML declaration or manually set contradicts the
auto-sensed encoding; ignoring` — this is not a sign of a broken material or
a failed solve.

## Mesh defeaturing / far-field coarsening: prefer a uniform size

Trying to keep a fine mesh only at the impact zone and coarsen/suppress
detail everywhere else (via a `FeatureSuppress` mesh control scoped to a
`NamedSelection` of "far" faces) repeatedly failed in this project with
`网格控制没有关联到任何几何结构` ("the mesh control isn't associated with
any geometry") across several different scoping attempts (raw face list,
`NamedSelection` by name, `NamedSelection` by ID list). None of the variants
tried got a `FeatureSuppress` control past `UnderDefined`. Given a
uniform-size mesh solved successfully and fast enough for this project's
geometry, the pragmatic default is: **start with one global `ElementSize`
covering the whole part**, and only invest in local sizing/defeaturing
controls if the resulting node/element count is actually too large to solve
in reasonable time — don't spend debugging time on defeaturing controls
preemptively.
