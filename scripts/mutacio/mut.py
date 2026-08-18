#!/usr/bin/env python
"""Coverage-guided per-test mutation verification.

Goal: for every test in <tests_dir>, find at least one mutant of production
code that makes THAT test fail. A test that fails on some mutant is
"verified" (it cries when the code it exercises breaks). A test that
survives every mutant of every line it covers is "unverified".

Usage (run from the repo worktree root):
  python mut.py <tests_dir> <out_dir> [--src a,b,c] [--budget-runs N]

Phase 1: pytest --cov with per-test contexts -> line -> tests map.
Phase 2: mutate lines covered by unverified tests, run only those tests.
"""
import ast
import copy
import json
import os
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

PY = sys.executable
APPS = [
    "social",
    "web",
    "ingesta",
    "music",
    "comptes",
    "analytics",
    "topquaranta",
    "ranking",
]
ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")

# ----------------------------------------------------------------- mutants


class Site:
    def __init__(self, kind, lineno, path):
        self.kind, self.lineno, self.path = kind, lineno, path

    def __repr__(self):
        return f"{self.kind}@{self.lineno}"


def collect_sites(tree):
    sites = []

    class V(ast.NodeVisitor):
        def __init__(self):
            self.path = []

        def generic_visit(self, node):
            for field, value in ast.iter_fields(node):
                if isinstance(value, list):
                    for i, item in enumerate(value):
                        if isinstance(item, ast.AST):
                            self.path.append((field, i))
                            self.visit(item)
                            self.path.pop()
                elif isinstance(value, ast.AST):
                    self.path.append((field, None))
                    self.visit(value)
                    self.path.pop()

        def add(self, kind, node):
            sites.append(Site(kind, node.lineno, tuple(self.path)))

        def visit_Compare(self, node):
            self.add("cmp", node)
            self.generic_visit(node)

        def visit_BoolOp(self, node):
            self.add("boolop", node)
            self.generic_visit(node)

        def visit_BinOp(self, node):
            if isinstance(
                node.op, (ast.Add, ast.Sub, ast.Mult, ast.FloorDiv, ast.Div, ast.Mod)
            ):
                self.add("binop", node)
            self.generic_visit(node)

        def visit_UnaryOp(self, node):
            if isinstance(node.op, ast.Not):
                self.add("not", node)
            self.generic_visit(node)

        def visit_If(self, node):
            self.add("if", node)
            self.generic_visit(node)

        def visit_While(self, node):
            self.add("if", node)
            self.generic_visit(node)

        def visit_IfExp(self, node):
            self.add("if", node)
            self.generic_visit(node)

        def visit_Return(self, node):
            if node.value is not None and not (
                isinstance(node.value, ast.Constant) and node.value.value is None
            ):
                self.add("ret", node)
            self.generic_visit(node)

        def visit_Constant(self, node):
            v = node.value
            if isinstance(v, bool):
                self.add("bool", node)
            elif isinstance(v, (int, float)) and not isinstance(v, bool):
                self.add("num", node)
            elif isinstance(v, str) and v and len(v) < 200:
                self.add("str", node)

        def visit_Expr(self, node):
            # docstrings excluded; only calls
            if isinstance(node.value, ast.Call):
                self.add("delcall", node)
            self.generic_visit(node)

        def visit_AugAssign(self, node):
            if isinstance(node.op, (ast.Add, ast.Sub)):
                self.add("aug", node)
            self.generic_visit(node)

        def visit_JoinedStr(self, node):
            # don't mutate string constants inside f-strings (unparse quirks)
            pass

    V().visit(tree)
    return sites


CMP_SWAP = {
    ast.Eq: ast.NotEq,
    ast.NotEq: ast.Eq,
    ast.Lt: ast.GtE,
    ast.LtE: ast.Gt,
    ast.Gt: ast.LtE,
    ast.GtE: ast.Lt,
    ast.In: ast.NotIn,
    ast.NotIn: ast.In,
    ast.Is: ast.IsNot,
    ast.IsNot: ast.Is,
}
BIN_SWAP = {
    ast.Add: ast.Sub,
    ast.Sub: ast.Add,
    ast.Mult: ast.Add,
    ast.Div: ast.Mult,
    ast.FloorDiv: ast.Mult,
    ast.Mod: ast.Add,
}


def get_by_path(tree, path):
    node = tree
    for field, idx in path:
        val = getattr(node, field)
        node = val[idx] if idx is not None else val
    return node


def set_by_path(tree, path, new):
    parent = get_by_path(tree, path[:-1])
    field, idx = path[-1]
    if idx is None:
        setattr(parent, field, new)
    else:
        getattr(parent, field)[idx] = new


def apply(tree, site):
    tree = copy.deepcopy(tree)
    node = get_by_path(tree, site.path)
    k = site.kind
    if k == "cmp":
        node.ops = [CMP_SWAP[type(op)]() for op in node.ops]
    elif k == "boolop":
        node.op = ast.Or() if isinstance(node.op, ast.And) else ast.And()
    elif k == "binop":
        node.op = BIN_SWAP[type(node.op)]()
    elif k == "not":
        set_by_path(tree, site.path, node.operand)
    elif k == "if":
        node.test = ast.UnaryOp(op=ast.Not(), operand=node.test)
    elif k == "ret":
        node.value = ast.Constant(value=None)
    elif k == "bool":
        node.value = not node.value
    elif k == "num":
        node.value = node.value + 1
    elif k == "str":
        node.value = node.value + "XX"
    elif k == "delcall":
        set_by_path(tree, site.path, ast.Pass())
    elif k == "aug":
        node.op = ast.Sub() if isinstance(node.op, ast.Add) else ast.Add()
    ast.fix_missing_locations(tree)
    return tree


# ---------------------------------------------------------------- coverage


def run_coverage(tests_dir, out_dir, src):
    cov_args = [f"--cov={s}" for s in src]
    cmd = [
        PY,
        "-m",
        "pytest",
        tests_dir,
        "-q",
        "-n",
        "0",
        "-p",
        "no:cacheprovider",
        "--cov-context=test",
        "--cov-report=",
        *cov_args,
    ]
    print("[cov]", " ".join(cmd), flush=True)
    r = subprocess.run(cmd, env=ENV, capture_output=True, text=True)
    (out_dir / "cov_run.log").write_text(r.stdout + r.stderr)
    if r.returncode != 0:
        print(r.stdout[-3000:])
        sys.exit("baseline failed")
    from coverage import CoverageData

    d = CoverageData()
    d.read()
    line_tests = {}  # file -> {line: set(testid)}
    for f in d.measured_files():
        rel = os.path.relpath(f)
        if "/tests/" in rel or "/migrations/" in rel or rel.startswith(".venv"):
            continue
        m = {}
        for ln, ctxs in d.contexts_by_lineno(f).items():
            ts = {c.split("|")[0] for c in ctxs if c and c.endswith("|run")}
            if ts:
                m[ln] = ts
        if m:
            line_tests[rel] = m
    return line_tests


def collect_tests(tests_dir):
    r = subprocess.run(
        [
            PY,
            "-m",
            "pytest",
            tests_dir,
            "-q",
            "-n",
            "0",
            "-p",
            "no:cacheprovider",
            "--collect-only",
        ],
        env=ENV,
        capture_output=True,
        text=True,
    )
    return [l.strip() for l in r.stdout.splitlines() if "::" in l]


# ------------------------------------------------------------------ runner


SLOW = set()  # tests that need real migrations (data seeds)


def run_tests(test_ids, junit, timeout=120):
    fast = [t for t in test_ids if t not in SLOW]
    slow = [t for t in test_ids if t in SLOW]
    failed = set()
    for ids, extra in ((fast, ["--no-migrations"]), (slow, [])):
        if not ids:
            continue
        r = _run(ids, junit, extra, timeout)
        if r is None:
            return None
        failed |= r
    return failed


def _run(test_ids, junit, extra, timeout):
    cmd = [
        PY,
        "-m",
        "pytest",
        "-q",
        "-n",
        "0",
        "-p",
        "no:cacheprovider",
        "--no-header",
        "-o",
        "console_output_style=classic",
        *extra,
        f"--junitxml={junit}",
        *test_ids,
    ]
    try:
        subprocess.run(cmd, env=ENV, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None
    if not junit.exists():
        return None
    root = ET.parse(junit).getroot()
    failed = set()
    for tc in root.iter("testcase"):
        if tc.find("failure") is not None:
            cls = tc.get("classname", "")
            name = tc.get("name")
            # classname like social.tests.test_x or social.tests.test_x.TestC
            parts = cls.split(".")
            # find file part
            for i in range(len(parts), 0, -1):
                cand = "/".join(parts[:i]) + ".py"
                if os.path.exists(cand):
                    rest = parts[i:]
                    tid = cand + "::" + "::".join(rest + [name])
                    failed.add(tid)
                    break
    junit.unlink(missing_ok=True)
    return failed


def norm(tid):
    # strip parametrize ids so we can match with coverage contexts consistently
    return tid


def main():
    tests_dir = sys.argv[1]
    out_dir = Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)
    src = APPS
    budget = 10**9
    for a in sys.argv[3:]:
        if a.startswith("--src="):
            src = a[6:].split(",")
        if a.startswith("--budget-runs="):
            budget = int(a[len("--budget-runs=") :])
        if a.startswith("--slow="):
            SLOW.update(l.strip() for l in open(a[7:]) if l.strip())
    # a killed run may have left a mutant on disk: restore the tree first
    subprocess.run(["git", "checkout", "--", "."], check=False)
    # clear pycache
    for p in Path(".").rglob("__pycache__"):
        if ".venv" not in str(p):
            shutil.rmtree(p, ignore_errors=True)

    state_f = out_dir / "state.json"
    if state_f.exists():
        st = json.loads(state_f.read_text())
        line_tests = {
            f: {int(k): set(v) for k, v in m.items()}
            for f, m in st["line_tests"].items()
        }
        all_tests = st["all_tests"]
        verified = st["verified"]
        tried = set(map(tuple, st["tried"]))
        print(
            f"[resume] {len(verified)} verified, {len(tried)} sites tried", flush=True
        )
    else:
        all_tests = collect_tests(tests_dir)
        print(f"[collect] {len(all_tests)} tests", flush=True)
        line_tests = run_coverage(tests_dir, out_dir, src)
        verified = {}
        tried = set()
        print(f"[cov] {len(line_tests)} production files covered", flush=True)

    def save():
        state_f.write_text(
            json.dumps(
                {
                    "line_tests": {
                        f: {str(k): sorted(v) for k, v in m.items()}
                        for f, m in line_tests.items()
                    },
                    "all_tests": all_tests,
                    "verified": verified,
                    "tried": sorted(tried),
                }
            )
        )

    all_set = set(all_tests)
    # coverage contexts may name parametrized ids identically to collect ids — good.
    covered_tests = (
        set().union(*[s for m in line_tests.values() for s in m.values()])
        if line_tests
        else set()
    )
    never_covered = sorted(all_set - covered_tests)
    (out_dir / "never_covered.txt").write_text("\n".join(never_covered))
    print(
        f"[cov] {len(never_covered)} tests cover no production line at all", flush=True
    )

    unverified = lambda: all_set - set(verified)
    runs = 0
    t0 = time.time()
    junit = out_dir / "junit.xml"
    SKIP_FILES = ("urls.py", "apps.py", "admin.py", "/settings/", "wsgi.py", "asgi.py")
    pref = {
        "cmp": 0,
        "if": 0,
        "boolop": 1,
        "delcall": 1,
        "ret": 1,
        "not": 1,
        "num": 2,
        "bool": 2,
        "aug": 2,
        "binop": 3,
        "str": 5,
    }
    # gather every site of every covered production file up front
    trees, originals, allsites = {}, {}, []
    for rel in line_tests:
        if any(x in rel for x in SKIP_FILES):
            continue
        p = Path(rel)
        try:
            originals[rel] = p.read_text()
            trees[rel] = ast.parse(originals[rel])
        except Exception as e:
            print("[skip]", rel, e)
            continue
        for s in collect_sites(trees[rel]):
            if s.lineno in line_tests[rel]:
                allsites.append((rel, s))
    print(f"[sites] {len(allsites)} candidate sites in {len(trees)} files", flush=True)

    def site_key(item):
        rel, s = item
        cov = line_tests[rel].get(s.lineno, set()) & unverified()
        return (pref[s.kind], -len(cov), rel, s.lineno)

    # rounds: re-sort after each round so exhausted tests stop attracting runs
    round_no = 0
    while runs < budget:
        round_no += 1
        pending = [
            it
            for it in allsites
            if (it[0], it[1].lineno, it[1].kind, repr(it[1].path)) not in tried
            and (line_tests[it[0]].get(it[1].lineno, set()) & unverified())
        ]
        if not pending:
            break
        pending.sort(key=site_key)
        # take a slice per round so priorities refresh as tests get verified
        for rel, s in pending[:40]:
            if runs >= budget:
                break
            key_t = (rel, s.lineno, s.kind, repr(s.path))
            targets = line_tests[rel].get(s.lineno, set()) & unverified()
            if not targets:
                tried.add(key_t)
                continue
            try:
                src_m = ast.unparse(apply(trees[rel], s))
                compile(src_m, rel, "exec")
            except Exception:
                tried.add(key_t)
                continue
            p = Path(rel)
            p.write_text(src_m)
            try:
                failed = run_tests(sorted(targets), junit)
            finally:
                p.write_text(originals[rel])
            runs += 1
            tried.add(key_t)
            if failed is None:
                print(f"[timeout] {rel}:{s.lineno} {s.kind}", flush=True)
                continue
            newly = failed & targets
            for t in newly:
                verified[t] = f"{rel}:{s.lineno} {s.kind}"
            print(
                f"[run {runs}] {rel}:{s.lineno} {s.kind} targets={len(targets)} killed={len(newly)} "
                f"verified={len(verified)}/{len(all_set)} unverified={len(unverified())} "
                f"t={time.time()-t0:.0f}s",
                flush=True,
            )
            if runs % 10 == 0:
                save()
        save()
    save()
    unv = sorted(unverified())
    (out_dir / "unverified.txt").write_text("\n".join(unv))
    (out_dir / "verified.json").write_text(
        json.dumps(verified, indent=1, sort_keys=True)
    )
    print(
        f"[done] runs={runs} verified={len(verified)} unverified={len(unv)} "
        f"never_covered={len(never_covered)} t={time.time()-t0:.0f}s",
        flush=True,
    )


if __name__ == "__main__":
    main()
