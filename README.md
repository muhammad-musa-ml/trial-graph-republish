# trial-graph-republish

I built a small pipeline that publishes the 1,195 ClinicalTrials.gov studies with AbbVie as lead sponsor as a graph (trials, conditions, interventions, sponsor), and that republishes only the part of the graph that changes when the mapping from condition labels to concepts changes.

## Why

Condition labels in the registry are free text. The same disease shows up as "Rheumatoid Arthritis", "Rheumatoid Arthritis (RA)" and "Arthritis, Rheumatoid", and "Healthy Volunteers" is listed as a condition. Someone has to decide which labels mean the same thing, and that decision changes: a label gets merged, split, dropped or renamed. I wanted to see what it takes to apply such a change without rebuilding the whole graph, and to prove that the result is the graph a full rebuild would give.

## What it does

- `fetch_trials.py` downloads the studies from the public ClinicalTrials.gov v2 API. The snapshot I used (API data timestamp 2026-11-06) is committed in `data/`, so everything else runs offline.
- `quality` screens every study. A missing or malformed id, a repeated id, no conditions or a bad start date quarantines the study with a reason code (Q001 to Q005). A missing start date, unbalanced parentheses in a condition label, a non-ASCII label or a missing sponsor is counted as a warning (W001 to W004) and the study stays in.
- An interpretation (`interpretations/v1.csv`, `v2.csv`) is a table of rules: a normalized condition label and the concept it stands for. One label can stand for several concepts or for none. A label with no rule becomes a concept of its own. A rule table with a repeated id or label, an unnormalized key or two labels for one concept is refused.
- `publish` builds the graph in SQLite. Every edge keeps its lineage: the rule ids that produced it and the source labels it came from.
- `republish` compares the stored rules with the new ones, finds the labels whose meaning changed, rewrites the condition edges of the trials that carry those labels and fixes the concept nodes. It refuses to run if the trial data is not the data the graph was published from.
- `check` builds the new interpretation from scratch next to the published graph and compares every table.

## Run it

Python 3.10 or newer. The code uses only the standard library; the tests need pytest.

```
python -m trialgraph quality
python -m trialgraph publish   --interp interpretations/v1.csv --db build/graph.db
python -m trialgraph republish --interp interpretations/v2.csv --db build/graph.db
python -m trialgraph check     --interp interpretations/v2.csv --db build/graph.db
python -m pytest
python measure.py
python tools/prove_tests_bite.py
```

## Results

`python measure.py` writes `results/summary.md`. One run on this laptop (Python 3.13.5, SQLite 3.49.1, Windows 11), median of 7 runs with the range in brackets:

| Change | Labels changed | Trials rewritten | Condition edges deleted / inserted (of 1,636) | Rows written: republish / full publish | Republish | Full publish |
|---|---|---|---|---|---|---|
| v1 to v2 | 28 | 137 of 1,195 | 169 / 83 | 318 / 7,407 | 0.061 s (0.056 to 0.070) | 0.154 s (0.144 to 0.157) |
| v2, one rule edited | 1 | 2 of 1,195 | 4 / 3 | 9 / 7,406 | 0.057 s (0.051 to 0.070) | 0.166 s (0.156 to 0.170) |

In every run the republished graph was identical, table by table, to a full build of the new rules. v2 merges the severity variants into the base disease, merges two spellings of relapsed or refractory myeloma, splits one combined label into three conditions, drops the healthy-volunteer labels and renames one concept.

Reading and checking the data is the first step of both paths and takes 0.041 s, so on this small snapshot most of the republish time is that step. The saving is in rows written, not in seconds.

The tests (71) include the real v1 to v2 change, nine hand-built changes (merge, exclude, retarget, split, new rule id, removed rule, rename, new rule, no change), 25 seeded random rule changes, and a check that a failed republish leaves the graph as it was. `tools/prove_tests_bite.py` breaks the code on a copy in 11 ways, one at a time, and every break fails at least one test (`results/tests-bite.md`).

## What this does not show

- The rules are mine. I wrote them from the label variants in this snapshot; no clinician or curator reviewed them. Some are judgement calls, such as merging "Moderate to Severe Rheumatoid Arthritis" into rheumatoid arthritis while keeping juvenile rheumatoid arthritis out of it.
- The graph is SQLite tables, not a graph database, and I did not load it into Neo4j.
- Concepts are my own ids. I did not map them to MeSH, MedDRA or any other ontology.
- It assumes the trial data does not change between publish and republish. Adding new studies is not handled; `republish` refuses and asks for a full publish.
- The snapshot is 1,195 studies and 7,407 rows. The timings come from one laptop and say nothing about larger graphs or a remote store.
- "AbbVie" is a name match on the lead sponsor field. It includes studies listed under "AbbVie (prior sponsor, Abbott)".

## Layout

- `trialgraph/`: `normalize.py`, `quality.py`, `interpret.py`, `publish.py`, `__main__.py`
- `interpretations/`: the two rule tables
- `data/abbvie_trials.jsonl`: the snapshot
- `tests/`, `tools/prove_tests_bite.py`, `measure.py`, `results/`

MIT licence.
