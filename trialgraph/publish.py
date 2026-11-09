"""Build the trial graph in SQLite and republish only the part an interpretation change touches.

Nodes: trials, concepts (conditions), interventions, sponsors.
Edges: STUDIES (trial -> concept), TESTS (trial -> intervention), SPONSORED_BY (trial -> sponsor).
Every edge carries its lineage: the rule ids that produced it and the source labels it came from.

Only STUDIES edges depend on the interpretation. republish() finds the labels whose meaning
changed between the stored interpretation and the new one, rewrites the STUDIES edges of the
trials that carry those labels, and fixes the concept nodes. The result must equal a full build
of the new interpretation; check() and the tests compare the two.
"""
import hashlib
import json
import os
import sqlite3
from collections import Counter, defaultdict

from . import interpret, quality
from .normalize import norm_label, sponsor_name

SCHEMA = """
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE trials(nct_id TEXT PRIMARY KEY, title TEXT, status TEXT, phase TEXT, start_date TEXT);
CREATE TABLE concepts(concept_id TEXT PRIMARY KEY, label TEXT NOT NULL);
CREATE TABLE interventions(intervention_id TEXT PRIMARY KEY, name TEXT NOT NULL, type TEXT);
CREATE TABLE sponsors(sponsor_id TEXT PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE edges(
  src TEXT NOT NULL, rel TEXT NOT NULL, dst TEXT NOT NULL,
  rule_ids TEXT NOT NULL, source_labels TEXT NOT NULL,
  PRIMARY KEY (src, rel, dst));
CREATE TABLE rules(
  rule_id TEXT PRIMARY KEY, match_key TEXT NOT NULL,
  concept_id TEXT NOT NULL, concept_label TEXT NOT NULL);
"""
TABLES = ["meta", "trials", "concepts", "interventions", "sponsors", "edges", "rules"]


class DataChanged(Exception):
    """The trial data differs from what the graph was published from."""


class Prepared:
    """Cleaned studies plus the indexes both publish paths need."""

    def __init__(self, rows):
        self.clean, self.quarantined, self.warned = quality.screen(rows)
        raw_counts = defaultdict(Counter)
        self.label_trials = defaultdict(list)
        for row in self.clean:
            keys = set()
            for raw in row["conditions"]:
                raw = raw.strip()
                if raw:
                    raw_counts[norm_label(raw)][raw] += 1
                    keys.add(norm_label(raw))
            for key in keys:
                self.label_trials[key].append(row["nct_id"])
        # A label with no rule becomes its own concept, named by its most common spelling.
        self.auto_labels = {
            key: sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
            for key, c in raw_counts.items()
        }
        self.by_id = {row["nct_id"]: row for row in self.clean}
        blob = json.dumps(self.clean, sort_keys=True, ensure_ascii=True).encode("ascii")
        self.digest = hashlib.sha256(blob).hexdigest()


def concept_label(concept_id, labels, prep):
    if concept_id.startswith("raw:"):
        return prep.auto_labels[concept_id[4:]]
    return labels[concept_id]


def study_edges(row, interp):
    """STUDIES edges of one trial under one interpretation."""
    found = {}
    for raw in row["conditions"]:
        raw = raw.strip()
        if not raw:
            continue
        for concept_id, rule_id in interpret.resolve(norm_label(raw), interp):
            rules, sources = found.setdefault(concept_id, (set(), set()))
            rules.add(rule_id)
            sources.add(raw)
    return [
        (row["nct_id"], "STUDIES", cid, json.dumps(sorted(r)), json.dumps(sorted(s)))
        for cid, (r, s) in sorted(found.items())
    ]


def fixed_rows(row):
    """Rows that do not depend on the interpretation: the trial, its sponsor and interventions."""
    nct_id = row["nct_id"]
    trial = (nct_id, row.get("title"), row.get("status"), "|".join(row.get("phases") or []),
             row.get("start_date"))
    interventions, spellings = {}, defaultdict(set)
    for item in row.get("interventions") or []:
        name = (item.get("name") or "").strip()
        if not name:
            continue
        iv_id = "iv:%s:%s" % (item.get("type"), norm_label(name))
        interventions.setdefault(iv_id, (iv_id, name, item.get("type")))
        spellings[iv_id].add(name)
    edges = [(nct_id, "TESTS", iv_id, json.dumps(["source"]), json.dumps(sorted(names)))
             for iv_id, names in sorted(spellings.items())]
    sponsor, sponsor_edge = None, None
    if (row.get("sponsor") or "").strip():
        name = sponsor_name(row["sponsor"])
        sponsor = ("sp:" + norm_label(name), name)
        sponsor_edge = (nct_id, "SPONSORED_BY", sponsor[0], json.dumps(["source"]),
                        json.dumps([row["sponsor"]]))
    return trial, interventions.values(), edges, sponsor, sponsor_edge


def connect(path):
    conn = sqlite3.connect(path, isolation_level=None)
    conn.execute("PRAGMA foreign_keys = OFF")
    return conn


def _put_rules(conn, interp):
    conn.execute("DELETE FROM rules")
    conn.executemany("INSERT INTO rules VALUES (?,?,?,?)", interp.as_rows())
    conn.execute("INSERT OR REPLACE INTO meta VALUES ('interpretation', ?)", (interp.version,))


def _sync_rules(conn, interp):
    """Change only the stored rules that differ from the new interpretation."""
    wanted = {row[0]: row for row in interp.as_rows()}
    current = {row[0]: row for row in conn.execute("SELECT * FROM rules")}
    conn.executemany("DELETE FROM rules WHERE rule_id=?", [(i,) for i in current if i not in wanted])
    conn.executemany("INSERT OR REPLACE INTO rules VALUES (?,?,?,?)",
                     [row for i, row in wanted.items() if current.get(i) != row])
    conn.execute("INSERT OR REPLACE INTO meta VALUES ('interpretation', ?)", (interp.version,))


def full_publish(path, rows, interp):
    """Build the whole graph from scratch under one interpretation."""
    prep = Prepared(rows)
    if os.path.exists(path):
        os.remove(path)
    conn = connect(path)
    labels = interp.concept_labels()
    conn.executescript(SCHEMA)
    conn.execute("BEGIN")
    try:
        edge_count = 0
        referenced = set()
        for row in prep.clean:
            trial, interventions, tests, sponsor, sponsor_edge = fixed_rows(row)
            conn.execute("INSERT INTO trials VALUES (?,?,?,?,?)", trial)
            conn.executemany("INSERT OR IGNORE INTO interventions VALUES (?,?,?)", interventions)
            conn.executemany("INSERT INTO edges VALUES (?,?,?,?,?)", tests)
            if sponsor:
                conn.execute("INSERT OR IGNORE INTO sponsors VALUES (?,?)", sponsor)
                conn.execute("INSERT INTO edges VALUES (?,?,?,?,?)", sponsor_edge)
            studies = study_edges(row, interp)
            conn.executemany("INSERT INTO edges VALUES (?,?,?,?,?)", studies)
            referenced.update(e[2] for e in studies)
            edge_count += len(studies)
        conn.executemany(
            "INSERT INTO concepts VALUES (?,?)",
            [(cid, concept_label(cid, labels, prep)) for cid in sorted(referenced)])
        _put_rules(conn, interp)
        conn.execute("INSERT INTO meta VALUES ('data_digest', ?)", (prep.digest,))
        conn.execute("COMMIT")
        rows_written = conn.total_changes
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()
    return {
        "trials": len(prep.clean), "quarantined": len(prep.quarantined),
        "studies_edges": edge_count, "concepts": len(referenced), "rows_written": rows_written,
    }


def stored_interpretation(conn):
    version = conn.execute("SELECT value FROM meta WHERE key='interpretation'").fetchone()[0]
    return interpret.build(version, conn.execute("SELECT * FROM rules").fetchall())


def republish(path, rows, new):
    """Move a published graph to a new interpretation, rewriting only what changed."""
    prep = Prepared(rows)
    conn = connect(path)
    try:
        digest = conn.execute("SELECT value FROM meta WHERE key='data_digest'").fetchone()[0]
        if digest != prep.digest:
            raise DataChanged("the trial data changed since this graph was published; run publish")
        old = stored_interpretation(conn)
        changed = sorted(k for k in prep.label_trials
                         if interpret.resolve(k, old) != interpret.resolve(k, new))
        affected = sorted({t for k in changed for t in prep.label_trials[k]})
        labels = new.concept_labels()
        conn.execute("BEGIN")
        try:
            deleted = inserted = 0
            for nct_id in affected:
                cur = conn.execute("DELETE FROM edges WHERE src=? AND rel='STUDIES'", (nct_id,))
                deleted += cur.rowcount
                edges = study_edges(prep.by_id[nct_id], new)
                conn.executemany("INSERT INTO edges VALUES (?,?,?,?,?)", edges)
                inserted += len(edges)
            referenced = {r[0] for r in conn.execute("SELECT DISTINCT dst FROM edges WHERE rel='STUDIES'")}
            current = dict(conn.execute("SELECT concept_id, label FROM concepts"))
            wanted = {cid: concept_label(cid, labels, prep) for cid in referenced}
            added = [(c, l) for c, l in wanted.items() if c not in current]
            renamed = [(l, c) for c, l in wanted.items() if c in current and current[c] != l]
            dropped = [(c,) for c in current if c not in wanted]
            conn.executemany("INSERT INTO concepts VALUES (?,?)", added)
            conn.executemany("UPDATE concepts SET label=? WHERE concept_id=?", renamed)
            conn.executemany("DELETE FROM concepts WHERE concept_id=?", dropped)
            _sync_rules(conn, new)
            conn.execute("COMMIT")
            rows_written = conn.total_changes
        except Exception:
            conn.execute("ROLLBACK")
            raise
    finally:
        conn.close()
    return {
        "from": old.version, "to": new.version, "labels_changed": len(changed),
        "trials_rewritten": len(affected), "studies_edges_deleted": deleted,
        "studies_edges_inserted": inserted, "concepts_added": len(added),
        "concepts_renamed": len(renamed), "concepts_dropped": len(dropped),
        "rows_written": rows_written,
    }


def dump(path):
    """Every table, sorted, as plain lists: two graphs are the same graph when their dumps are equal."""
    conn = connect(path)
    try:
        return {t: sorted(conn.execute("SELECT * FROM %s" % t).fetchall()) for t in TABLES}
    finally:
        conn.close()
