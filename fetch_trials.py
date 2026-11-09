"""Download the studies whose lead sponsor matches AbbVie from the public
ClinicalTrials.gov v2 API and write one trimmed JSON line per study.

    python fetch_trials.py data/abbvie_trials.jsonl

The output file is committed, so nothing else in this repository needs the network.
"""
import json
import sys
import time
import urllib.parse
import urllib.request

API = "https://clinicaltrials.gov/api/v2"
FIELDS = "|".join([
    "NCTId", "BriefTitle", "OverallStatus", "Phase", "StartDate",
    "LeadSponsorName", "Condition", "InterventionName", "InterventionType",
])


def get(url):
    with urllib.request.urlopen(url, timeout=60) as response:
        return json.load(response)


def trim(study):
    p = study.get("protocolSection", {})
    ident = p.get("identificationModule", {})
    return {
        "nct_id": ident.get("nctId"),
        "title": ident.get("briefTitle"),
        "status": p.get("statusModule", {}).get("overallStatus"),
        "start_date": p.get("statusModule", {}).get("startDateStruct", {}).get("date"),
        "phases": p.get("designModule", {}).get("phases", []),
        "sponsor": p.get("sponsorCollaboratorsModule", {}).get("leadSponsor", {}).get("name"),
        "conditions": p.get("conditionsModule", {}).get("conditions", []),
        "interventions": [
            {"name": i.get("name"), "type": i.get("type")}
            for i in p.get("armsInterventionsModule", {}).get("interventions", [])
        ],
    }


def main(out_path):
    stamp = get(API + "/version")["dataTimestamp"]
    params = {"query.lead": "AbbVie", "pageSize": "500", "fields": FIELDS}
    token = None
    rows = []
    while True:
        query = dict(params)
        if token:
            query["pageToken"] = token
        page = get(API + "/studies?" + urllib.parse.urlencode(query, safe="|"))
        rows.extend(trim(s) for s in page["studies"])
        token = page.get("nextPageToken")
        if not token:
            break
        time.sleep(0.5)
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")
    print("studies", len(rows), "api_data_timestamp", stamp)


if __name__ == "__main__":
    main(sys.argv[1])
