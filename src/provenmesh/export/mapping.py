"""Export mapping — field-to-column mapping and header definitions (v2 §32).

Defines the exact column layout for each of the six Google Sheets tabs.
"""

from __future__ import annotations

# Column headers for each tab (excluding the 5 common columns)
TAB_HEADERS: dict[str, list[str]] = {
    "Startups": [
        "Canonical ID", "Entity Name", "Record Type", "Verification Status", "Source URL",
        "Description", "Founded Date", "Founders", "Headquarters",
        "Industry", "Total Funding", "Last Funding Round", "Employee Count",
        "Website", "Investors", "Products", "Tech Stack",
    ],
    "Products": [
        "Canonical ID", "Entity Name", "Record Type", "Verification Status", "Source URL",
        "Description", "Company", "Category", "Launch Date", "Pricing",
        "Pricing Model", "Features", "Platforms", "Website", "GitHub URL",
    ],
    "Papers": [
        "Canonical ID", "Entity Name", "Record Type", "Verification Status", "Source URL",
        "Title", "Abstract", "Authors", "Published Date", "ArXiv ID",
        "Categories", "GitHub URL", "GitHub Stars", "Citations", "Affiliations",
    ],
    "Jobs": [
        "Canonical ID", "Entity Name", "Record Type", "Verification Status", "Source URL",
        "Title", "Company", "Location", "Remote Policy", "Employment Type",
        "Salary Min", "Salary Max", "Skills", "Posted Date",
    ],
    "News": [
        "Canonical ID", "Entity Name", "Record Type", "Verification Status", "Source URL",
        "Title", "Summary", "Published Date", "Author", "Publisher",
        "Mentioned Entities", "Key Topics",
    ],
    "Entity Mapping Log": [
        "Canonical ID", "Entity Name", "Record Type", "Resolution Method",
        "Resolution Confidence", "Source Count", "Is Seed",
        "Verification Status", "Grounding Ratio", "Source URL",
    ],
}

# Field names (matching content dict keys) for each record type
FIELD_ORDER: dict[str, list[str]] = {
    "STARTUP": [
        "description", "foundedDate", "founders", "headquarters",
        "industry", "fundingTotal", "lastFundingRound", "employeeCount",
        "website", "investors", "products", "techStack",
    ],
    "PRODUCT": [
        "description", "company", "category", "launchDate", "pricing",
        "pricingModel", "features", "platforms", "website", "githubUrl",
    ],
    "PAPER": [
        "title", "abstract", "authors", "publishedDate", "arxivId",
        "categories", "githubUrl", "githubStars", "citations", "affiliations",
    ],
    "JOB": [
        "title", "company", "location", "remotePolicy", "employmentType",
        "salaryMin", "salaryMax", "skills", "postedDate",
    ],
    "NEWS_SIGNAL": [
        "title", "summary", "publishedDate", "author", "publisher",
        "mentionedEntities", "keyTopics",
    ],
}

# Map record types to tab names
RECORD_TYPE_TO_TAB: dict[str, str] = {
    "STARTUP": "Startups",
    "PRODUCT": "Products",
    "PAPER": "Papers",
    "JOB": "Jobs",
    "NEWS_SIGNAL": "News",
}


def get_headers(tab_name: str) -> list[str]:
    """Get column headers for a Sheets tab."""
    return TAB_HEADERS.get(tab_name, [])


def get_field_order(record_type: str) -> list[str]:
    """Get the ordered field names for a record type's columns."""
    return FIELD_ORDER.get(record_type, [])


def get_tab_name(record_type: str) -> str:
    """Get the Sheets tab name for a record type."""
    return RECORD_TYPE_TO_TAB.get(record_type, "Unknown")
