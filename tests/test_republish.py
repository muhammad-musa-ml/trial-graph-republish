import random

import pytest

from trialgraph import interpret, publish
from trialgraph.normalize import norm_label

from conftest import study


def build_both(tmp_path, rows, old, new):
    """Publish old, republish to new, and also publish new from scratch."""
    inc, full = str(tmp_path / "inc.db"), str(tmp_path / "full.db")
    publish.full_publish(inc, rows, old)
    stats = publish.republish(inc, rows, new)
    publish.full_publish(full, rows, new)
    return inc, full, stats


def interp(version, *rules):
    return interpret.build(version, list(rules))


ROWS = [
    study("NCT00000001", ["Hepatitis C", "Healthy"]),
    study("NCT00000002", ["Hepatitis C Virus (HCV)"]),
    study("NCT00000003", ["Gout"]),
    study("NCT00000004", ["Gout", "Combined"]),
]
BASE = [
    ("r1", "hepatitis c", "cond:hcv", "Hepatitis C"),
    ("r2", "healthy", "cond:healthy", "Healthy Volunteers"),
]


@pytest.mark.parametrize("name, new_rules, touched", [
    ("merge two raw labels", BASE + [("r3", "hepatitis c virus (hcv)", "cond:hcv", "Hepatitis C")],
     ["NCT00000002"]),
    ("exclude a label", [BASE[0], ("r2", "healthy", "-", "-")], ["NCT00000001"]),
    ("retarget a rule", [("r1", "hepatitis c", "cond:chc", "Chronic Hepatitis C"), BASE[1]],
     ["NCT00000001"]),
    ("split one label", BASE + [("r4", "combined", "cond:a;cond:b", "A;B")], ["NCT00000004"]),
    ("new rule id only", [("r9", "hepatitis c", "cond:hcv", "Hepatitis C"), BASE[1]], ["NCT00000001"]),
    ("rule removed", [BASE[0]], ["NCT00000001"]),
    ("concept renamed, no edge changes", [("r1", "hepatitis c", "cond:hcv", "Hepatitis C Virus"), BASE[1]], []),
    ("unmapped label gets a rule", BASE + [("r5", "gout", "cond:gout", "Gout")],
     ["NCT00000003", "NCT00000004"]),
    ("nothing changes", BASE, []),
])
def test_republish_equals_a_full_rebuild_and_touches_only_the_affected_trials(tmp_path, name, new_rules, touched):
    old, new = interp("old", *BASE), interp("new", *new_rules)
    inc, full, stats = build_both(tmp_path, ROWS, old, new)
    assert stats["trials_rewritten"] == len(touched), name
    assert publish.dump(inc) == publish.dump(full), name


def test_node_only_change_rewrites_no_edges(tmp_path):
    old = interp("old", *BASE)
    new = interp("new", ("r1", "hepatitis c", "cond:hcv", "Hepatitis C Virus"), BASE[1])
    inc, full, stats = build_both(tmp_path, ROWS, old, new)
    assert stats["studies_edges_deleted"] == stats["studies_edges_inserted"] == 0
    assert stats["concepts_renamed"] == 1


def test_concept_with_no_remaining_edge_is_dropped(tmp_path):
    old = interp("old", *BASE)
    new = interp("new", BASE[0], ("r2", "healthy", "-", "-"))
    inc, full, stats = build_both(tmp_path, ROWS, old, new)
    assert stats["concepts_dropped"] == 1
    assert ("cond:healthy",) not in publish.connect(inc).execute("SELECT concept_id FROM concepts").fetchall()


def test_republishing_the_same_interpretation_twice_changes_nothing(tmp_path):
    old, new = interp("old", *BASE), interp("new", *BASE, ("r3", "gout", "cond:gout", "Gout"))
    inc, full, first = build_both(tmp_path, ROWS, old, new)
    again = publish.republish(inc, ROWS, new)
    assert first["trials_rewritten"] == 2
    assert again["trials_rewritten"] == 0 and again["labels_changed"] == 0
    assert publish.dump(inc) == publish.dump(full)


def test_changed_data_is_refused(tmp_path):
    inc = str(tmp_path / "inc.db")
    publish.full_publish(inc, ROWS, interp("old", *BASE))
    with pytest.raises(publish.DataChanged):
        publish.republish(inc, ROWS + [study("NCT00000009", ["Gout"])], interp("new", *BASE))


def test_a_failed_republish_leaves_the_graph_as_it_was(tmp_path, monkeypatch):
    inc = str(tmp_path / "inc.db")
    publish.full_publish(inc, ROWS, interp("old", *BASE))
    before = publish.dump(inc)

    def boom(*args, **kwargs):
        raise RuntimeError("stop after the edges were rewritten")

    monkeypatch.setattr(publish, "concept_label", boom)
    new = interp("new", *BASE, ("r3", "gout", "cond:gout", "Gout"))
    with pytest.raises(RuntimeError):
        publish.republish(inc, ROWS, new)
    assert publish.dump(inc) == before


def test_real_data_v1_to_v2_equals_a_full_rebuild(tmp_path, rows, v1, v2):
    inc, full, stats = build_both(tmp_path, rows, v1, v2)
    assert publish.dump(inc) == publish.dump(full)
    assert 0 < stats["trials_rewritten"] < len(rows)


def test_real_data_rewritten_trials_are_exactly_those_whose_edges_differ(tmp_path, rows, v1, v2):
    """Compare against a brute-force diff of every trial's STUDIES edges."""
    prep = publish.Prepared(rows)
    differing = {
        r["nct_id"] for r in prep.clean
        if publish.study_edges(r, v1) != publish.study_edges(r, v2)
    }
    inc, full, stats = build_both(tmp_path, rows, v1, v2)
    assert stats["trials_rewritten"] >= len(differing)
    # every trial whose edges differ was rewritten; a trial rewritten without a difference is
    # allowed only when its label's lineage changed, which study_edges reports as a difference.
    assert stats["trials_rewritten"] == len(differing)


def random_rules(rng, base, keys):
    """Mutate a rule table: drop, retarget, exclude or add a rule."""
    rules = {key: [rule.rule_id, list(rule.concept_ids)] for key, rule in base.rules.items()}
    names = dict(base.concept_labels())
    for _ in range(rng.randint(1, 6)):
        kind = rng.choice(["drop", "retarget", "exclude", "add", "rename"])
        if kind == "add":
            key = rng.choice(keys)
            if key not in rules:
                rules[key] = ["x%05d" % rng.randrange(10 ** 5), ["cond:n%d" % rng.randrange(8)]]
        elif kind == "rename" and names:
            names[rng.choice(sorted(names))] = "Renamed %d" % rng.randrange(10 ** 4)
        elif rules:
            key = rng.choice(sorted(rules))
            if kind == "drop":
                del rules[key]
            elif kind == "retarget":
                rules[key][1] = ["cond:n%d" % rng.randrange(8)]
            elif kind == "exclude":
                rules[key][1] = ["-"]
    rows = []
    for key, (rule_id, ids) in rules.items():
        labels = ["-" if cid == "-" else names.setdefault(cid, "Concept " + cid) for cid in ids]
        rows.append((rule_id, key, ";".join(ids), ";".join(labels)))
    return interpret.build("rand", rows)


def random_pair(rows, v1, v2, seed):
    rng = random.Random(seed)
    subset = rows[::4]
    keys = sorted({norm_label(c) for r in subset for c in r["conditions"] if c.strip()})
    old = random_rules(rng, rng.choice([v1, v2]), keys)
    return subset, old, random_rules(rng, old, keys)


@pytest.mark.parametrize("seed", range(25))
def test_random_rule_changes_on_real_data_equal_a_full_rebuild(tmp_path, rows, v1, v2, seed):
    subset, old, new = random_pair(rows, v1, v2, seed)
    inc, full, stats = build_both(tmp_path, subset, old, new)
    assert publish.dump(inc) == publish.dump(full)


def test_the_random_changes_are_not_vacuous(rows, v1, v2):
    """Most seeds must change what some label means, or the equality test above proves nothing."""
    moved = 0
    for seed in range(25):
        subset, old, new = random_pair(rows, v1, v2, seed)
        keys = {norm_label(c) for r in subset for c in r["conditions"] if c.strip()}
        if any(interpret.resolve(k, old) != interpret.resolve(k, new) for k in keys):
            moved += 1
    assert moved >= 15
