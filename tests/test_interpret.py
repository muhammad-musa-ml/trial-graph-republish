import os

import pytest

from trialgraph import interpret
from trialgraph.normalize import norm_label

HERE = os.path.dirname(__file__)
ROOT = os.path.dirname(HERE)


def rows(*items):
    return list(items)


def test_shipped_interpretations_load():
    for name in ("v1", "v2"):
        interp = interpret.load(os.path.join(ROOT, "interpretations", name + ".csv"))
        assert interp.version == name
        assert len(interp.rules) > 20


def test_resolve_rule_unmapped_and_excluded():
    interp = interpret.build("t", rows(
        ("r1", "psoriasis", "cond:psoriasis", "Psoriasis"),
        ("r2", "healthy", "-", "-"),
        ("r3", "multi", "cond:a;cond:b", "A;B"),
    ))
    assert interpret.resolve("psoriasis", interp) == (("cond:psoriasis", "r1"),)
    assert interpret.resolve("healthy", interp) == ()
    assert interpret.resolve("multi", interp) == (("cond:a", "r3"), ("cond:b", "r3"))
    assert interpret.resolve("gout", interp) == (("raw:gout", "auto"),)


def test_concept_labels_skip_exclusions():
    interp = interpret.build("t", rows(
        ("r1", "a", "cond:a", "A"), ("r2", "b", "-", "-")))
    assert interp.concept_labels() == {"cond:a": "A"}


@pytest.mark.parametrize("bad, message", [
    ([("r1", "a", "cond:a", "A"), ("r1", "b", "cond:b", "B")], "duplicate rule_id"),
    ([("r1", "a", "cond:a", "A"), ("r2", "a", "cond:b", "B")], "already has rule"),
    ([("r1", "A", "cond:a", "A")], "not in normalized form"),
    ([("r1", "a", "cond:a;cond:b", "A")], "2 concept ids but 1 labels"),
    ([("r1", "a", "cond:a;-", "A;-")], "cannot be combined"),
    ([("r1", "a", "disease-a", "A")], "must start with 'cond:'"),
    ([("r1", "a", "cond:a", "A"), ("r2", "b", "cond:a", "Other")], "two labels"),
])
def test_invalid_rule_tables_are_refused(bad, message):
    with pytest.raises(ValueError, match=message):
        interpret.build("t", bad)


def test_every_shipped_match_key_is_normalized():
    for name in ("v1", "v2"):
        interp = interpret.load(os.path.join(ROOT, "interpretations", name + ".csv"))
        assert all(norm_label(k) == k for k in interp.rules)


def test_rows_round_trip():
    interp = interpret.load(os.path.join(ROOT, "interpretations", "v2.csv"))
    again = interpret.build("v2", interp.as_rows())
    assert again == interp
