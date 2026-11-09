"""Data-quality checks run before anything is published.

A study that fails a quarantine check (Q...) is kept out of the graph and listed with its
reason code. A warning (W...) keeps the study in the graph and is counted in the report.
"""
import datetime
import re

NCT_ID = re.compile(r"^NCT\d{8}$")

QUARANTINE = {
    "Q001": "nct_id missing",
    "Q002": "nct_id is not NCT followed by eight digits",
    "Q003": "nct_id appears again (the first record is kept)",
    "Q004": "no condition labels",
    "Q005": "start_date is not YYYY, YYYY-MM or YYYY-MM-DD",
}
WARNINGS = {
    "W001": "start_date missing",
    "W002": "a condition label has unbalanced parentheses",
    "W003": "a condition label has non-ASCII characters",
    "W004": "sponsor missing",
}


def _valid_date(text):
    for fmt in ("%Y", "%Y-%m", "%Y-%m-%d"):
        try:
            datetime.datetime.strptime(text, fmt)
            return True
        except ValueError:
            continue
    return False


def check_study(row):
    """Return (quarantine codes, warning codes) for one study, ignoring duplicates."""
    quarantine, warnings = [], []
    nct_id = (row.get("nct_id") or "").strip()
    if not nct_id:
        quarantine.append("Q001")
    elif not NCT_ID.match(nct_id):
        quarantine.append("Q002")
    labels = [c for c in (row.get("conditions") or []) if c and c.strip()]
    if not labels:
        quarantine.append("Q004")
    start = row.get("start_date")
    if not start:
        warnings.append("W001")
    elif not _valid_date(start):
        quarantine.append("Q005")
    if any(c.count("(") != c.count(")") for c in labels):
        warnings.append("W002")
    if any(not c.isascii() for c in labels):
        warnings.append("W003")
    if not (row.get("sponsor") or "").strip():
        warnings.append("W004")
    return quarantine, warnings


def screen(rows):
    """Split rows into (clean rows, quarantined [(nct_id, codes)], warnings [(nct_id, codes)])."""
    clean, quarantined, warned, seen = [], [], [], set()
    for row in rows:
        quarantine, warnings = check_study(row)
        nct_id = (row.get("nct_id") or "").strip()
        if nct_id and not quarantine and nct_id in seen:
            quarantine.append("Q003")
        if quarantine:
            quarantined.append((nct_id, quarantine))
            continue
        seen.add(nct_id)
        if warnings:
            warned.append((nct_id, warnings))
        clean.append(row)
    return clean, quarantined, warned
