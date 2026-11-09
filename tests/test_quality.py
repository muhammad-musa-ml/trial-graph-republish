from trialgraph.normalize import norm_label, sponsor_name
from trialgraph.quality import check_study, screen


def study(**over):
    row = {
        "nct_id": "NCT00000001",
        "title": "t",
        "status": "COMPLETED",
        "start_date": "2020-01",
        "phases": [],
        "sponsor": "AbbVie",
        "conditions": ["Psoriasis"],
        "interventions": [],
    }
    row.update(over)
    return row


def test_norm_label_apostrophes_case_and_spaces():
    assert norm_label("Crohn´s  Disease ") == "crohn's disease"
    assert norm_label("Crohn’s Disease") == norm_label("CROHN'S DISEASE")


def test_sponsor_name_drops_the_parenthetical():
    assert sponsor_name("AbbVie (prior sponsor, Abbott)") == "AbbVie"
    assert sponsor_name("AbbVie") == "AbbVie"


def test_clean_study_has_no_codes():
    assert check_study(study()) == ([], [])


def test_each_quarantine_code_fires():
    assert check_study(study(nct_id=""))[0] == ["Q001"]
    assert check_study(study(nct_id="NCT123"))[0] == ["Q002"]
    assert check_study(study(conditions=[]))[0] == ["Q004"]
    assert check_study(study(conditions=["  "]))[0] == ["Q004"]
    assert check_study(study(start_date="2020-13"))[0] == ["Q005"]
    assert check_study(study(start_date="20-01"))[0] == ["Q005"]


def test_each_warning_code_fires_and_keeps_the_study():
    assert check_study(study(start_date=None)) == ([], ["W001"])
    assert check_study(study(conditions=["Rheumatoid Arthritis (RA"])) == ([], ["W002"])
    assert check_study(study(conditions=["Crohn´s Disease"])) == ([], ["W003"])
    assert check_study(study(sponsor=None)) == ([], ["W004"])


def test_valid_partial_dates_pass():
    for date in ("2020", "2020-02", "2020-02-29"):
        assert check_study(study(start_date=date))[0] == []


def test_screen_quarantines_a_repeated_id_and_keeps_the_first():
    first = study(title="first")
    second = study(title="second")
    clean, quarantined, warned = screen([first, second, study(nct_id="bad")])
    assert [r["title"] for r in clean] == ["first"]
    assert quarantined == [("NCT00000001", ["Q003"]), ("bad", ["Q002"])]
    assert warned == []


def test_screen_reports_warnings_for_kept_studies():
    clean, quarantined, warned = screen([study(start_date=None)])
    assert len(clean) == 1 and quarantined == []
    assert warned == [("NCT00000001", ["W001"])]
