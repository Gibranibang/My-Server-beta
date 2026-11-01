#!/usr/bin/env python3
"""
MyServer Desktop Alpha - Unified E2E Test Suite Runner.
Discovers and executes Tier 1 (Features), Tier 2 (Boundaries), Tier 3 (Pairwise), and Tier 4 (Scenarios).
Outputs comprehensive test summary and enforces exit code 0 only on full pass.
"""

import os
import sys
import time
import argparse
import unittest

ALPHA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ALPHA_DIR not in sys.path:
    sys.path.insert(0, ALPHA_DIR)

E2E_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
if E2E_TESTS_DIR not in sys.path:
    sys.path.insert(0, E2E_TESTS_DIR)

import test_tier1_features
import test_tier2_boundaries
import test_tier3_pairwise
import test_tier4_scenarios

# Force utf-8 encoding with replace for Windows terminal compatibility
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


TIER_MODULES = {
    1: ("Tier 1 - Isolated Feature Coverage (R1-R5)", test_tier1_features.TestTier1Features),
    2: ("Tier 2 - Boundary Value & Stress Analysis", test_tier2_boundaries.TestTier2Boundaries),
    3: ("Tier 3 - Pairwise Combinatorial Interactions", test_tier3_pairwise.TestTier3Pairwise),
    4: ("Tier 4 - Real-World End-to-End Workload Scenarios", test_tier4_scenarios.TestTier4Scenarios),
}


class DetailedResultCollector(unittest.TestResult):
    """Custom test result collector capturing pass/fail/skip details per test."""

    def __init__(self):
        super().__init__()
        self.successes = []

    def addSuccess(self, test):
        super().addSuccess(test)
        self.successes.append(test)


def run_tier(tier_num, verbosity=1):
    """Run a single tier test suite and return metrics."""
    tier_name, test_class = TIER_MODULES[tier_num]
    suite = unittest.TestLoader().loadTestsFromTestCase(test_class)
    runner = unittest.TextTestRunner(verbosity=verbosity)

    print("\n" + "=" * 78)
    print(f"[*] RUNNING: {tier_name}")
    print("=" * 78)

    start_time = time.time()
    result = runner.run(suite)
    elapsed = time.time() - start_time

    total_tests = result.testsRun
    failures = len(result.failures)
    errors = len(result.errors)
    skipped = len(result.skipped)
    passed = total_tests - (failures + errors + skipped)

    return {
        "tier": tier_num,
        "name": tier_name,
        "total": total_tests,
        "passed": passed,
        "failed": failures,
        "errors": errors,
        "skipped": skipped,
        "elapsed": elapsed,
        "is_success": result.wasSuccessful(),
        "failure_details": result.failures,
        "error_details": result.errors,
    }


def main():
    parser = argparse.ArgumentParser(description="MyServer Desktop Alpha E2E Test Suite Runner")
    parser.add_argument("--tier", type=int, choices=[1, 2, 3, 4], help="Run a specific tier (1, 2, 3, or 4)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output for each test")
    args = parser.parse_args()

    verbosity = 2 if args.verbose else 1

    selected_tiers = [args.tier] if args.tier else [1, 2, 3, 4]

    print("=" * 78)
    print("           MYSERVER DESKTOP ALPHA - E2E TEST SUITE RUNNER")
    print("=" * 78)
    print(f"Target Directory : {ALPHA_DIR}")
    print(f"Selected Tiers   : {selected_tiers}")
    print("=" * 78)

    tier_results = []
    overall_start = time.time()

    for t_num in selected_tiers:
        res = run_tier(t_num, verbosity=verbosity)
        tier_results.append(res)

    overall_elapsed = time.time() - overall_start

    # Print Summary Report Table
    print("\n" + "=" * 78)
    print("                         E2E TEST SUMMARY REPORT")
    print("=" * 78)
    print(f"{'Tier':<8}{'Total':<8}{'Pass':<8}{'Fail':<8}{'Error':<8}{'Duration':<12}{'Status'}")
    print("-" * 78)

    all_passed = True
    grand_total = 0
    grand_pass = 0
    grand_fail = 0
    grand_error = 0

    for r in tier_results:
        grand_total += r["total"]
        grand_pass += r["passed"]
        grand_fail += r["failed"]
        grand_error += r["errors"]
        status_str = "PASS [OK]" if r["is_success"] else "FAIL [X]"
        if not r["is_success"]:
            all_passed = False

        print(
            f"Tier {r['tier']:<3}{r['total']:<8}{r['passed']:<8}{r['failed']:<8}{r['errors']:<8}{r['elapsed']:.2f}s{'':<6}{status_str}"
        )

    print("-" * 78)
    print(
        f"{'TOTAL':<8}{grand_total:<8}{grand_pass:<8}{grand_fail:<8}{grand_error:<8}{overall_elapsed:.2f}s{'':<6}{'ALL PASSED' if all_passed else 'FAILURES DETECTED'}"
    )
    print("=" * 78)

    if not all_passed:
        print("\n[!] BREAKDOWN OF FAILED / ERRORED TESTS (BASELINE DEFECTS TO IMPLEMENT):")
        for r in tier_results:
            if not r["is_success"]:
                print(f"\n--- {r['name']} Failures ---")
                for test, trace in r["failure_details"]:
                    print(f"\n[FAIL] {test}:")
                    print(trace.strip())
                for test, trace in r["error_details"]:
                    print(f"\n[ERROR] {test}:")
                    print(trace.strip())

    print("\n" + "=" * 78)
    if all_passed:
        print(">> VERDICT: SUCCESS (Exit Code 0). All E2E requirements fully verified!")
        print("=" * 78)
        sys.exit(0)
    else:
        print(f">> VERDICT: FAILED (Exit Code 1). {grand_fail + grand_error} tests failed.")
        print("=" * 78)
        sys.exit(1)


if __name__ == "__main__":
    main()
