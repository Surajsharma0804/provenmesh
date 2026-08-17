"""ProvenMesh CLI — main entry point for all pipeline commands.

Usage:
    python -m provenmesh crawl           # Run discovery producers
    python -m provenmesh extract         # Start extraction workers
    python -m provenmesh resolve         # Start resolution workers
    python -m provenmesh export          # Export to Google Sheets
    python -m provenmesh run             # Run full pipeline
    python -m provenmesh worker <type>   # Start a specific worker type
"""

from __future__ import annotations

import asyncio
import signal

import click

from provenmesh.config.settings import get_settings
from provenmesh.observability.logging import get_logger, setup_logging

logger = get_logger(__name__)


def _setup() -> None:
    """Common setup for all commands."""
    settings = get_settings()
    logging_config = settings.configs_dir / "logging.yaml"
    setup_logging(logging_config if logging_config.exists() else None)


@click.group()
@click.version_option(version="1.0.0", prog_name="ProvenMesh")
def cli() -> None:
    """ProvenMesh — Evidence-first Intelligence Graph Pipeline."""
    _setup()


@cli.command()
@click.option(
    "--verticals", "-v", multiple=True,
    default=["startups", "products", "papers", "jobs", "news"],
)
def crawl(verticals: tuple[str, ...]) -> None:
    """Run discovery producers for specified verticals."""
    from provenmesh.crawler.producers.jobs import JobsProducer
    from provenmesh.crawler.producers.news import NewsProducer
    from provenmesh.crawler.producers.papers import PapersProducer
    from provenmesh.crawler.producers.products import ProductProducer
    from provenmesh.crawler.producers.startups import StartupProducer

    producer_map = {
        "startups": StartupProducer,
        "products": ProductProducer,
        "papers": PapersProducer,
        "jobs": JobsProducer,
        "news": NewsProducer,
    }

    async def run_producers() -> None:
        tasks = []
        for v in verticals:
            producer_cls = producer_map.get(v)
            if producer_cls:
                producer = producer_cls()
                tasks.append(producer.run())
                logger.info("producer_scheduled", vertical=v)
            else:
                logger.warning("unknown_vertical", vertical=v)

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for v, result in zip(verticals, results, strict=False):
            if isinstance(result, Exception):
                logger.error("producer_failed", vertical=v, error=str(result))
            else:
                logger.info("producer_completed", vertical=v, urls_discovered=result)

    asyncio.run(run_producers())


@cli.command()
@click.option("--workers", "-w", default=2, help="Number of worker instances")
@click.option("--worker-id-prefix", default="crawl", help="Worker ID prefix")
def fetch(workers: int, worker_id_prefix: str) -> None:
    """Start crawl fetch workers."""
    from provenmesh.workers.crawl_worker import CrawlWorker

    async def run_workers() -> None:
        shutdown = asyncio.Event()
        _setup_signal_handlers(shutdown)

        tasks = []
        for i in range(workers):
            worker = CrawlWorker(worker_id=f"{worker_id_prefix}-{i}")
            tasks.append(worker.run(shutdown))

        await asyncio.gather(*tasks)

    asyncio.run(run_workers())


@cli.command()
@click.option("--workers", "-w", default=2, help="Number of worker instances")
def extract(workers: int) -> None:
    """Start extraction workers."""
    from provenmesh.workers.extraction_worker import ExtractionWorker

    async def run_workers() -> None:
        shutdown = asyncio.Event()
        _setup_signal_handlers(shutdown)

        tasks = []
        for i in range(workers):
            worker = ExtractionWorker(worker_id=f"extraction-{i}")
            tasks.append(worker.run(shutdown))

        await asyncio.gather(*tasks)

    asyncio.run(run_workers())


@cli.command()
@click.option("--workers", "-w", default=2, help="Number of worker instances")
def resolve(workers: int) -> None:
    """Start resolution workers."""
    from provenmesh.workers.resolution_worker import ResolutionWorker

    async def run_workers() -> None:
        shutdown = asyncio.Event()
        _setup_signal_handlers(shutdown)

        tasks = []
        for i in range(workers):
            worker = ResolutionWorker(worker_id=f"resolver-{i}")
            tasks.append(worker.run(shutdown))

        await asyncio.gather(*tasks)

    asyncio.run(run_workers())


@cli.command()
def export() -> None:
    """Export validated records to Google Sheets."""
    from provenmesh.export.sheets import SheetsExporter

    async def run_export() -> None:
        exporter = SheetsExporter()
        results = await exporter.export_all()
        for tab, count in results.items():
            logger.info("export_result", tab=tab, records=count)

    asyncio.run(run_export())


@cli.command()
@click.option("--crawl-workers", default=2)
@click.option("--extract-workers", default=2)
@click.option("--resolve-workers", default=2)
@click.option("--auto-export", is_flag=True, default=False,
              help="Auto-export to Google Sheets periodically.")
@click.option("--export-interval", default=30,
              help="Auto-export interval in minutes (default: 30).")
def run(
    crawl_workers: int,
    extract_workers: int,
    resolve_workers: int,
    auto_export: bool,
    export_interval: int,
) -> None:
    """Run the full pipeline (producers + all worker types)."""
    from provenmesh.crawler.producers.jobs import JobsProducer
    from provenmesh.crawler.producers.news import NewsProducer
    from provenmesh.crawler.producers.papers import PapersProducer
    from provenmesh.crawler.producers.products import ProductProducer
    from provenmesh.crawler.producers.startups import StartupProducer
    from provenmesh.workers.crawl_worker import CrawlWorker
    from provenmesh.workers.extraction_worker import ExtractionWorker
    from provenmesh.workers.resolution_worker import ResolutionWorker

    async def auto_export_loop(shutdown: asyncio.Event, interval_minutes: int) -> None:
        """Periodically export to Google Sheets while the pipeline is running."""
        interval_secs = interval_minutes * 60
        logger.info("auto_export_started", interval_minutes=interval_minutes)
        while not shutdown.is_set():
            try:
                await asyncio.sleep(interval_secs)
                if shutdown.is_set():
                    break
                from provenmesh.export.sheets import SheetsExporter
                exporter = SheetsExporter()
                results = await exporter.export_all()
                logger.info("auto_export_done", results=results)
            except Exception as e:
                logger.warning("auto_export_error", error=str(e))

    async def run_all() -> None:
        shutdown = asyncio.Event()
        _setup_signal_handlers(shutdown)

        tasks = []

        # Start producers
        producers = [
            StartupProducer(), ProductProducer(), PapersProducer(),
            JobsProducer(), NewsProducer(),
        ]
        for p in producers:
            tasks.append(p.run())

        # Start workers
        for i in range(crawl_workers):
            worker = CrawlWorker(worker_id=f"crawl-{i}")
            tasks.append(worker.run(shutdown))

        for i in range(extract_workers):
            worker = ExtractionWorker(worker_id=f"extraction-{i}")
            tasks.append(worker.run(shutdown))

        for i in range(resolve_workers):
            worker = ResolutionWorker(worker_id=f"resolver-{i}")
            tasks.append(worker.run(shutdown))

        # Auto-export loop
        if auto_export:
            tasks.append(auto_export_loop(shutdown, export_interval))
            logger.info(
                "auto_export_enabled",
                interval_minutes=export_interval,
                message=f"Sheet will auto-update every {export_interval} min",
            )

        await asyncio.gather(*tasks, return_exceptions=True)

    asyncio.run(run_all())


@cli.command()
def migrate() -> None:
    """Run database migrations."""
    import subprocess
    subprocess.run(["alembic", "upgrade", "head"], check=True)  # noqa: S607


def _setup_signal_handlers(shutdown_event: asyncio.Event) -> None:
    """Setup graceful shutdown on SIGINT/SIGTERM."""
    def handler(sig: int, frame: object) -> None:
        logger.info("shutdown_signal_received", signal=sig)
        shutdown_event.set()

    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)


def main() -> None:
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()
