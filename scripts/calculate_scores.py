#!/usr/bin/env python3
"""Aggregate offline ratings. Does not call LLMs or submit forms."""

import argparse
import csv
import math
from pathlib import Path
import statistics

from benchmark import ROOT, read_json, write_json

METRICS = ("overall", "food_pairing", "balance")


def calculate_scores(dataset, rating_paths, config):
    weights = config["score_weights"]
    if set(weights) != set(METRICS) or any(type(w) not in (int, float) or not math.isfinite(w) or w < 0 for w in weights.values()) or sum(weights.values()) <= 0:
        raise ValueError("score_weights must contain three finite nonnegative weights with a positive sum")
    expected = config["expected_llm_judges"]
    if type(expected) is not int or expected < 1:
        raise ValueError("expected_llm_judges must be a positive integer")
    recipes = {variant["recipe_id"] for model in dataset["models"] for recipe in model["recipes"] for variant in recipe["variants"]}
    seen, grouped = set(), {}
    for path in rating_paths:
        with Path(path).open(encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            required = {"dataset_id", "recipe_id", "source", "judge_id", *METRICS}
            if not required.issubset(reader.fieldnames or []):
                raise ValueError(f"Missing rating columns in {path}")
            for row in reader:
                if not any((row[m] or "").strip() for m in METRICS):
                    continue
                if row["dataset_id"] != dataset["dataset_id"]:
                    raise ValueError("Ratings belong to a different dataset; refresh the rating template")
                recipe_id, source, judge = row["recipe_id"], row["source"], row["judge_id"].strip()
                if recipe_id not in recipes or source not in ("llm", "human") or not judge:
                    raise ValueError("Unknown recipe_id, source, or empty judge_id")
                key = (recipe_id, source, judge)
                if key in seen:
                    raise ValueError("Duplicate recipe/source/judge rating")
                seen.add(key)
                values = {metric: float(row[metric]) for metric in METRICS}
                if any(not math.isfinite(v) or not 1 <= v <= 5 for v in values.values()):
                    raise ValueError("All rating values must be finite numbers in [1, 5]")
                weighted = sum(values[m] * weights[m] for m in METRICS) / sum(weights.values())
                grouped.setdefault(recipe_id, {}).setdefault(source, []).append((judge, values, weighted))
                if source == "llm" and len(grouped[recipe_id][source]) > expected:
                    raise ValueError("More LLM judges than expected; update expected_llm_judges in config")
    output = {}
    for recipe_id, sources in grouped.items():
        output[recipe_id] = {}
        for source, entries in sources.items():
            output[recipe_id][source] = {
                "stars": statistics.mean(entry[2] for entry in entries),
                "count": len(entries),
                "metrics": {metric: statistics.mean(e[1][metric] for e in entries) for metric in METRICS},
                "expected_judges": expected if source == "llm" else None,
                "complete": len(entries) == expected if source == "llm" else True,
            }
    return {"dataset_id": dataset["dataset_id"], "weights": weights, "recipes": output}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=ROOT / "web/data/recipes.json")
    parser.add_argument("--ratings", nargs="*", type=Path, default=[])
    parser.add_argument("--config", type=Path, default=ROOT / "config/review.json")
    parser.add_argument("--out", type=Path, default=ROOT / "web/data/scores.json")
    args = parser.parse_args()
    try:
        scores = calculate_scores(read_json(args.data), args.ratings, read_json(args.config))
        write_json(args.out, scores)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        parser.error(str(exc))
    print(f"Saved scores for {len(scores['recipes'])} recipes: {args.out}")


if __name__ == "__main__":
    main()
