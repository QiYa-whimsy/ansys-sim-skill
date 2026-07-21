# Troubleshooting

Read this file when a PyAnsys call errors, hangs, times out, or a session or
process looks orphaned.

## License errors

Symptom: checkout failed, feature not found, or a launch call hangs then
times out with a license-related message.

- Confirm `ANSYSLMD_LICENSE_FILE` (or the equivalent env var for the site's
  license server) is set and reachable.
- Run `python scripts/session_check.py check` to see installed versions,
  whether the license env var is present, and any local processes that may
  already be holding a seat.
- If seats are exhausted by orphaned processes, use
  `session_check.py check --kill-orphans --execute` to terminate them, then
  retry.

## gRPC connection timeout or port in use

Symptom: `launch_mechanical`/`launch_mapdl` in gRPC mode hangs or raises a
connection error.

- Pass an explicit port and confirm nothing else is already bound to it.
- Check local firewall rules if the launch is to a remote/containerized
  target.
- Confirm the ANSYS version being launched matches an installation actually
  present (`get_available_ansys_installations()`).

## Embedded App crashing on a headless server

Symptom: `ansys.mechanical.core.App()` fails or crashes with no display
available.

- Switch to `launch_mechanical(batch=True)` (gRPC, no GUI) instead of the
  embedded `App` on headless/CI machines.
- For MAPDL, headless gRPC launch (`launch_mapdl(mode="grpc")`) does not need
  a display; the default GUI-free launch should work without changes.

## Non-convergence or solve failure

Before concluding the script is wrong, inspect the actual solver output:

- Was the failure a convergence failure (nonlinear iteration did not
  converge) or a setup failure (missing material property, unconnected
  contact, singular stiffness matrix from an unconstrained rigid body mode)?
- Under-constrained models (missing or incorrectly located supports) are a
  common cause of singular-matrix failures — verify every body has enough
  constraint to remove rigid-body motion.
- For nonlinear static/transient runs, check whether auto time-stepping
  bisected below the minimum time step before giving up — that's a
  convergence signal, not necessarily a script bug.

## Orphaned processes holding license seats

Symptom: license checkout fails even though no session is knowingly open.

- `session_check.py check` lists locally running Mechanical/MAPDL-adjacent
  processes.
- Confirm with the user before killing anything that might be another
  in-progress interactive session, then run
  `session_check.py check --kill-orphans --execute`.

## Unit-system mismatch symptoms

- A result exactly 1000x too large or too small usually indicates an mm/m
  mix-up between geometry, material properties, or load magnitude.
- A stress result that looks physically implausible (e.g. absurdly low or
  high compared to material yield) is worth an explicit unit-system check
  before trusting the number — see the unit check snippet in
  `static-structural.md`.

## All-zero results after a "successful" solve

Symptom: `Solution.ObjectState` is `Solved`, `Solution.Status` is `Done`, no
exception was raised anywhere, but every result object's `Maximum`/`Minimum`
evaluates to exactly `0` after `EvaluateAllResults()`.

This is **not** necessarily a script bug in the result-extraction code — it
is the expected output when the load/contact never actually acted on the
model (most commonly: an impact/contact analysis where the moving body never
touched the target — see the velocity-direction pitfall in
`explicit-dynamics-impact.md`). Before assuming the result objects are wrong:

- Confirm the load/BC that should be driving the response actually has
  `ObjectState == FullyDefined` and a nonzero magnitude in the direction you
  expect.
- For contact/impact analyses specifically, run the direction/pilot-solve
  preflight checks in `explicit-dynamics-impact.md` on a short duration
  before re-running the full solve — a full re-solve without first fixing the
  root cause just reproduces the same all-zero result after the same long
  wait.
- Don't accept "it solved without error" as proof of a meaningful result;
  a physically-inert setup solves cleanly too.

## Saving the project database

`app.save_as(path)` raises `FileExistsError` if `path` already exists — pass
`overwrite=True` explicitly on any re-save of a path used by a previous run,
rather than switching to a new path every time (which fragments the
deliverable across multiple `.mechdb` files). There is no `model.Project`
object on the embedded `App`'s `Model` — use `app.save_as(...)` /
`app.save(...)` directly on the `App` instance, not through `Model`.
