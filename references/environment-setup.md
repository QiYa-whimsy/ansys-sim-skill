# Environment setup and licensing

Read this file when setting up or debugging the Mechanical/MAPDL Python
connection, choosing a launch mode, or diagnosing ANSYS licensing.

## Discovering installations

```python
from ansys.tools.path import get_available_ansys_installations
get_available_ansys_installations()  # {version_int: install_path, ...}
```

On Windows, installs are also discoverable via `AWP_ROOT<ver>` environment
variables (e.g. `AWP_ROOT251` for 2025 R1). When multiple versions are
installed, pin the exact one the user's model was built with — do not let
PyAnsys silently pick "latest" for anything other than throwaway scratch work.

## Licensing

- `ANSYSLMD_LICENSE_FILE` (or `ANSYS_LICENSE_FILE` on some setups) points at
  the license server (`port@host` or a local license file). Confirm it's set
  before assuming a license failure is a script bug.
- Every launched session (embedded `App`, gRPC `Mechanical`/`Mapdl` server)
  checks out a seat for its lifetime. Concurrent sweep runs each hold a
  separate seat — never set sweep concurrency above the seats actually
  available (see `fatigue-and-sweeps.md`).
- `scripts/session_check.py check` reports install versions, whether the
  license env var is present, and lists locally running processes that look
  like they may be holding a seat.

## Connection modes

**Embedded / in-process** — best for interactive scripting, Jupyter, or a
single dev-loop iteration:

```python
from ansys.mechanical.core import App
app = App()
try:
    ...
finally:
    app.close()
```

```python
from ansys.mapdl.core import launch_mapdl
mapdl = launch_mapdl()
try:
    ...
finally:
    mapdl.exit()
```

**gRPC server / separate process** — best for headless, CI, or batch sweep
runs, since each subprocess gets an isolated session with no state bleed
between runs:

```python
from ansys.mechanical.core import launch_mechanical
mechanical = launch_mechanical(batch=True)  # batch=True: no GUI
try:
    ...
finally:
    mechanical.exit()
```

```python
from ansys.mapdl.core import launch_mapdl
mapdl = launch_mapdl(mode="grpc")
try:
    ...
finally:
    mapdl.exit()
```

`sweep_runner.py` runs each parameter row as its own subprocess for exactly
this reason — pick the gRPC/batch launch mode inside the per-case template
script so each subprocess owns a clean session.

## Headless / Linux gotchas

- Without a display, avoid launching Mechanical in GUI mode; use
  `launch_mechanical(batch=True)` or MAPDL's default headless gRPC mode.
- If a session hangs on launch with no error, check firewall/port
  availability for the gRPC port before assuming a script bug —
  `troubleshooting.md` has the specific symptoms.

## Mandatory cleanup pattern

Always wrap session use in `try/finally` (or a context manager where the
library provides one) so a mid-script exception still releases the license
seat:

```python
app = App()
try:
    # ... build, mesh, solve, extract ...
    pass
finally:
    app.close()
```
