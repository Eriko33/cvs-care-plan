"""Fetch a single drug's SPL label XML from the DailyMed API.

Usage:
    python -m rag.fetch_label "Privigen" labels/privigen.xml
"""
import sys
from pathlib import Path

import requests

API_BASE = "https://dailymed.nlm.nih.gov/dailymed/services/v2"


def find_setid(drug_name: str) -> str:
    resp = requests.get(f"{API_BASE}/spls.json", params={"drug_name": drug_name})
    resp.raise_for_status()
    results = resp.json()["data"]
    if not results:
        raise ValueError(f"No SPL found for drug name '{drug_name}'")
    return results[0]["setid"]


def fetch_label_xml(drug_name: str, out_path: str) -> None:
    setid = find_setid(drug_name)
    resp = requests.get(f"{API_BASE}/spls/{setid}.xml")
    resp.raise_for_status()

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_bytes(resp.content)
    print(f"Saved '{drug_name}' (setid={setid}) -> {out_path}")


if __name__ == "__main__":
    name = sys.argv[1]
    output = sys.argv[2] if len(sys.argv) > 2 else f"labels/{name.lower().replace(' ', '_')}.xml"
    fetch_label_xml(name, output)
