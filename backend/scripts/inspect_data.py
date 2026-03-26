"""
inspect_data.py

Inspects all SAP O2C JSONL datasets.
- Reads across all part-*.jsonl files per entity
- Shows field names, sample values, and potential FK columns
- Helps you design the graph schema before ingestion
"""

import json
import os
from pathlib import Path
from collections import defaultdict

# ── Path to your dataset root ──────────────────────────────────────────────
# Adjust this if your folder is placed differently
DATA_ROOT = Path(__file__).parent.parent / "data" / "raw" / "sap-order-to-cash-dataset" / "sap-o2c-data"


def read_jsonl_folder(folder: Path, max_records: int = 200) -> list[dict]:
    """
    Reads all part-*.jsonl files in a folder.
    Returns up to max_records combined records.
    """
    records = []
    part_files = sorted(folder.glob("part-*.jsonl"))
    
    if not part_files:
        return []
    
    for part_file in part_files:
        with open(part_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
                if len(records) >= max_records:
                    return records
    return records


def count_all_records(folder: Path) -> int:
    """Count total records across all part files."""
    total = 0
    for part_file in sorted(folder.glob("part-*.jsonl")):
        with open(part_file, "r", encoding="utf-8") as f:
            total += sum(1 for line in f if line.strip())
    return total


def inspect_entity(name: str, folder: Path) -> None:
    print(f"\n{'='*65}")
    print(f"  ENTITY : {name}")
    print(f"  FOLDER : {folder.name}")
    print(f"{'='*65}")

    if not folder.exists():
        print("  Folder not found — skipping")
        return

    part_files = sorted(folder.glob("part-*.jsonl"))
    print(f"  Part files : {len(part_files)}")

    total = count_all_records(folder)
    print(f"  Total records : {total:,}")

    records = read_jsonl_folder(folder, max_records=200)
    if not records:
        print("   No records found")
        return

    sample = records[0]
    fields = list(sample.keys())

    print(f"\n  Fields ({len(fields)}):")
    for field in fields:
        # Collect up to 3 non-null sample values
        sample_vals = []
        for r in records:
            v = r.get(field)
            if v is not None and v != "" and len(sample_vals) < 3:
                sample_vals.append(repr(v)[:40])
        print(f"    {field:<45} → {', '.join(sample_vals)}")

    # Detect likely ID / FK columns
    id_fields = [f for f in fields if any(
        kw in f.lower() for kw in ["id", "number", "key", "code", "no"]
    )]
    if id_fields:
        print(f"\n  Likely ID/FK fields:")
        for f in id_fields:
            unique_vals = list({str(r.get(f)) for r in records if r.get(f)})[:5]
            print(f"    {f:<45} → {unique_vals}")


def main():
    if not DATA_ROOT.exists():
        print(f"  DATA_ROOT not found: {DATA_ROOT}")
        print("   Update the DATA_ROOT path in this script.")
        return

    # All entity folders to inspect
    entities = sorted([
        d for d in DATA_ROOT.iterdir() if d.is_dir()
    ])

    print(f"\nFound {len(entities)} entity folders under:\n  {DATA_ROOT}\n")

    for folder in entities:
        inspect_entity(folder.name.replace("_", " ").title(), folder)

    print(f"\n\n{'='*65}")
    print("  Inspection complete.")
    print("  Next step: use the field names above to design your graph schema.")
    print(f"{'='*65}\n")


if __name__ == "__main__":
    main()