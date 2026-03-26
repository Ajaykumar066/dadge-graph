"""
reader.py

Utility to read partitioned JSONL files (part-*.jsonl) from the SAP dataset.

WHY A DEDICATED READER:
- Every entity folder has multiple part-*.jsonl files
- Records may have nested dicts (e.g. creationTime) that need flattening
- We want one consistent place to handle encoding, empty lines, bad JSON
- All ingestion scripts import from here — no duplicated file-reading logic
"""

import json
import logging
from pathlib import Path
from typing import Generator

logger = logging.getLogger(__name__)

# ── Root path to the dataset ───────────────────────────────────────────────
# Resolves to: backend/data/raw/sap-order-to-cash-dataset/sap-o2c-data
DATA_ROOT = (
    Path(__file__).parent.parent.parent
    / "data"
    / "raw"
    / "sap-order-to-cash-dataset"
    / "sap-o2c-data"
)


def iter_records(entity_folder: str) -> Generator[dict, None, None]:
    """
    Yields one record at a time from all part-*.jsonl files
    in a given entity folder.

    WHY A GENERATOR:
    - For large folders (e.g. product_storage_locations has 16k records)
      loading everything into RAM at once is wasteful.
    - A generator yields one record, processes it, then moves on.
    - Ingestion scripts can use this in a for-loop without worrying
      about memory.

    Args:
        entity_folder: folder name under DATA_ROOT
                       e.g. "sales_order_headers"

    Yields:
        dict: one parsed JSON record
    """
    folder = DATA_ROOT / entity_folder
    if not folder.exists():
        logger.warning(f"Folder not found: {folder}")
        return

    part_files = sorted(folder.glob("part-*.jsonl"))
    if not part_files:
        logger.warning(f"No part-*.jsonl files in: {folder}")
        return

    for part_file in part_files:
        with open(part_file, "r", encoding="utf-8") as f:
            for line_number, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as e:
                    logger.warning(
                        f"Skipping bad JSON in {part_file.name} "
                        f"line {line_number}: {e}"
                    )
                    continue


def load_all(entity_folder: str) -> list[dict]:
    """
    Loads ALL records from an entity folder into a list.

    Use this only for small entities (< 1000 records).
    For large entities, use iter_records() directly.

    Args:
        entity_folder: folder name under DATA_ROOT

    Returns:
        list of all records
    """
    return list(iter_records(entity_folder))


def safe_str(value) -> str | None:
    """
    Converts any value to a clean string.
    Returns None for null, empty string, or the literal "null".

    WHY: Neo4j MERGE uses the ID field to find or create a node.
    If the ID is None, MERGE will fail or create a node with
    a null key — which breaks uniqueness constraints.
    Always sanitize IDs before sending to Neo4j.
    """
    if value is None:
        return None
    s = str(value).strip()
    if s == "" or s.lower() == "null":
        return None
    return s


def make_composite_id(*parts) -> str | None:
    """
    Creates a composite ID by joining parts with '_'.

    Used for entities that have no single primary key,
    e.g. SalesOrderItem: salesOrder="740506", salesOrderItem="10"
         → composite_id = "740506_10"

    Returns None if ANY part is None/empty (prevents bad IDs).
    """
    cleaned = [safe_str(p) for p in parts]
    if any(c is None for c in cleaned):
        return None
    return "_".join(cleaned)


def count_records(entity_folder: str) -> int:
    """Returns the total number of records across all part files."""
    return sum(1 for _ in iter_records(entity_folder))