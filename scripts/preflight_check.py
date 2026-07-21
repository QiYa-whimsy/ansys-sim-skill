#!/usr/bin/env python3
"""Cheap, pre-solve sanity checks for contact/impact-style analyses
(Explicit Dynamics drop/impact tests, or any analysis where a moving body
must reach a target).

Both subcommands open a real embedded Mechanical session and import real
geometry (seconds of license time), but neither generates a mesh or runs a
real solve — they exist specifically to catch the class of mistake that is
otherwise only visible after a full multi-hour solve completes "successfully"
with an all-zero result (see references/explicit-dynamics-impact.md and
references/troubleshooting.md, "All-zero results after a successful solve").

Commands:
  direction  Import two STEP bodies (target + moving body) and check whether
             a configured velocity direction actually points from the mover
             toward the target. No mesh, no solve. Seconds of license time.
  pilot      Run everything through mesh + BC + a SHORT step end time (a
             fraction of the real one) and confirm the result fields are
             already nonzero before you commit to the full duration. This
             does consume real solve/license time, but a small fraction of
             the full run.

Usage:
    python scripts/preflight_check.py direction --target part.stp --mover impactor.stp --velocity 0 0 1
    python scripts/preflight_check.py pilot --template run_case.py --pilot-fraction 0.05

`pilot` is analysis-agnostic like sweep_runner.py: it invokes your own
pipeline script as a subprocess with an extra --end-time-s override, on the
contract that the script accepts that flag and prints "RESULT <name>:
Maximum = <value> [<unit>]" lines to stdout (the same shape solve_run.py
already prints). It does not contain PyMechanical logic itself.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


class PreflightError(RuntimeError):
    """Expected, user-facing error for this tool."""


def cmd_direction(args: argparse.Namespace) -> int:
    from ansys.mechanical.core import App

    target_path = Path(args.target)
    mover_path = Path(args.mover)
    if not target_path.exists():
        raise PreflightError(f"target STEP not found: {target_path}")
    if not mover_path.exists():
        raise PreflightError(f"mover STEP not found: {mover_path}")

    velocity_dir = tuple(args.velocity)
    mag = sum(c ** 2 for c in velocity_dir) ** 0.5
    if mag == 0:
        raise PreflightError("--velocity must be a nonzero direction vector")
    velocity_unit = tuple(c / mag for c in velocity_dir)

    app = App()
    try:
        model = app.Model
        gi1 = model.GeometryImportGroup.AddGeometryImport()
        gi1.Import(str(target_path))
        gi2 = model.GeometryImportGroup.AddGeometryImport()
        gi2.Import(str(mover_path))

        target_body = model.Geometry.Children[0].Children[0]
        mover_body = model.Geometry.Children[1].Children[0]

        def centroid(body):
            xs, ys, zs = [], [], []
            for v in body.GetGeoBody().Vertices:
                xs.append(v.X)
                ys.append(v.Y)
                zs.append(v.Z)
            return (sum(xs) / len(xs), sum(ys) / len(ys), sum(zs) / len(zs))

        target_c = centroid(target_body)
        mover_c = centroid(mover_body)

        to_target = tuple(t - m for t, m in zip(target_c, mover_c))
        to_target_mag = sum(c ** 2 for c in to_target) ** 0.5
        if to_target_mag == 0:
            raise PreflightError("target and mover centroids coincide -- cannot judge direction")
        to_target_unit = tuple(c / to_target_mag for c in to_target)

        dot = sum(a * b for a, b in zip(velocity_unit, to_target_unit))

        print(f"Mover centroid:  {mover_c}")
        print(f"Target centroid: {target_c}")
        print(f"Direction mover->target (unit): {to_target_unit}")
        print(f"Configured velocity direction (unit): {velocity_unit}")
        print(f"Dot product: {dot:.4f}")

        if dot <= args.min_dot:
            print(
                f"PREFLIGHT FAIL: velocity does not point toward the target "
                f"(dot={dot:.4f} <= {args.min_dot}). The mover will fly away or "
                f"pass tangent to the target. Fix the velocity direction before "
                f"spending solve time."
            )
            return 1

        print(f"PREFLIGHT PASS: velocity points toward the target (dot={dot:.4f} > {args.min_dot}).")
        return 0
    finally:
        app.close()


RESULT_LINE_RE = re.compile(
    r"^RESULT\s+(\S+):\s+Maximum\s*=\s*([-\d.eE]+)\s*\[.*?\]\s+Minimum\s*=\s*([-\d.eE]+)\s*\[.*?\]"
)


def cmd_pilot(args: argparse.Namespace) -> int:
    template_path = Path(args.template)
    if not template_path.exists():
        raise PreflightError(f"template script not found: {template_path}")
    if not (0 < args.pilot_fraction < 1):
        raise PreflightError("--pilot-fraction must be between 0 and 1")

    pilot_end_time = args.full_end_time_s * args.pilot_fraction
    print(
        f"Running pilot solve at {pilot_end_time:.6g}s "
        f"({args.pilot_fraction:.0%} of the full {args.full_end_time_s:.6g}s) "
        f"via {template_path} --end-time-s {pilot_end_time:.6g} ..."
    )

    proc = subprocess.run(
        [sys.executable, str(template_path), "--end-time-s", str(pilot_end_time)],
        capture_output=True,
        text=True,
    )
    print(proc.stdout)
    if proc.stderr:
        print(proc.stderr, file=sys.stderr)

    if proc.returncode != 0:
        raise PreflightError(f"pilot solve subprocess exited with code {proc.returncode}")

    results = {}
    for line in proc.stdout.splitlines():
        m = RESULT_LINE_RE.match(line.strip())
        if m:
            name, maximum, minimum = m.groups()
            results[name] = (float(maximum), float(minimum))

    if not results:
        raise PreflightError(
            "no 'RESULT <name>: Maximum = ... Minimum = ...' lines found in pilot "
            "output -- template script must print results in that shape"
        )

    print("Pilot results:", results)

    nonzero = {name: vals for name, vals in results.items() if vals[0] != 0 or vals[1] != 0}
    if not nonzero:
        print(
            "PREFLIGHT FAIL: all extracted results are exactly zero after the pilot "
            "solve. Contact/response has not registered yet -- do NOT proceed to "
            "the full-duration solve without investigating (check contact scoping, "
            "velocity direction/magnitude, initial gap, and pilot duration)."
        )
        return 1

    print(f"PREFLIGHT PASS: nonzero response detected in {list(nonzero)}. Safe to proceed to the full solve.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Pre-solve sanity checks for contact/impact analyses."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    direction = sub.add_parser(
        "direction", help="Check whether a configured velocity direction points toward the target body"
    )
    direction.add_argument("--target", required=True, help="Path to the target body STEP file")
    direction.add_argument("--mover", required=True, help="Path to the moving body (impactor) STEP file")
    direction.add_argument(
        "--velocity", nargs=3, type=float, required=True, metavar=("X", "Y", "Z"),
        help="Configured velocity direction, e.g. --velocity 0 0 1"
    )
    direction.add_argument(
        "--min-dot", type=float, default=0.05,
        help="Minimum acceptable dot(velocity_unit, mover->target_unit) to pass (default 0.05)"
    )
    direction.set_defaults(func=cmd_direction)

    pilot = sub.add_parser(
        "pilot", help="Run a short pilot solve via a template script and check for nonzero response"
    )
    pilot.add_argument("--template", required=True, help="Path to the real pipeline script (must accept --end-time-s)")
    pilot.add_argument("--full-end-time-s", type=float, required=True, help="The full/real analysis step end time in seconds")
    pilot.add_argument("--pilot-fraction", type=float, default=0.05, help="Fraction of --full-end-time-s to run as the pilot (default 0.05)")
    pilot.set_defaults(func=cmd_pilot)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except PreflightError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
