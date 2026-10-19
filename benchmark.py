"""Benchmark and verification suite for Assurance Expiry Engine (AEE).

Validates all 4 core scenarios, runs full test suite, performs honesty checks,
and scans for forbidden words and mandatory limitations statements.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import site
import subprocess
import sys
import tempfile
from pathlib import Path

from aee.report import LIMITATIONS_STATEMENT

USER_SCRIPTS = (
    Path(site.getuserbase())
    / f"Python{sys.version_info.major}{sys.version_info.minor}"
    / "Scripts"
)

SCENARIOS = [
    "01-clean",
    "02-expired-control",
    "03-stale-evidence",
    "04-shared-dependency",
]
EVAL_NOW = "2026-10-19T12:00:00Z"
FORBIDDEN_WORDS = ["noncompliant", "unsafe", "violation"]


def find_aee_executable() -> str:
    """Find the aee executable path or fall back to sys.executable -m aee."""
    if USER_SCRIPTS.exists():
        os.environ["PATH"] = str(USER_SCRIPTS) + os.pathsep + os.environ.get("PATH", "")
    aee_path = shutil.which("aee")
    if aee_path:
        return aee_path
    if (USER_SCRIPTS / "aee.exe").exists():
        return str(USER_SCRIPTS / "aee.exe")
    return "aee"


def run_scenarios(
    aee_bin: str,
    temp_dir: Path,
) -> tuple[bool, list[dict[str, str]], dict[str, str]]:
    """Run all 4 scenarios, evaluate findings and reports."""
    all_passed = True
    rows: list[dict[str, str]] = []
    generated_reports: dict[str, str] = {}

    for scen in SCENARIOS:
        scen_dir = Path("fixtures/scenarios") / scen
        model_file = scen_dir / "model.yaml"
        expected_file = scen_dir / "expected.json"

        expected = json.loads(expected_file.read_text(encoding="utf-8"))
        exp_exit = expected["exit_code"]
        exp_new_inv = expected["new_invalidations"]
        forbidden_list = expected.get("forbidden_substrings", FORBIDDEN_WORDS)

        findings_path = temp_dir / f"{scen}_findings.json"
        report_path = temp_dir / f"{scen}_report.md"
        history_path = temp_dir / f"{scen}_history.jsonl"

        # 1. Run aee check
        check_cmd = [
            aee_bin,
            "check",
            "--model",
            str(model_file),
            "--now",
            EVAL_NOW,
            "--output",
            str(findings_path),
        ]
        check_proc = subprocess.run(check_cmd, capture_output=True, text=True)
        actual_exit = check_proc.returncode

        # Read findings
        actual_inv = -1
        if findings_path.exists():
            try:
                findings_data = json.loads(findings_path.read_text(encoding="utf-8"))
                actual_inv = len(findings_data.get("invalidations", []))
            except Exception:
                actual_inv = -1

        # 2. Run aee report
        report_cmd = [
            aee_bin,
            "report",
            "--model",
            str(model_file),
            "--history",
            str(history_path),
            "--now",
            EVAL_NOW,
            "--output",
            str(report_path),
        ]
        report_proc = subprocess.run(report_cmd, capture_output=True, text=True)
        report_content = report_path.read_text(encoding="utf-8") if report_path.exists() else ""
        generated_reports[scen] = report_content

        # 3. Check forbidden substrings
        lower_report = report_content.lower()
        found_forbidden = [w for w in forbidden_list if w in lower_report]
        forbidden_str = ", ".join(found_forbidden) if found_forbidden else "None"

        # 4. Determine scenario result
        passed = (
            actual_exit == exp_exit
            and actual_inv == exp_new_inv
            and len(found_forbidden) == 0
            and report_proc.returncode == 0
        )
        if not passed:
            all_passed = False

        rows.append(
            {
                "Scenario": scen,
                "Expected": f"exit {exp_exit}",
                "Actual": f"exit {actual_exit}",
                "Claims invalidated": str(actual_inv),
                "Forbidden words?": forbidden_str,
                "Result": "PASS" if passed else "FAIL",
            }
        )

    return all_passed, rows, generated_reports


def print_table(rows: list[dict[str, str]]) -> None:
    """Print formatted ASCII table matching required header."""
    headers = ["Scenario", "Expected", "Actual", "Claims invalidated", "Forbidden words?", "Result"]
    col_widths = {h: max(len(h), max(len(r[h]) for r in rows)) for h in headers}

    header_line = " | ".join(h.ljust(col_widths[h]) for h in headers)
    sep_line = "-+-".join("-" * col_widths[h] for h in headers)

    print(header_line)
    print(sep_line)
    for r in rows:
        print(" | ".join(r[h].ljust(col_widths[h]) for h in headers))


def run_pytest() -> tuple[bool, str]:
    """Run full pytest suite and extract pass count."""
    cmd = [sys.executable, "-m", "pytest", "-v"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    out = proc.stdout + "\n" + proc.stderr

    # Extract pass count
    match = re.search(r"(\d+)\s+passed", out)
    pass_summary = f"{match.group(1)} passed" if match else "pytest completed"
    return proc.returncode == 0, pass_summary


def run_honesty_checks(reports: dict[str, str]) -> bool:
    """Execute honesty checks: source tree grep, forbidden words, and limitations constant."""
    print("\n--- Honesty checks ---")
    all_ok = True

    # 1. Grep source tree: only the review command may assign "assured"
    src_dir = Path("src/aee")
    assignment_pattern = re.compile(r'(\w+(?:\.\w+)*)\s*=\s*["\']assured["\']')
    violations = []

    for py_file in src_dir.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        for line_num, line in enumerate(content.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if assignment_pattern.search(line):
                # Must only be in cli.py
                if py_file.name != "cli.py":
                    violations.append(f"{py_file.name}:{line_num}: {line}")

    if not violations:
        print("[PASS] grep source tree: only the review command may assign \"assured\"")
    else:
        all_ok = False
        print(f"[FAIL] Unauthorized assignment to 'assured': {violations}")

    # 2. No forbidden words in generated reports
    forbidden_violations = []
    for scen, rep_content in reports.items():
        lower_rep = rep_content.lower()
        for fw in FORBIDDEN_WORDS:
            if fw in lower_rep:
                forbidden_violations.append(f"{scen}: found '{fw}'")

    if not forbidden_violations:
        print("[PASS] no forbidden words in generated reports")
    else:
        all_ok = False
        print(f"[FAIL] Forbidden words detected in reports: {forbidden_violations}")

    # 3. Limitations paragraph appears verbatim in every report
    limitations_violations = []
    for scen, rep_content in reports.items():
        if LIMITATIONS_STATEMENT not in rep_content:
            limitations_violations.append(scen)

    if not limitations_violations:
        print("[PASS] Limitations paragraph appears verbatim in every report")
    else:
        all_ok = False
        print(f"[FAIL] Limitations paragraph missing or altered in: {limitations_violations}")

    return all_ok


def main() -> int:
    """Main benchmark runner entrypoint."""
    aee_bin = find_aee_executable()

    with tempfile.TemporaryDirectory() as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)
        scenarios_ok, rows, reports = run_scenarios(aee_bin, tmp_dir)

        print("\nScenario Results:")
        print_table(rows)

        pytest_ok, pytest_summary = run_pytest()
        print(f"\nPytest: {pytest_summary} ({'PASS' if pytest_ok else 'FAIL'})")

        honesty_ok = run_honesty_checks(reports)

        if scenarios_ok and pytest_ok and honesty_ok:
            print("\nResult: All scenarios, honesty checks, and test suite PASSED.")
            return 0
        else:
            print("\nResult: Benchmark verification FAILED.")
            return 1


if __name__ == "__main__":
    sys.exit(main())
