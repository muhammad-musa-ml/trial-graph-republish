"""An interpretation is a versioned table of rules: a normalized condition label and the
concept (or concepts) it stands for. Labels with no rule become a concept of their own.

CSV columns: rule_id, match_key, concept_id, concept_label
  - match_key must already be in baseline-normalized form (see normalize.norm_label)
  - one label can stand for several concepts: ids and labels are joined with ';'
  - concept_id '-' (with label '-') means the label is not a condition and gets no edge
"""
import csv
import os
from dataclasses import dataclass

from .normalize import norm_label

EXCLUDE = "-"
HEADER = ["rule_id", "match_key", "concept_id", "concept_label"]


@dataclass(frozen=True)
class Rule:
    rule_id: str
    match_key: str
    concept_ids: tuple
    labels: tuple

    @property
    def excluded(self):
        return self.concept_ids == (EXCLUDE,)


@dataclass(frozen=True)
class Interpretation:
    version: str
    rules: dict  # match_key -> Rule

    def concept_labels(self):
        return {
            cid: label
            for rule in self.rules.values() if not rule.excluded
            for cid, label in zip(rule.concept_ids, rule.labels)
        }

    def as_rows(self):
        """The rules as the (rule_id, match_key, concept_id, concept_label) rows they came from."""
        return sorted(
            (r.rule_id, r.match_key, ";".join(r.concept_ids), ";".join(r.labels))
            for r in self.rules.values()
        )


def build(version, rows):
    """Validate (rule_id, match_key, concept_id, concept_label) rows and return an Interpretation."""
    rules, seen_ids, labels = {}, set(), {}
    for rule_id, key, concept_id, label in rows:
        if rule_id in seen_ids:
            raise ValueError("duplicate rule_id %s" % rule_id)
        seen_ids.add(rule_id)
        if key in rules:
            raise ValueError("%s: match_key %r already has rule %s" % (rule_id, key, rules[key].rule_id))
        if norm_label(key) != key:
            raise ValueError("%s: match_key %r is not in normalized form" % (rule_id, key))
        ids, names = tuple(concept_id.split(";")), tuple(label.split(";"))
        if len(ids) != len(names):
            raise ValueError("%s: %d concept ids but %d labels" % (rule_id, len(ids), len(names)))
        if EXCLUDE in ids and ids != (EXCLUDE,):
            raise ValueError("%s: '-' cannot be combined with other concepts" % rule_id)
        for cid, name in zip(ids, names):
            if cid == EXCLUDE:
                continue
            if not cid.startswith("cond:"):
                raise ValueError("%s: concept id %r must start with 'cond:'" % (rule_id, cid))
            if labels.setdefault(cid, name) != name:
                raise ValueError("%s: concept %s has two labels, %r and %r" % (rule_id, cid, labels[cid], name))
        rules[key] = Rule(rule_id, key, ids, names)
    return Interpretation(version, rules)


def load(path):
    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        if next(reader) != HEADER:
            raise ValueError("%s: header must be %s" % (path, ",".join(HEADER)))
        rows = [tuple(r) for r in reader if r]
    version = os.path.splitext(os.path.basename(path))[0]
    return build(version, rows)


def resolve(key, interpretation):
    """Concepts a normalized label stands for: sorted (concept_id, rule_id) pairs."""
    rule = interpretation.rules.get(key)
    if rule is None:
        return (("raw:" + key, "auto"),)
    if rule.excluded:
        return ()
    return tuple(sorted((cid, rule.rule_id) for cid in rule.concept_ids))
