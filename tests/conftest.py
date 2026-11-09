import json
import os

import pytest

from trialgraph import interpret

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_rows():
    with open(os.path.join(ROOT, "data", "abbvie_trials.jsonl"), encoding="utf-8") as f:
        return [json.loads(line) for line in f]


@pytest.fixture(scope="session")
def rows():
    return load_rows()


@pytest.fixture(scope="session")
def v1():
    return interpret.load(os.path.join(ROOT, "interpretations", "v1.csv"))


@pytest.fixture(scope="session")
def v2():
    return interpret.load(os.path.join(ROOT, "interpretations", "v2.csv"))


def study(nct_id, conditions, interventions=(), sponsor="AbbVie", **over):
    row = {
        "nct_id": nct_id, "title": "t " + nct_id, "status": "COMPLETED", "start_date": "2020-01",
        "phases": ["PHASE2"], "sponsor": sponsor, "conditions": list(conditions),
        "interventions": [{"name": n, "type": "DRUG"} for n in interventions],
    }
    row.update(over)
    return row
