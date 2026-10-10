#!/usr/bin/env python3
"""Rebuild metrics from JSONL and optionally join blind human tasting scores."""

import argparse
import csv
import json
import math
from pathlib import Path
import statistics

from benchmark import read_json, summary, write_json


def tasting_scores(path, records):
    samples = {r["sample_id"]: r for r in records if r["status"] == "ok"}
    ratings, seen = {}, set()
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        pairing_field = "food_pairing_1_to_5" if "food_pairing_1_to_5" in (reader.fieldnames or []) else "broth_pairing_1_to_5"
        fields = ("overall_1_to_5", pairing_field, "balance_1_to_5")
        required = {"sample_id", "taster_id", *fields}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("Ratings CSV is missing required columns")
        for row in reader:
            if not any(row[field].strip() for field in fields):
                continue
            sample, taster = row["sample_id"], row["taster_id"].strip()
            if sample not in samples or not taster:
                raise ValueError("Unknown sample_id or missing taster_id")
            pair = (sample, taster)
            if pair in seen:
                raise ValueError(f"Duplicate tasting: {sample} / {taster}")
            seen.add(pair)
            values = {field: float(row[field]) for field in fields}
            if any(not math.isfinite(v) or not 1 <= v <= 5 for v in values.values()):
                raise ValueError("All three tasting scores must be between 1 and 5")
            ratings.setdefault(samples[sample]["model"], []).append((sample, values))
    return {
        model: {
            "ratings": len(rows), "samples_tasted": len({sample for sample, _ in rows}),
            **{f"mean_{field}": statistics.mean(values[field] for _, values in rows) for field in fields},
        } for model, rows in ratings.items()
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--ratings", type=Path)
    args = parser.parse_args()
    try:
        records = [json.loads(line) for line in (args.run_dir / "results.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        if read_json(args.run_dir / "manifest.json")["dry_run"]:
            parser.error("Dry runs contain no measurements to summarize")
        rows = summary(records)
        if args.ratings:
            ratings = tasting_scores(args.ratings, records)
            for row in rows:
                row["human_tasting"] = ratings.get(row["model"])
        write_json(args.run_dir / "summary.json", rows)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    print(f"Saved: {args.run_dir / 'summary.json'}")


if __name__ == "__main__":
    main()
