"""Google Sheets export — six-tab final output (PDF §12, v2 §30-32).

Tabs: Startups | Products | Papers | Jobs | News | Entity Mapping Log

Export rules:
    - Only records passing ALL three quality gates:
        1. Grounded (verification_status in [grounded, partial])
        2. Schema-valid (JSON schema validation passed)
        3. Resolved (canonical_id assigned)
    - Strip internal metadata before export
    - Entity Mapping Log tracks every resolution decision
    - Batch writes to Sheets API (500 rows per batch)
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from provenmesh.graph.repository import EntityRepository
from provenmesh.observability.logging import get_logger
from provenmesh.observability.metrics import EXPORT_FAILURE_TOTAL, EXPORT_SUCCESS_TOTAL
from provenmesh.storage.transactions import read_only_session

if TYPE_CHECKING:
    from provenmesh.graph.models import EntityRecord

logger = get_logger(__name__)


class SheetsExporter:
    """Exports validated, grounded, resolved entities to Google Sheets."""

    def __init__(self) -> None:
        self._batch_size = 500
        self._run_id = str(uuid.uuid4())

    async def export_all(self) -> dict[str, int]:
        """Export all entity types to their respective tabs.

        Returns dict of {tab_name: records_exported}.
        """
        results: dict[str, int] = {}

        type_tab_map = {
            "STARTUP": "Startups",
            "PRODUCT": "Products",
            "PAPER": "Papers",
            "JOB": "Jobs",
            "NEWS_SIGNAL": "News",
        }

        TAB_HEADERS = {
            "Startups": [
                "Canonical ID", "Company Name", "Type", "Status", "Source URL",
                "Description", "Founded Date", "Founders", "HQ",
                "Industry", "Funding Total", "Last Funding Round",
                "Employees", "Website", "Investors", "Products", "Tech Stack",
            ],
            "Products": [
                "Canonical ID", "Product Name", "Type", "Status", "Source URL",
                "Description", "Company", "Category", "Launch Date", "Pricing",
                "Pricing Model", "Features", "Platforms", "Website", "GitHub URL",
            ],
            "Papers": [
                "Canonical ID", "Paper Name", "Type", "Status", "Source URL",
                "Title", "Abstract", "Authors", "Published Date", "ArXiv ID",
                "Categories", "GitHub URL", "GitHub Stars", "Citations", "Affiliations",
            ],
            "Jobs": [
                "Canonical ID", "Job Title", "Type", "Status", "Source URL",
                "Title", "Company", "Location", "Remote Policy", "Employment Type",
                "Salary Min", "Salary Max", "Skills", "Posted Date",
            ],
            "News": [
                "Canonical ID", "Headline", "Type", "Status", "Source URL",
                "Title", "Summary", "Published Date", "Author", "Publisher",
                "Mentioned Entities", "Key Topics",
            ],
            "Entity Mapping Log": [
                "Canonical ID", "Entity Name", "Type", "Resolution Method",
                "Resolution Confidence", "Source Count", "Is Seed",
                "Verification Status", "Grounding Ratio", "Source URL",
            ],
        }

        # Setup: create all tabs and write headers (clears old data first)
        all_tabs = list(type_tab_map.values()) + ["Entity Mapping Log"]
        await self._setup_tabs(all_tabs, TAB_HEADERS)

        for record_type, tab_name in type_tab_map.items():
            try:
                count = await self._export_type(record_type, tab_name)
                results[tab_name] = count
                EXPORT_SUCCESS_TOTAL.labels(tab=tab_name).inc(count)
            except Exception as e:
                logger.error(
                    "export_tab_failed",
                    tab=tab_name,
                    error=str(e),
                )
                EXPORT_FAILURE_TOTAL.labels(tab=tab_name, reason=type(e).__name__).inc()
                results[tab_name] = 0

        # Export entity mapping log
        results["Entity Mapping Log"] = await self._export_mapping_log()

        logger.info("export_completed", results=results, run_id=self._run_id)
        return results

    async def _setup_tabs(
        self,
        tab_names: list[str],
        headers: dict[str, list[str]],
    ) -> None:
        """Create all tabs if missing and write their header rows."""
        from pathlib import Path
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build
        from provenmesh.config.settings import PROJECT_ROOT, get_settings

        settings = get_settings()
        if not settings.google_sheets_spreadsheet_id:
            return

        creds_path = settings.google_sheets_credentials_json
        resolved = Path(creds_path)
        if not resolved.is_absolute():
            resolved = PROJECT_ROOT / resolved

        creds = Credentials.from_service_account_file(
            str(resolved),
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
        service = build("sheets", "v4", credentials=creds)
        spreadsheet_id = settings.google_sheets_spreadsheet_id

        # Get existing sheet titles
        sheet_meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        existing = {s["properties"]["title"] for s in sheet_meta.get("sheets", [])}

        # Create missing tabs in one batchUpdate
        requests = []
        for tab_name in tab_names:
            if tab_name not in existing:
                requests.append({"addSheet": {"properties": {"title": tab_name}}})

        if requests:
            service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"requests": requests},
            ).execute()
            logger.info("sheet_tabs_created", count=len(requests))

        # Clear existing data and write headers to each tab
        for tab_name in tab_names:
            tab_headers = headers.get(tab_name, [])
            if not tab_headers:
                continue
            try:
                # Clear the tab first (avoids duplicate rows on re-run)
                service.spreadsheets().values().clear(
                    spreadsheetId=spreadsheet_id,
                    range=f"{tab_name}!A:Z",
                ).execute()
                # Write header row
                service.spreadsheets().values().update(
                    spreadsheetId=spreadsheet_id,
                    range=f"{tab_name}!A1",
                    valueInputOption="RAW",
                    body={"values": [tab_headers]},
                ).execute()
                logger.info("sheet_header_written", tab=tab_name)
            except Exception as e:
                logger.warning("sheet_header_failed", tab=tab_name, error=str(e))

    async def _export_type(self, record_type: str, tab_name: str) -> int:
        """Export all exportable records of a given type."""
        async with read_only_session() as session:
            repo = EntityRepository(session)
            offset = 0
            total = 0

            while True:
                entities = await repo.get_exportable(
                    record_type, self._batch_size, offset,
                )
                if not entities:
                    break

                rows = [self._entity_to_row(e) for e in entities]
                await self._write_batch(tab_name, rows)

                # Mark as exported
                canonical_ids = [e.canonical_id for e in entities]
                await repo.mark_exported(canonical_ids)
                await session.commit()

                total += len(entities)
                offset += self._batch_size

        return total

    def _entity_to_row(self, entity: EntityRecord) -> list[str]:
        """Convert an entity record to a flat row for Sheets export.

        Strips internal metadata (v2 §31).
        """
        content = entity.content or {}
        row: list[str] = []

        # Common fields
        row.append(str(entity.canonical_id))
        row.append(str(entity.entity_name))
        row.append(str(entity.record_type))
        row.append(str(entity.verification_status))
        row.append(str(entity.source_url))

        # Type-specific fields
        for field_name in self._get_field_order(entity.record_type):
            field_data = content.get(field_name, {})
            if isinstance(field_data, dict):
                row.append(str(field_data.get("value", "")))
            elif isinstance(field_data, list):
                values = [
                    str(item.get("value", "") if isinstance(item, dict) else item)
                    for item in field_data
                ]
                row.append("; ".join(values))
            else:
                row.append(str(field_data) if field_data else "")

        return row

    def _get_field_order(self, record_type: str) -> list[str]:
        """Get ordered field names for a record type's sheet columns."""
        field_orders: dict[str, list[str]] = {
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
        return field_orders.get(record_type, [])

    async def _export_mapping_log(self) -> int:
        """Export the entity mapping log (PDF §12, tab 6).

        Lists every resolution decision for auditability.
        """
        async with read_only_session() as session:
            EntityRepository(session)
            # Get all resolved entities for the log
            from sqlalchemy import select

            from provenmesh.graph.models import EntityRecord

            result = await session.execute(
                select(EntityRecord)
                .where(EntityRecord.resolution_method != "unresolved")
                .order_by(EntityRecord.created_at)
                .limit(50000)
            )
            entities = result.scalars().all()

            rows = []
            for e in entities:
                rows.append([
                    e.canonical_id,
                    e.entity_name,
                    e.record_type,
                    e.resolution_method,
                    str(round(e.resolution_confidence or 0.0, 3)),
                    str(e.source_count or 0),
                    "Yes" if e.is_seed else "No",
                    e.verification_status or "",
                    str(round(e.grounding_ratio or 0.0, 2)),
                    e.source_url or "",
                ])

            if rows:
                await self._write_batch("Entity Mapping Log", rows)

            return len(rows)

    async def _write_batch(self, tab_name: str, rows: list[list[str]]) -> None:
        """Write a batch of rows to a Google Sheets tab.

        Uses the Sheets API v4 batchUpdate for efficiency.
        """
        from provenmesh.config.settings import get_settings
        settings = get_settings()

        if not settings.google_sheets_spreadsheet_id:
            logger.warning("sheets_export_skipped", reason="no spreadsheet ID configured")
            return

        try:
            from pathlib import Path

            from google.oauth2.service_account import Credentials
            from googleapiclient.discovery import build
            from provenmesh.config.settings import PROJECT_ROOT

            creds_path = settings.google_sheets_credentials_json
            # Resolve relative paths against the project root
            resolved = Path(creds_path)
            if not resolved.is_absolute():
                resolved = PROJECT_ROOT / resolved

            creds = Credentials.from_service_account_file(
                str(resolved),
                scopes=["https://www.googleapis.com/auth/spreadsheets"],
            )
            service = build("sheets", "v4", credentials=creds)
            spreadsheet_id = settings.google_sheets_spreadsheet_id

            # Ensure the tab exists — create it if not
            try:
                sheet_meta = service.spreadsheets().get(
                    spreadsheetId=spreadsheet_id
                ).execute()
                existing_titles = {
                    s["properties"]["title"]
                    for s in sheet_meta.get("sheets", [])
                }
                if tab_name not in existing_titles:
                    body_add = {
                        "requests": [{
                            "addSheet": {
                                "properties": {"title": tab_name}
                            }
                        }]
                    }
                    service.spreadsheets().batchUpdate(
                        spreadsheetId=spreadsheet_id,
                        body=body_add,
                    ).execute()
                    logger.info("sheet_tab_created", tab=tab_name)
            except Exception as tab_err:
                logger.warning("sheet_tab_check_failed", tab=tab_name, error=str(tab_err))

            body = {"values": [[str(c) for c in row] for row in rows]}
            service.spreadsheets().values().append(
                spreadsheetId=spreadsheet_id,
                range=f"{tab_name}!A1",
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body=body,
            ).execute()

            logger.info(
                "sheets_batch_written",
                tab=tab_name,
                rows=len(rows),
            )

        except Exception as e:
            logger.error("sheets_write_failed", tab=tab_name, error=str(e))
            raise
