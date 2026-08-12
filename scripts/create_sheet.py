"""Create Google Sheet with the six required tabs.

Usage:
    python scripts/create_sheet.py

Requires:
    GOOGLE_SHEETS_CREDENTIALS_JSON environment variable pointing to
    the service account credentials JSON file.
"""

from __future__ import annotations

import json
import os
import sys

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build


TAB_NAMES = [
    "Startups",
    "Products",
    "Papers",
    "Jobs",
    "News",
    "Entity Mapping Log",
]

TAB_HEADERS = {
    "Startups": [
        "Canonical ID", "Entity Name", "Record Type", "Verification Status",
        "Source URL", "Description", "Founded Date", "Founders", "Headquarters",
        "Industry", "Total Funding", "Last Funding Round", "Employee Count",
        "Website", "Investors", "Products", "Tech Stack",
    ],
    "Products": [
        "Canonical ID", "Entity Name", "Record Type", "Verification Status",
        "Source URL", "Description", "Company", "Category", "Launch Date",
        "Pricing", "Pricing Model", "Features", "Platforms", "Website", "GitHub URL",
    ],
    "Papers": [
        "Canonical ID", "Entity Name", "Record Type", "Verification Status",
        "Source URL", "Title", "Abstract", "Authors", "Published Date",
        "ArXiv ID", "Categories", "GitHub URL", "GitHub Stars", "Citations", "Affiliations",
    ],
    "Jobs": [
        "Canonical ID", "Entity Name", "Record Type", "Verification Status",
        "Source URL", "Title", "Company", "Location", "Remote Policy",
        "Employment Type", "Salary Min", "Salary Max", "Skills", "Posted Date",
    ],
    "News": [
        "Canonical ID", "Entity Name", "Record Type", "Verification Status",
        "Source URL", "Title", "Summary", "Published Date", "Author",
        "Publisher", "Mentioned Entities", "Key Topics",
    ],
    "Entity Mapping Log": [
        "Canonical ID", "Entity Name", "Record Type", "Resolution Method",
        "Resolution Confidence", "Source Count", "Is Seed",
        "Verification Status", "Grounding Ratio", "Source URL",
    ],
}


def create_sheet() -> str:
    """Create a new Google Sheet with all six tabs and headers."""
    creds_path = os.getenv("GOOGLE_SHEETS_CREDENTIALS_JSON")
    if not creds_path:
        print("ERROR: Set GOOGLE_SHEETS_CREDENTIALS_JSON env var")
        sys.exit(1)

    creds = Credentials.from_service_account_file(
        creds_path,
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    service = build("sheets", "v4", credentials=creds)

    # Create spreadsheet with tabs
    body = {
        "properties": {"title": "ProvenMesh Intelligence Graph Export"},
        "sheets": [
            {
                "properties": {
                    "title": tab_name,
                    "index": i,
                    "gridProperties": {"frozenRowCount": 1},
                }
            }
            for i, tab_name in enumerate(TAB_NAMES)
        ],
    }

    spreadsheet = service.spreadsheets().create(body=body).execute()
    sheet_id = spreadsheet["spreadsheetId"]
    print(f"✓ Created spreadsheet: https://docs.google.com/spreadsheets/d/{sheet_id}")

    # Write headers to each tab
    data = []
    for tab_name in TAB_NAMES:
        headers = TAB_HEADERS.get(tab_name, [])
        data.append({
            "range": f"'{tab_name}'!A1",
            "values": [headers],
        })

    service.spreadsheets().values().batchUpdate(
        spreadsheetId=sheet_id,
        body={"valueInputOption": "RAW", "data": data},
    ).execute()

    print(f"✓ Headers written to all {len(TAB_NAMES)} tabs")
    return sheet_id


if __name__ == "__main__":
    sid = create_sheet()
    print(f"\nSet this in .env:")
    print(f"GOOGLE_SHEET_ID={sid}")
