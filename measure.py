"""Measure a full publish against a republish, on the committed snapshot.

    python measure.py

Writes results/measurements.json and results/summary.md. Timings are wall-clock seconds of the
publish or republish call alone, on a temporary SQLite file, repeated RUNS times.
"""
import json
import os
import platform
import shutil
import sqlite3
import statistics
import sys
import tempfile
import time

from trialgraph import interpret, publish, quality

ROOT = os.path.dirname(os.path.abspath(__file__))
RUNS = 7


def read_rows():
    with open(os.path.join(ROOT, "data", "abbvie_trials.jsonl"), encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def timed(fn):
    start = time.perf_counter()
    result = fn()
    return time.perf_counter() - start, result


def spread(values):
    return "%.3f s (%.3f to %.3f)" % (statistics.median(values), min(values), max(values))


def one_rule_edit(v2):
    """v2 with a single rule changed: 'moderate plaque psoriasis' now stands for plain psoriasis."""
    rows = []
    for rule_id, key, cid, label in v2.as_rows():
        if key == "moderate plaque psoriasis":
            cid, label = "cond:psoriasis", "Psoriasis"
        rows.append((rule_id, key, cid, label))
    return interpret.build("v2-edit", rows)


def scenario(rows, old, new, workdir):
    base = os.path.join(workdir, "base.db")
    publish.full_publish(base, rows, old)
    republish_times, full_times, prepare_times, stats = [], [], [], None
    for i in range(RUNS):
        inc = os.path.join(workdir, "inc%d.db" % i)
        shutil.copyfile(base, inc)
        seconds, stats = timed(lambda: publish.republish(inc, rows, new))
        republish_times.append(seconds)
        full = os.path.join(workdir, "full%d.db" % i)
        seconds, full_stats = timed(lambda: publish.full_publish(full, rows, new))
        full_times.append(seconds)
        prepare_times.append(timed(lambda: publish.Prepared(rows))[0])
        if publish.dump(inc) != publish.dump(full):
            raise SystemExit("republished graph differs from a full build: %s -> %s" % (old.version, new.version))
    conn = sqlite3.connect(base)
    studies = conn.execute("SELECT COUNT(*) FROM edges WHERE rel='STUDIES'").fetchone()[0]
    conn.close()
    stats = dict(stats)
    stats.update({
        "studies_edges_before": studies,
        "republish_seconds": republish_times,
        "full_publish_seconds": full_times,
        "prepare_seconds": prepare_times,
        "full_rows_written": full_stats["rows_written"],
    })
    return stats


def main():
    rows = read_rows()
    v1 = interpret.load(os.path.join(ROOT, "interpretations", "v1.csv"))
    v2 = interpret.load(os.path.join(ROOT, "interpretations", "v2.csv"))
    clean, quarantined, warned = quality.screen(rows)
    out = {
        "python": platform.python_version(), "sqlite": sqlite3.sqlite_version,
        "platform": platform.platform(), "runs": RUNS,
        "studies": len(rows), "kept": len(clean), "quarantined": len(quarantined),
        "warnings": {code: sum(1 for _, c in warned if code in c) for code in sorted(quality.WARNINGS)},
    }
    with tempfile.TemporaryDirectory() as tmp:
        out["v1_to_v2"] = scenario(rows, v1, v2, tmp)
    with tempfile.TemporaryDirectory() as tmp:
        out["v2_one_rule_edit"] = scenario(rows, v2, one_rule_edit(v2), tmp)
    os.makedirs(os.path.join(ROOT, "results"), exist_ok=True)
    with open(os.path.join(ROOT, "results", "measurements.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, indent=2, sort_keys=True)
        f.write("\n")
    with open(os.path.join(ROOT, "results", "summary.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write(summary(out))
    sys.stdout.write(summary(out))


def summary(out):
    lines = [
        "# Measurements",
        "",
        "Snapshot: %d AbbVie-sponsored studies, %d kept, %d quarantined. Warnings: %s."
        % (out["studies"], out["kept"], out["quarantined"],
           ", ".join("%s %d" % (k, v) for k, v in out["warnings"].items())),
        "Python %s, SQLite %s, %s. Each timing is the median of %d runs, with the range in brackets."
        % (out["python"], out["sqlite"], out["platform"], out["runs"]),
        "",
        "| Change | Labels changed | Trials rewritten | STUDIES edges deleted / inserted (of %d) | Concepts added / renamed / dropped | Rows written: republish / full publish | Republish | Full publish |"
        % out["v1_to_v2"]["studies_edges_before"],
        "|---|---|---|---|---|---|---|---|",
    ]
    for key, title in [("v1_to_v2", "v1 to v2"), ("v2_one_rule_edit", "v2, one rule edited")]:
        s = out[key]
        lines.append("| %s | %d | %d of %d | %d / %d | %d / %d / %d | %d / %d | %s | %s |" % (
            title, s["labels_changed"], s["trials_rewritten"], out["kept"],
            s["studies_edges_deleted"], s["studies_edges_inserted"],
            s["concepts_added"], s["concepts_renamed"], s["concepts_dropped"],
            s["rows_written"], s["full_rows_written"],
            spread(s["republish_seconds"]), spread(s["full_publish_seconds"])))
    lines += [
        "",
        "Reading and checking the data (the first step of both paths) takes %s, so most of the "
        "republish time is that step and not the writes."
        % spread(out["v1_to_v2"]["prepare_seconds"]),
        "",
        "In every run the republished graph was compared with a full build of the new rules, "
        "table by table, and was identical.",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
