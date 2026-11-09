import json
import sqlite3

from trialgraph import interpret, publish

from conftest import study


def table(path, sql, *args):
    conn = sqlite3.connect(path)
    try:
        return conn.execute(sql, args).fetchall()
    finally:
        conn.close()


def small_interp():
    return interpret.build("t", [
        ("r1", "hepatitis c", "cond:hcv", "Hepatitis C"),
        ("r2", "hepatitis c virus (hcv)", "cond:hcv", "Hepatitis C"),
        ("r3", "healthy", "-", "-"),
        ("r4", "combined", "cond:a;cond:b", "A;B"),
    ])


def test_two_spellings_of_one_concept_make_one_edge_with_both_lineages(tmp_path):
    db = str(tmp_path / "g.db")
    rows = [study("NCT00000001", ["Hepatitis C", "Hepatitis C Virus (HCV)"])]
    publish.full_publish(db, rows, small_interp())
    edges = table(db, "SELECT dst, rule_ids, source_labels FROM edges WHERE rel='STUDIES'")
    assert len(edges) == 1
    dst, rule_ids, labels = edges[0]
    assert dst == "cond:hcv"
    assert json.loads(rule_ids) == ["r1", "r2"]
    assert json.loads(labels) == ["Hepatitis C", "Hepatitis C Virus (HCV)"]


def test_excluded_label_has_no_edge_and_unmapped_label_keeps_its_own_spelling(tmp_path):
    db = str(tmp_path / "g.db")
    rows = [study("NCT00000001", ["Healthy", "Gout"]), study("NCT00000002", ["gout "])]
    publish.full_publish(db, rows, small_interp())
    assert table(db, "SELECT dst, rule_ids FROM edges WHERE rel='STUDIES' ORDER BY src") == [
        ("raw:gout", '["auto"]'), ("raw:gout", '["auto"]')]
    assert table(db, "SELECT label FROM concepts") == [("Gout",)]


def test_one_label_can_make_edges_to_several_concepts(tmp_path):
    db = str(tmp_path / "g.db")
    publish.full_publish(db, [study("NCT00000001", ["Combined"])], small_interp())
    assert table(db, "SELECT dst FROM edges WHERE rel='STUDIES' ORDER BY dst") == [("cond:a",), ("cond:b",)]


def test_sponsor_spellings_share_one_node_and_interventions_are_deduplicated(tmp_path):
    db = str(tmp_path / "g.db")
    rows = [
        study("NCT00000001", ["Gout"], ["Drug X", "drug x"], sponsor="AbbVie"),
        study("NCT00000002", ["Gout"], ["Drug X"], sponsor="AbbVie (prior sponsor, Abbott)"),
    ]
    publish.full_publish(db, rows, small_interp())
    assert table(db, "SELECT sponsor_id, name FROM sponsors") == [("sp:abbvie", "AbbVie")]
    assert table(db, "SELECT COUNT(*) FROM edges WHERE rel='SPONSORED_BY'") == [(2,)]
    assert table(db, "SELECT COUNT(*) FROM interventions") == [(1,)]


def test_quarantined_studies_are_not_published(tmp_path):
    db = str(tmp_path / "g.db")
    rows = [study("NCT00000001", ["Gout"]), study("NCT00000001", ["Gout"]), study("bad", ["Gout"]),
            study("NCT00000003", [])]
    stats = publish.full_publish(db, rows, small_interp())
    assert stats["trials"] == 1 and stats["quarantined"] == 3
    assert table(db, "SELECT nct_id FROM trials") == [("NCT00000001",)]


def test_every_edge_has_lineage_on_the_real_data(tmp_path, rows, v1):
    db = str(tmp_path / "g.db")
    stats = publish.full_publish(db, rows, v1)
    assert stats["trials"] + stats["quarantined"] == len(rows)
    assert table(db, "SELECT COUNT(*) FROM edges WHERE rule_ids='[]' OR source_labels='[]'") == [(0,)]
    # every STUDIES edge ends at a published concept, and every concept has an edge
    assert table(db, "SELECT COUNT(*) FROM edges e LEFT JOIN concepts c ON c.concept_id=e.dst "
                     "WHERE e.rel='STUDIES' AND c.concept_id IS NULL") == [(0,)]
    assert table(db, "SELECT COUNT(*) FROM concepts c WHERE NOT EXISTS "
                     "(SELECT 1 FROM edges e WHERE e.dst=c.concept_id)") == [(0,)]


def test_publish_is_repeatable(tmp_path, rows, v1):
    a, b = str(tmp_path / "a.db"), str(tmp_path / "b.db")
    publish.full_publish(a, rows, v1)
    publish.full_publish(b, rows, v1)
    assert publish.dump(a) == publish.dump(b)
