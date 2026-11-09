"""Break the code on a copy, one change at a time, and show that the tests notice.

    python tools/prove_tests_bite.py > results/tests-bite.md

Each mutant replaces one piece of source text that must occur exactly once. The copy is made
in a temporary directory; the working tree is never touched.
"""
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MUTANTS = [
    ("republish rewrites no trials", "trialgraph/publish.py",
     "affected = sorted({t for k in changed for t in prep.label_trials[k]})",
     "affected = []"),
    ("republish ignores a changed rule id", "trialgraph/publish.py",
     "if interpret.resolve(k, old) != interpret.resolve(k, new))",
     "if [c for c, _ in interpret.resolve(k, old)] != [c for c, _ in interpret.resolve(k, new)])"),
    ("republish keeps a concept that lost its last edge", "trialgraph/publish.py",
     'conn.executemany("DELETE FROM concepts WHERE concept_id=?", dropped)', "pass"),
    ("republish does not rename a concept", "trialgraph/publish.py",
     'conn.executemany("UPDATE concepts SET label=? WHERE concept_id=?", renamed)', "pass"),
    ("republish does not remove the old edges of a trial", "trialgraph/publish.py",
     "cur = conn.execute(\"DELETE FROM edges WHERE src=? AND rel='STUDIES'\", (nct_id,))\n"
     "                deleted += cur.rowcount",
     "deleted += 0"),
    ("republish leaves the stored rules as they were", "trialgraph/publish.py",
     "_sync_rules(conn, new)", "pass"),
    ("republish does not check that the data is unchanged", "trialgraph/publish.py",
     "if digest != prep.digest:", "if False:"),
    ("an excluded label still gets an edge", "trialgraph/interpret.py",
     "    if rule.excluded:\n        return ()\n", "    if rule.excluded:\n        return (('cond:excluded', rule.rule_id),)\n"),
    ("unbalanced parentheses are not reported", "trialgraph/quality.py",
     'c.count("(") != c.count(")")', 'c.count("(") == c.count(")") + 99'),
    ("curly and acute apostrophes are not unified", "trialgraph/normalize.py",
     "text.translate(_APOSTROPHES)", "text"),
    ("a repeated id is not quarantined", "trialgraph/quality.py",
     "if nct_id and not quarantine and nct_id in seen:", "if False:"),
]


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def run_tests(cwd):
    result = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
                            cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    failed = [line.split(" - ")[0].replace("FAILED ", "")
              for line in (result.stdout or "").splitlines() if line.startswith("FAILED")]
    return result.returncode, failed


def main():
    print("| Change made to a copy | Tests | Failing test files |")
    print("|---|---|---|")
    survivors = 0
    for name, rel, old, new in MUTANTS:
        with tempfile.TemporaryDirectory() as tmp:
            copy = os.path.join(tmp, "copy")
            shutil.copytree(ROOT, copy, ignore=shutil.ignore_patterns(".git", "build", "__pycache__", ".pytest_cache"))
            target = os.path.join(copy, rel)
            before = sha(target)
            with open(target, encoding="utf-8", newline="") as f:
                text = f.read()
            if text.count(old) != 1:
                print("| %s | NOT RUN (anchor found %d times) | |" % (name, text.count(old)))
                survivors += 1
                continue
            with open(target, "w", encoding="utf-8", newline="") as f:
                f.write(text.replace(old, new))
            if sha(target) == before:
                print("| %s | NOT RUN (file unchanged) | |" % name)
                survivors += 1
                continue
            code, failed = run_tests(copy)
            if code == 0:
                survivors += 1
                print("| %s | PASSED (the tests missed it) | |" % name)
            else:
                files = sorted({f.split("::")[0].replace("tests/", "") for f in failed})
                print("| %s | %d failed | %s |" % (name, len(failed), ", ".join(files) or "(collection error)"))
    # the unmodified copy must pass, or the table above says nothing
    with tempfile.TemporaryDirectory() as tmp:
        copy = os.path.join(tmp, "copy")
        shutil.copytree(ROOT, copy, ignore=shutil.ignore_patterns(".git", "build", "__pycache__", ".pytest_cache"))
        code, _ = run_tests(copy)
    print()
    print("Unmodified copy: %s. Changes the tests missed or that did not run: %d of %d."
          % ("all tests pass" if code == 0 else "TESTS FAIL", survivors, len(MUTANTS)))
    return 0 if code == 0 and survivors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
