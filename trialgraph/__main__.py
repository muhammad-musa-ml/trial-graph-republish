"""Command line.

    python -m trialgraph quality   --data data/abbvie_trials.jsonl
    python -m trialgraph publish   --data data/abbvie_trials.jsonl --interp interpretations/v1.csv --db build/graph.db
    python -m trialgraph republish --data data/abbvie_trials.jsonl --interp interpretations/v2.csv --db build/graph.db
    python -m trialgraph check     --data data/abbvie_trials.jsonl --interp interpretations/v2.csv --db build/graph.db
"""
import argparse
import json
import os
import sys
import tempfile
from collections import Counter

from . import interpret, publish, quality


def read_rows(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def cmd_quality(args):
    clean, quarantined, warned = quality.screen(read_rows(args.data))
    print("studies read %d, kept %d, quarantined %d" % (len(clean) + len(quarantined), len(clean), len(quarantined)))
    counts = Counter(code for _, codes in quarantined for code in codes)
    counts.update(code for _, codes in warned for code in codes)
    for code in sorted(counts):
        text = quality.QUARANTINE.get(code) or quality.WARNINGS[code]
        print("  %s  %4d  %s" % (code, counts[code], text))
    return 0


def cmd_publish(args):
    os.makedirs(os.path.dirname(os.path.abspath(args.db)), exist_ok=True)
    stats = publish.full_publish(args.db, read_rows(args.data), interpret.load(args.interp))
    print(json.dumps(stats, sort_keys=True))
    return 0


def cmd_republish(args):
    try:
        stats = publish.republish(args.db, read_rows(args.data), interpret.load(args.interp))
    except publish.DataChanged as err:
        print("refused:", err, file=sys.stderr)
        return 2
    print(json.dumps(stats, sort_keys=True))
    return 0


def cmd_check(args):
    """Build the interpretation from scratch beside the graph and compare the two."""
    rows, interp = read_rows(args.data), interpret.load(args.interp)
    with tempfile.TemporaryDirectory() as tmp:
        fresh = os.path.join(tmp, "fresh.db")
        publish.full_publish(fresh, rows, interp)
        have, want = publish.dump(args.db), publish.dump(fresh)
    bad = [t for t in publish.TABLES if have[t] != want[t]]
    if bad:
        print("DIFFERENT in:", ", ".join(bad))
        return 1
    print("same graph as a full build of %s (%d rows in %d tables)" % (
        interp.version, sum(len(v) for v in want.values()), len(want)))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="trialgraph")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, fn, needs_interp in [("quality", cmd_quality, False), ("publish", cmd_publish, True),
                                   ("republish", cmd_republish, True), ("check", cmd_check, True)]:
        p = sub.add_parser(name)
        p.add_argument("--data", default="data/abbvie_trials.jsonl")
        if needs_interp:
            p.add_argument("--interp", required=True)
            p.add_argument("--db", default="build/graph.db")
        p.set_defaults(fn=fn)
    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
