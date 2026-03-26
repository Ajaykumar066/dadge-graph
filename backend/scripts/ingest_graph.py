"""
ingest_graph.py

Entry point to run the full graph ingestion pipeline.
Run this script to populate Neo4j from scratch.

Usage:
    python scripts/ingest_graph.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# This must run before any app imports
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

# Now safe to import app modules
from app.core.database import get_driver, close_driver
from app.graph.ingest import (
    create_constraints,
    clear_database,
    ingest_business_partners,
    ingest_products,
    ingest_plants,
    ingest_sales_orders,
    ingest_sales_order_items,
    ingest_schedule_lines,
    ingest_outbound_deliveries,
    ingest_outbound_delivery_items,
    ingest_billing_documents,
    ingest_billing_document_items,
    ingest_journal_entries,
    ingest_payments,
    create_relationships,
    validate_graph,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def main():
    logger.info("=" * 55)
    logger.info("  SAP O2C Graph Ingestion Pipeline")
    logger.info("=" * 55)

    driver = get_driver()

    try:
        # ── Phase 1: Schema ──────────────────────────────────
        logger.info("\n[Phase 1] Schema setup")
        create_constraints(driver)

        # ── Phase 2: Clear ───────────────────────────────────
        logger.info("\n[Phase 2] Clearing existing data")
        clear_database(driver)

        # ── Phase 3: Root nodes ──────────────────────────────
        logger.info("\n[Phase 3] Root nodes")
        ingest_business_partners(driver)
        ingest_products(driver)

        logger.info("\n" + "=" * 55)
        logger.info("  ✅ Phase 3 complete — root nodes loaded")
        logger.info("  Next: run Step 5 to add remaining nodes")
        logger.info("=" * 55)

        # ── Phase 4: O2C flow — layer 1 ─────────────────────
        logger.info("\n[Phase 4] O2C flow nodes — layer 1")
        ingest_plants(driver)
        ingest_sales_orders(driver)
        ingest_sales_order_items(driver)

        logger.info("\n" + "=" * 55)
        logger.info("  ✅ Phase 4 complete")
        logger.info("  Next: run Step 6 to add delivery + billing nodes")
        logger.info("=" * 55)

        # ── Phase 5: Delivery layer ──────────────────────────
        logger.info("\n[Phase 5] Delivery layer")
        ingest_schedule_lines(driver)
        ingest_outbound_deliveries(driver)
        ingest_outbound_delivery_items(driver)

        logger.info("\n" + "=" * 55)
        logger.info("  ✅ Phase 5 complete")
        logger.info("  Next: run Step 7 to add billing + payment nodes")
        logger.info("=" * 55)

        # ── Phase 6: Billing + Payment layer ────────────────
        logger.info("\n[Phase 6] Billing and payment layer")
        ingest_billing_documents(driver)
        ingest_billing_document_items(driver)
        ingest_journal_entries(driver)
        ingest_payments(driver)

        logger.info("\n" + "=" * 55)
        logger.info("  ✅ Phase 6 complete — all nodes loaded")
        logger.info("  Next: Step 8 will create all relationships")
        logger.info("=" * 55)

        # ── Phase 7: Relationships ───────────────────────────
        logger.info("\n[Phase 7] Creating relationships")
        create_relationships(driver)

        logger.info("\n" + "=" * 55)
        logger.info("  ✅ Full graph ingestion complete!")
        logger.info("=" * 55)

        # ── Phase 8: Validation ──────────────────────────────
        logger.info("\n[Phase 8] Validation")
        validate_graph(driver)

    except Exception as e:
        logger.error(f"\n❌ Pipeline failed: {e}")
        raise
    finally:
        close_driver()


if __name__ == "__main__":
    main()