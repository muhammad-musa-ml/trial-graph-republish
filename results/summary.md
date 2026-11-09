# Measurements

Snapshot: 1195 AbbVie-sponsored studies, 1195 kept, 0 quarantined. Warnings: W001 18, W002 1, W003 3, W004 0.
Python 3.13.5, SQLite 3.49.1, Windows-11-10.0.26200-SP0. Each timing is the median of 7 runs, with the range in brackets.

| Change | Labels changed | Trials rewritten | STUDIES edges deleted / inserted (of 1636) | Concepts added / renamed / dropped | Rows written: republish / full publish | Republish | Full publish |
|---|---|---|---|---|---|---|---|
| v1 to v2 | 28 | 137 of 1195 | 169 / 83 | 2 / 1 / 27 | 318 / 7407 | 0.061 s (0.056 to 0.070) | 0.154 s (0.144 to 0.157) |
| v2, one rule edited | 1 | 2 of 1195 | 4 / 3 | 0 / 0 / 0 | 9 / 7406 | 0.057 s (0.051 to 0.070) | 0.166 s (0.156 to 0.170) |

Reading and checking the data (the first step of both paths) takes 0.041 s (0.037 to 0.045), so most of the republish time is that step and not the writes.

In every run the republished graph was compared with a full build of the new rules, table by table, and was identical.
