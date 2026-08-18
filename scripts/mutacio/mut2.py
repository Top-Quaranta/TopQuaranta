#!/usr/bin/env python
"""Second-pass mutation for tests the coverage-guided harness cannot reach.

Mode A (banks): a test that covers no production line at run time is usually
asserting over module-level data (phrase banks, hashtag lists, constants).
For each such test we take the project modules its test file imports, mutate
their sites (constants first) and run just that test until one mutant kills it.

Mode B (files): tests that read non-Python artefacts (bin/tq-*, deploy/*,
docs-map.yml, Caddyfile, .sh). We record which repo files each test opens
(sys.addaudithook via a tiny pytest plugin), then apply line-deletion mutants
to those files and run the test until it fails.

Usage: mut2.py <out_dir> <tests_file> [--max-sites N]
Writes <out_dir>/verified2.json and unverified2.txt
"""
import ast
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import mut  # noqa: E402  (reuse collect_sites/apply/run_tests)

PY = sys.executable
APPS = (
    "social",
    "web",
    "ingesta",
    "music",
    "comptes",
    "analytics",
    "topquaranta",
    "ranking",
    "scripts",
)
ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")

PLUGIN = """
import json, os, sys, pytest
_cur = {"id": None}
_files = {}
_repo = os.getcwd()
def _hook(event, args):
    if event == "open" and _cur["id"]:
        p = args[0]
        if isinstance(p, bytes): p = p.decode(errors="ignore")
        p = str(p)
        if p.startswith(_repo) and "/.venv/" not in p and "/tests/" not in p and "__pycache__" not in p:
            _files.setdefault(_cur["id"], set()).add(os.path.relpath(p, _repo))
sys.addaudithook(_hook)
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    _cur["id"] = item.nodeid
    yield
    _cur["id"] = None
def pytest_sessionfinish(session):
    out = os.environ.get("MUT_OPENED_OUT")
    if out:
        json.dump({k: sorted(v) for k, v in _files.items()}, open(out, "w"))
"""


def imported_modules(test_file):
    tree = ast.parse(Path(test_file).read_text())
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module)
            for a in node.names:  # from pkg import submodule
                mods.add(node.module + "." + a.name)
        elif isinstance(node, ast.Import):
            for a in node.names:
                mods.add(a.name)
    files = []
    for m in sorted(mods):
        if not m.split(".")[0] in APPS:
            continue
        p = Path(m.replace(".", "/") + ".py")
        if p.exists():
            files.append(str(p))
        p2 = Path(m.replace(".", "/")) / "__init__.py"
        if p2.exists():
            files.append(str(p2))
    return files


def opened_files(test_ids, out_dir):
    plug = out_dir / "mutplug.py"
    plug.write_text(PLUGIN)
    outj = out_dir / "opened.json"
    env = dict(ENV, PYTHONPATH=str(out_dir), MUT_OPENED_OUT=str(outj))
    subprocess.run(
        [
            PY,
            "-m",
            "pytest",
            "-q",
            "-n",
            "0",
            "-p",
            "no:cacheprovider",
            "-p",
            "mutplug",
            "--no-migrations",
            *test_ids,
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    return json.loads(outj.read_text()) if outj.exists() else {}


def main():
    out_dir = Path(sys.argv[1])
    out_dir.mkdir(exist_ok=True, parents=True)
    tests = [l.strip() for l in open(sys.argv[2]) if l.strip()]
    max_sites = 80
    skip_a = "--skip-a" in sys.argv
    for a in sys.argv[3:]:
        if a.startswith("--max-sites="):
            max_sites = int(a.split("=")[1])
    subprocess.run(["git", "checkout", "--", "."], check=False)
    junit = out_dir / "junit2.xml"
    verified, t0 = {}, time.time()
    pref = {
        "str": 0,
        "num": 0,
        "bool": 0,
        "cmp": 1,
        "if": 1,
        "boolop": 2,
        "delcall": 2,
        "ret": 2,
        "not": 2,
        "aug": 3,
        "binop": 3,
    }

    # ---- Mode A: module-import banks
    by_file = {}
    for t in tests:
        by_file.setdefault(t.split("::")[0], []).append(t)
    for tf, tids in [] if skip_a else by_file.items():
        app = tf.split("/")[0]
        # same-app modules first (banks live next to their tests), then the rest
        mods = sorted(
            imported_modules(tf), key=lambda r: (not r.startswith(app + "/"), r)
        )
        for rel in mods:
            pending = [t for t in tids if t not in verified]
            if not pending:
                break
            src = Path(rel).read_text()
            try:
                tree = ast.parse(src)
            except Exception:
                continue
            sites = sorted(
                mut.collect_sites(tree), key=lambda s: (pref[s.kind], s.lineno)
            )
            for s in sites[:max_sites]:
                pending = [t for t in tids if t not in verified]
                if not pending:
                    break
                try:
                    m = ast.unparse(mut.apply(tree, s))
                    compile(m, rel, "exec")
                except Exception:
                    continue
                Path(rel).write_text(m)
                try:
                    failed = mut.run_tests(pending, junit)
                finally:
                    Path(rel).write_text(src)
                if failed:
                    for t in failed:
                        if t in pending:
                            verified[t] = f"{rel}:{s.lineno} {s.kind}"
                print(
                    f"[A] {rel}:{s.lineno} {s.kind} pending={len(pending)} killed={len(failed or [])} "
                    f"verified={len(verified)}/{len(tests)} t={time.time()-t0:.0f}s",
                    flush=True,
                )

    # ---- Mode B: opened files (line-deletion)
    rest = [t for t in tests if t not in verified]
    if rest:
        opened = opened_files(rest, out_dir)
        file_tests = {}
        for t, fs in opened.items():
            for f in fs:
                if f.endswith((".pyc",)) or f.startswith(".git/"):
                    continue
                file_tests.setdefault(f, set()).add(t)
        # most-shared files first
        for f in sorted(file_tests, key=lambda f: -len(file_tests[f])):
            p = Path(f)
            if not p.is_file():
                continue
            try:
                lines = p.read_text().splitlines(keepends=True)
            except Exception:
                continue
            for i, line in enumerate(lines):
                pending = sorted(t for t in file_tests[f] if t not in verified)
                if not pending:
                    break
                if not line.strip() or line.lstrip().startswith("#"):
                    continue
                p.write_text("".join(lines[:i] + lines[i + 1 :]))
                try:
                    failed = mut.run_tests(pending, junit)
                finally:
                    p.write_text("".join(lines))
                if failed:
                    for t in failed:
                        if t in pending:
                            verified[t] = f"{f}:{i+1} line-deleted"
                    (out_dir / "verified2.json").write_text(
                        json.dumps(verified, indent=1)
                    )
                print(
                    f"[B] {f}:{i+1} pending={len(pending)} killed={len(failed or [])} "
                    f"verified={len(verified)}/{len(tests)} t={time.time()-t0:.0f}s",
                    flush=True,
                )
    unv = [t for t in tests if t not in verified]
    (out_dir / "verified2.json").write_text(json.dumps(verified, indent=1))
    (out_dir / "unverified2.txt").write_text("\n".join(unv))
    print(
        f"[done2] verified={len(verified)} unverified={len(unv)} t={time.time()-t0:.0f}s"
    )


if __name__ == "__main__":
    main()
