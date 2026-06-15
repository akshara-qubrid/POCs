"""
Smoke-test runner for all three POCs.
Tests a single live API call per system to verify connectivity and agent flow.

Usage:
    python test_all.py              # runs all three
    python test_all.py apm          # ai-product-manager only
    python test_all.py memory       # memory-governance only
    python test_all.py diligence    # startup-due-diligence only
"""
import json
import sys
import time
import traceback


def separator(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def test_apm():
    separator("TEST: AI Product Manager")
    import importlib, sys as _sys
    # run from the ai-product-manager folder so relative imports resolve
    import os
    os.chdir(os.path.join(os.path.dirname(__file__), "ai-product-manager"))
    _sys.path.insert(0, os.getcwd())
    from ai_product_manager.main import run
    result = run("An AI-powered personal finance tracker for Gen Z users")
    assert isinstance(result, dict), f"Expected dict, got {type(result)}"
    print("\n[PASS] AI Product Manager returned a dict result")
    return result


def test_memory():
    separator("TEST: Memory Governance")
    import os, sys as _sys
    os.chdir(os.path.join(os.path.dirname(__file__), "memory-governance"))
    _sys.path.insert(0, os.getcwd())
    from memory_governance.main import run_demo
    results = run_demo()
    assert results, "Expected non-empty results from memory governance"
    print("\n[PASS] Memory Governance completed successfully")
    return results


def test_diligence():
    separator("TEST: Startup Due Diligence")
    import os, sys as _sys
    os.chdir(os.path.join(os.path.dirname(__file__), "startup-due-diligence"))
    _sys.path.insert(0, os.getcwd())
    from due_diligence.main import run
    result = run("B2B SaaS platform for automated AP/AR reconciliation targeting mid-market CFOs")
    assert isinstance(result, dict), f"Expected dict, got {type(result)}"
    print("\n[PASS] Startup Due Diligence returned a dict result")
    return result


TESTS = {
    "apm": test_apm,
    "memory": test_memory,
    "diligence": test_diligence,
}

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "all"
    base_dir = os.path.dirname(os.path.abspath(__file__))

    import os

    passed = []
    failed = []

    tests_to_run = list(TESTS.items()) if target == "all" else [(target, TESTS[target])]

    for name, fn in tests_to_run:
        # reset cwd for each test
        os.chdir(base_dir)
        t0 = time.time()
        try:
            fn()
            elapsed = time.time() - t0
            passed.append((name, elapsed))
        except Exception as exc:
            elapsed = time.time() - t0
            failed.append((name, str(exc)))
            print(f"\n[FAIL] {name}: {exc}")
            traceback.print_exc()

    print(f"\n{'='*60}")
    print("RESULTS")
    print(f"{'='*60}")
    for name, elapsed in passed:
        print(f"  ✓ {name:12} passed  ({elapsed:.1f}s)")
    for name, err in failed:
        print(f"  ✗ {name:12} FAILED  — {err[:80]}")
    print()
    sys.exit(0 if not failed else 1)
