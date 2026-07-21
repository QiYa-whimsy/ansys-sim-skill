#!/usr/bin/env python3
"""Batch parameter-sweep orchestrator for PyAnsys template scripts.

This tool is analysis-agnostic: it does not contain any PyMechanical/PyMAPDL
logic itself. It runs a user/Claude-authored template script once per row of
a parameter table, each as an isolated subprocess (so every case gets a clean
interpreter and license handshake with no state bleed between runs).

Template contract:
  - accepts each parameter column as a --<column_name> <value> CLI flag,
  - opens and closes its own ANSYS session,
  - prints exactly one JSON object as the LAST line of stdout, containing at
    least a "case_id" field plus whatever result fields it extracted.

`plan` never opens an ANSYS session. `run` requires --execute.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any


class SweepError(RuntimeError):
    """Expected, user-facing error for this tool."""


def load_params(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise SweepError(f"params file not found: {path}")

    suffix = path.suffix.lower()
    if suffix in (".yaml", ".yml"):
        try:
            import yaml
        except ImportError:
            raise SweepError("pyyaml is required to read .yaml/.yml params files")
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        if not isinstance(data, list):
            raise SweepError("YAML params file must be a list of case dicts")
        rows = [{str(k): str(v) for k, v in row.items()} for row in data]
    elif suffix == ".csv":
        with path.open("r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            rows = [dict(row) for row in reader]
    else:
        raise SweepError(f"unsupported params file type: {suffix} (use .csv or .yaml)")

    if not rows:
        raise SweepError("params file contained no rows")

    for i, row in enumerate(rows):
        if "case_id" not in row or not row["case_id"]:
            row["case_id"] = f"case_{i + 1:03d}"

    return rows


def build_template_args(template: Path, row: dict[str, str]) -> list[str]:
    args = [sys.executable, str(template)]
    for key, value in row.items():
        args.append(f"--{key}")
        args.append(str(value))
    return args


def cmd_plan(args: argparse.Namespace) -> int:
    rows = load_params(Path(args.params))
    template = Path(args.template)
    if not template.exists():
        raise SweepError(f"template script not found: {template}")

    print(f"Template: {template}")
    print(f"Case count: {len(rows)}")
    for row in rows:
        print(f"  - {row['case_id']}: " + ", ".join(f"{k}={v}" for k, v in row.items() if k != "case_id"))
    print("\nNo ANSYS session opened. Re-run with 'run --execute' to solve these cases.")
    return 0


def run_one_case(template: Path, row: dict[str, str]) -> dict[str, Any]:
    case_id = row["case_id"]
    cmd = build_template_args(template, row)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except Exception as exc:  # noqa: BLE001
        return {"case_id": case_id, "status": "error", "error": f"failed to launch: {exc}"}

    stdout_lines = [line for line in proc.stdout.splitlines() if line.strip()]
    if proc.returncode != 0:
        return {
            "case_id": case_id,
            "status": "error",
            "error": f"exit code {proc.returncode}",
            "stderr": proc.stderr[-2000:],
        }
    if not stdout_lines:
        return {"case_id": case_id, "status": "error", "error": "template printed no output"}

    last_line = stdout_lines[-1]
    try:
        result = json.loads(last_line)
    except json.JSONDecodeError as exc:
        return {
            "case_id": case_id,
            "status": "error",
            "error": f"last stdout line was not valid JSON: {exc}",
            "raw_last_line": last_line,
        }

    result.setdefault("case_id", case_id)
    result["status"] = "ok"
    return result


def cmd_run(args: argparse.Namespace) -> int:
    if not args.execute:
        raise SweepError("run requires --execute to open real ANSYS sessions; use 'plan' to preview")

    rows = load_params(Path(args.params))
    template = Path(args.template)
    if not template.exists():
        raise SweepError(f"template script not found: {template}")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "manifest.csv"

    print(f"Running {len(rows)} case(s) with max_parallel={args.max_parallel} ...")
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, args.max_parallel)) as pool:
        futures = {pool.submit(run_one_case, template, row): row["case_id"] for row in rows}
        for future in as_completed(futures):
            case_id = futures[future]
            result = future.result()
            results.append(result)
            print(f"  [{result.get('status', 'unknown')}] {case_id}")

    fieldnames: list[str] = []
    for result in results:
        for key in result:
            if key not in fieldnames:
                fieldnames.append(key)

    with manifest_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for result in results:
            writer.writerow(result)

    ok_count = sum(1 for r in results if r.get("status") == "ok")
    print(f"\n{ok_count}/{len(results)} case(s) succeeded. Manifest written to {manifest_path}")
    return 0 if ok_count == len(results) else 1


def cmd_status(args: argparse.Namespace) -> int:
    manifest_path = Path(args.out_dir) / "manifest.csv"
    if not manifest_path.exists():
        raise SweepError(f"no manifest found at {manifest_path}")

    with manifest_path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)

    ok = [r for r in rows if r.get("status") == "ok"]
    failed = [r for r in rows if r.get("status") != "ok"]
    print(f"Total: {len(rows)}  OK: {len(ok)}  Failed: {len(failed)}")
    for row in failed:
        print(f"  FAILED {row.get('case_id')}: {row.get('error', 'unknown error')}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Batch parameter-sweep orchestrator for PyAnsys templates.")
    sub = parser.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan", help="Preview the case matrix without opening any ANSYS session")
    plan.add_argument("--params", required=True, help="Path to params.csv or params.yaml")
    plan.add_argument("--template", required=True, help="Path to the per-case PyAnsys template script")
    plan.set_defaults(func=cmd_plan)

    run = sub.add_parser("run", help="Execute the sweep (requires --execute)")
    run.add_argument("--params", required=True, help="Path to params.csv or params.yaml")
    run.add_argument("--template", required=True, help="Path to the per-case PyAnsys template script")
    run.add_argument("--out-dir", default="runs", help="Directory to write manifest.csv into")
    run.add_argument("--max-parallel", type=int, default=1, help="Max concurrent cases (bounded by license seats)")
    run.add_argument("--execute", action="store_true", help="Required to actually run cases")
    run.set_defaults(func=cmd_run)

    status = sub.add_parser("status", help="Summarize an existing manifest")
    status.add_argument("--out-dir", default="runs", help="Directory containing manifest.csv")
    status.set_defaults(func=cmd_status)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except SweepError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
