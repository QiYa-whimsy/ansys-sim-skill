#!/usr/bin/env python3
"""Environment, license, and orphaned-session diagnostics for PyAnsys work.

Default behavior is read-only. Killing orphaned processes or attempting a
real license checkout both require --execute.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from typing import Any

PROCESS_NAME_HINTS = (
    "ansys",
    "aisol",
    "mechanical",
    "mapdl",
    "ansyscl",
    "cadoedoc",
    "rmwmgr",
)

LICENSE_ENV_VARS = (
    "ANSYSLMD_LICENSE_FILE",
    "ANSYS_LICENSE_FILE",
    "LM_LICENSE_FILE",
)


class SessionCheckError(RuntimeError):
    """Expected, user-facing error for this tool."""


@dataclass
class ProcessInfo:
    pid: int
    name: str
    cmdline: str


def find_awp_root_env() -> dict[str, str]:
    """Fallback discovery via AWP_ROOT<NNN> env vars, independent of any PyAnsys package."""
    found = {}
    for name, value in os.environ.items():
        if name.startswith("AWP_ROOT") and value:
            version = name[len("AWP_ROOT"):]
            found[version] = value
    return found


def find_ansys_installations() -> dict[str, Any]:
    result: dict[str, Any] = {
        "via_ansys_tools_path": {},
        "ansys_tools_path_importable": False,
        "via_awp_root_env": find_awp_root_env(),
    }
    try:
        from ansys.tools.path import get_available_ansys_installations
    except ImportError:
        return result
    result["ansys_tools_path_importable"] = True
    try:
        installs = get_available_ansys_installations()
    except Exception as exc:  # noqa: BLE001
        result["ansys_tools_path_error"] = str(exc)
        return result
    result["via_ansys_tools_path"] = {str(version): str(path) for version, path in installs.items()}
    return result


PYANSYS_PACKAGES = ("ansys.mechanical.core", "ansys.mapdl.core", "ansys.dpf.post")


def find_pyansys_packages() -> dict[str, bool]:
    import importlib.util

    result = {}
    for pkg in PYANSYS_PACKAGES:
        try:
            result[pkg] = importlib.util.find_spec(pkg) is not None
        except ModuleNotFoundError:
            result[pkg] = False
    return result


def find_license_env() -> dict[str, str]:
    found = {}
    for name in LICENSE_ENV_VARS:
        value = os.environ.get(name)
        if value:
            found[name] = value
    return found


def find_candidate_processes() -> list[ProcessInfo]:
    try:
        import psutil
    except ImportError:
        raise SessionCheckError(
            "psutil is required for process inspection. Install it with "
            "'pip install psutil' or run with --skip-processes."
        )

    own_pid = os.getpid()
    candidates: list[ProcessInfo] = []
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            info = proc.info
            if info["pid"] == own_pid:
                continue
            name = (info.get("name") or "").lower()
            cmdline_list = info.get("cmdline") or []
            cmdline = " ".join(cmdline_list).lower()
            haystack = f"{name} {cmdline}"
            if any(hint in haystack for hint in PROCESS_NAME_HINTS):
                candidates.append(
                    ProcessInfo(
                        pid=info["pid"],
                        name=info.get("name") or "",
                        cmdline=" ".join(cmdline_list),
                    )
                )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return candidates


def attempt_launch_test() -> dict[str, Any]:
    result: dict[str, Any] = {"attempted": True, "success": False, "error": None}
    try:
        from ansys.mapdl.core import launch_mapdl
    except ImportError:
        result["error"] = "ansys-mapdl-core is not installed"
        return result

    mapdl = None
    try:
        mapdl = launch_mapdl(mode="grpc")
        result["success"] = True
        result["version"] = getattr(mapdl, "version", None)
    except Exception as exc:  # noqa: BLE001 - report any launch failure verbatim
        result["error"] = str(exc)
    finally:
        if mapdl is not None:
            try:
                mapdl.exit()
            except Exception:
                pass
    return result


def cmd_check(args: argparse.Namespace) -> int:
    report: dict[str, Any] = {
        "ansys_installations": find_ansys_installations(),
        "pyansys_packages_installed": find_pyansys_packages(),
        "license_env": find_license_env(),
    }

    if args.skip_processes:
        report["candidate_processes"] = []
        report["candidate_processes_skipped"] = True
    else:
        try:
            processes = find_candidate_processes()
        except SessionCheckError as exc:
            report["candidate_processes"] = []
            report["candidate_processes_error"] = str(exc)
        else:
            report["candidate_processes"] = [asdict(p) for p in processes]

    if args.launch_test:
        if not args.execute:
            raise SessionCheckError("--launch-test requires --execute (it checks out a real license seat)")
        report["launch_test"] = attempt_launch_test()

    if args.kill_orphans:
        if not args.execute:
            raise SessionCheckError("--kill-orphans requires --execute")
        killed = []
        errors = []
        try:
            import psutil
        except ImportError:
            raise SessionCheckError("psutil is required to kill processes")
        for proc_info in report.get("candidate_processes", []):
            pid = proc_info["pid"]
            try:
                psutil.Process(pid).terminate()
                killed.append(pid)
            except Exception as exc:  # noqa: BLE001
                errors.append({"pid": pid, "error": str(exc)})
        report["killed_pids"] = killed
        report["kill_errors"] = errors

    print(json.dumps(report, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Diagnose ANSYS installation, licensing, and orphaned sessions."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="Report installs, license env, and candidate processes")
    check.add_argument(
        "--skip-processes", action="store_true", help="Skip process inspection (no psutil dependency)"
    )
    check.add_argument(
        "--launch-test",
        action="store_true",
        help="Attempt a real short-lived MAPDL launch to confirm a seat is checkoutable (consumes a seat)",
    )
    check.add_argument(
        "--kill-orphans",
        action="store_true",
        help="Terminate processes reported as candidate orphans",
    )
    check.add_argument(
        "--execute",
        action="store_true",
        help="Required to actually perform --launch-test or --kill-orphans",
    )
    check.set_defaults(func=cmd_check)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except SessionCheckError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
