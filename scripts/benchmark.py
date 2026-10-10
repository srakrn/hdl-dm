#!/usr/bin/env python3
"""Benchmark native OpenRouter decisions using only Python's stdlib."""

import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import random
import shlex
import statistics
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from practical import generate_recipe, selection_payload, validate_config

ROOT = Path(__file__).resolve().parents[1]
ENDPOINT = "https://openrouter.ai/api/alpha/decisions"
INGREDIENT_CATALOG = json.loads((ROOT / "config/ingredients.json").read_text(encoding="utf-8"))
INGREDIENTS = tuple(item["id"] for item in INGREDIENT_CATALOG)
THAI_NAMES = {item["id"]: item["thai_name"] for item in INGREDIENT_CATALOG}


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def get_api_key(env_file=ROOT / ".env"):
    if "OPENROUTER_API_KEY" in os.environ:
        return os.environ["OPENROUTER_API_KEY"].strip()
    if not env_file.exists():
        return ""
    for line in env_file.read_text(encoding="utf-8").splitlines():
        name, separator, value = line.strip().partition("=")
        if separator and name.strip() == "OPENROUTER_API_KEY":
            try:
                parts = shlex.split(value, comments=True)
            except ValueError:
                raise ValueError("Invalid quoting for OPENROUTER_API_KEY in .env") from None
            if len(parts) > 1:
                raise ValueError("OPENROUTER_API_KEY in .env must be a single value")
            return parts[0].strip() if parts else ""
    return ""


def build_payload(model, profile, unit_ml):
    return {
        "model": model,
        "state": {
            "task": "Design a Haidilao-style dipping sauce for food cooked in plain water, tailored to the Thai diner's preferences in this profile.",
            "cooking_context": "The food is cooked in plain, unseasoned water, with no soup base, salt, or stock. The dip supplies seasoning while preserving the food's own flavor.",
            "preferences": profile["preferences"],
            "excluded_ingredients": profile["excluded"],
            "available_ingredients": list(INGREDIENTS),
            "ingredient_descriptions": {
                item["id"]: {"name": item["name"], "flavor": item["flavor"]}
                for item in INGREDIENT_CATALOG
            },
            "flavor_assumptions": "These are draft sensory descriptions for this experiment. Where a station sauce is ambiguous, use the stated assumption rather than inventing a specific product recipe.",
            "preparation": "Minced pork is fully cooked. All condiments are ready to eat. Measure every ingredient by volume with the same measuring spoon.",
            "volume_mapping": f"The experiment maps each Noul directly to volume: 0 = omit, 1 = {unit_ml:g} mL (one unit), 0.5 = half a unit. Do not normalize the sum to one. Noul remains a probability of yes, not a native volume prediction.",
            "goal": "Evaluate each ingredient for one coherent dip. Balance acidity, saltiness, chili heat, sweetness, aroma, richness, and texture. Not every ingredient is needed. Respect excluded ingredients and avoid redundant additions, especially multiple forms of garlic or cilantro.",
        },
        "questions": {
            item["id"]: {
                "type": "noul",
                "instructions": f"Should {item['name']} be included in this dipping sauce for food cooked in plain water? Consider the diner's preferences, exclusions, and the full ingredient list. Flavor and texture: {item['flavor']}",
                "criteria": {
                    "true": f"True when {item['name']} contributes a desirable flavor or texture for this diner's profile, complements the unseasoned food, and is not excluded. Its contribution is useful without an unnecessary duplicate of another condiment.",
                    "false": f"False when {item['name']} is excluded, conflicts with the diner's preferences, adds unnecessary duplicate seasoning, or makes the dip too salty, sour, sweet, spicy, numbing, oily, or overpowering for the food.",
                },
            } for item in INGREDIENT_CATALOG
        },
    }


def parse_answers(response):
    if not isinstance(response, dict):
        raise ValueError("Response must be an object")
    answers = response.get("answers")
    if not isinstance(answers, dict) or set(answers) != set(INGREDIENTS):
        raise ValueError(f"Expected exactly the {len(INGREDIENTS)} ingredient answers")
    result = {}
    for name, answer in answers.items():
        if not isinstance(answer, dict) or answer.get("type") != "noul":
            raise ValueError(f"Invalid answer type: {name}")
        value = answer.get("noul")
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError(f"Noul must be a finite number in [0, 1]: {name}")
        result[name] = value
    return result


class APIError(Exception):
    def __init__(self, message, attempts):
        super().__init__(message)
        self.attempts = attempts


def reject_nonfinite_json(value):
    raise ValueError(f"Non-standard JSON numeric constant: {value}")


def post_decisions(payload, key, timeout, retries):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(ENDPOINT, data=body, headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json",
        "X-Title": "Haidilao Decisions Benchmark",
    }, method="POST")
    for attempt in range(retries + 1):
        try:
            with urlopen(request, timeout=timeout) as response:
                result = json.load(response, parse_constant=reject_nonfinite_json)
            if isinstance(result, dict) and "error" in result:
                raise APIError("OpenRouter returned an error in a successful HTTP response", attempt + 1)
            return result, attempt + 1
        except HTTPError as exc:
            # Do not log arbitrary server bodies which may contain echoed secrets.
            if exc.code not in (429, 500, 502, 503, 504, 524, 529) or attempt == retries:
                raise APIError(f"HTTP {exc.code}: {exc.reason}", attempt + 1) from exc
            retry_after = exc.headers.get("Retry-After", "")
            delay = min(60, float(retry_after)) if retry_after.isdigit() else min(60, 2 ** attempt)
            exc.close()
            time.sleep(delay)
        except (URLError, TimeoutError, OSError, ValueError) as exc:
            # An ambiguous timeout may already be billed. Never retry it automatically.
            raise APIError(f"Transport/JSON error ({type(exc).__name__})", attempt + 1) from exc


def summary(records):
    rows = []
    for model in dict.fromkeys(record["model"] for record in records):
        group = [r for r in records if r["model"] == model]
        valid = [r for r in group if r["status"] == "ok"]
        latencies = sorted(r["latency_seconds"] for r in group)
        costs = [r.get("usage", {}).get("cost") for r in group]
        known_costs = [c for c in costs if type(c) in (int, float) and math.isfinite(c)]
        deviations = []
        for profile_id in dict.fromkeys(r["profile_id"] for r in valid):
            repeated = [r for r in valid if r["profile_id"] == profile_id]
            if len(repeated) > 1:
                deviations.extend(statistics.pstdev(r["noul"][name] for r in repeated) for name in repeated[0]["noul"])
        rows.append({
            "model": model, "requests": len(group), "valid": len(valid),
            "valid_rate": len(valid) / len(group),
            "latency_median_seconds": statistics.median(latencies),
            "latency_p95_seconds": latencies[math.ceil(.95 * len(latencies)) - 1],
            "reported_cost_usd": sum(known_costs) if known_costs else None,
            "cost_known_requests": len(known_costs),
            "mean_noul_stddev": statistics.mean(deviations) if deviations else None,
            "excluded_volume_units": sum(r["excluded_volume_units"] for r in valid) if valid else None,
        })
    return rows


def export_reports(out, records):
    write_json(out / "summary.json", summary(records))
    # Keep raw API records in English; localize only the recipe presentation.
    recipes = []
    for record in records:
        if record["status"] == "ok":
            recipes.append({
                "sample_id": record["sample_id"], "model": record["model"],
                "profile_id": record["profile_id"], "repeat": record["repeat"],
                **{field: {THAI_NAMES[name]: record[field][name] for name in INGREDIENTS}
                   for field in ("noul", "volume_units", "volume_ml")},
                **({"servings": {THAI_NAMES[name]: dose for name, dose in record["servings"].items()}} if "servings" in record else {}),
            })
    write_json(out / "recipes.json", recipes)
    with (out / "recipes.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["sample_id", "model", "profile_id", "repeat", "ingredient", "noul", "volume_units", "volume_ml", "excluded", "dose_amount", "dose_unit"])
        for r in records:
            if r["status"] == "ok":
                for name in INGREDIENTS:
                    writer.writerow([r["sample_id"], r["model"], r["profile_id"], r["repeat"], THAI_NAMES[name], r["noul"][name], r["volume_units"][name], r["volume_ml"][name], name in r["excluded"], r.get("servings", {}).get(name, {}).get("amount", ""), r.get("servings", {}).get(name, {}).get("unit", "")])
    with (out / "tasting.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["sample_id", "taster_id", "overall_1_to_5", "food_pairing_1_to_5", "balance_1_to_5", "notes"])
        for r in records:
            if r["status"] == "ok":
                writer.writerow([r["sample_id"], "", "", "", "", ""])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models-file", type=Path, default=ROOT / "config/models.json")
    parser.add_argument("--models", nargs="+", help="Override config with exact OpenRouter model IDs")
    parser.add_argument("--jev-only", action="store_true")
    parser.add_argument("--profiles-file", type=Path, default=ROOT / "config/profiles.json")
    parser.add_argument("--profile", nargs="+", help="Select profile IDs")
    parser.add_argument("--workers", type=int, default=1, help="Concurrent recipe jobs; dose steps within each recipe stay sequential")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--method", choices=("practical", "noul"), default="practical", help="practical: Noul selection then discrete Choice doses; noul: original experiment")
    parser.add_argument("--preparation-file", type=Path, default=ROOT / "config/preparation.json")
    parser.add_argument("--unit-ml", type=float, default=5, help="Legacy noul unit size; practical mode uses preparation config ladle_ml")
    parser.add_argument("--threshold", type=float, help="Legacy noul mode only: optional binary volume mapping")
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--seed", type=int, default=42, help="Job order seed, not a model sampling seed")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--dry-run", action="store_true", help="Save payloads without network or API key")
    args = parser.parse_args()
    if args.workers < 1 or args.repeats < 1 or args.retries < 0 or not math.isfinite(args.unit_ml) or args.unit_ml <= 0 or not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("repeats, unit-ml and timeout must be positive; retries must be nonnegative")
    if args.threshold is not None and not 0 <= args.threshold <= 1:
        parser.error("threshold must be in [0, 1]")
    preparation = None
    if args.method == "practical":
        try:
            preparation = read_json(args.preparation_file)
            validate_config(preparation, INGREDIENTS)
        except (ValueError, KeyError, TypeError, OSError) as exc:
            parser.error(str(exc))
        if args.threshold is not None or args.unit_ml != 5:
            parser.error("For practical mode set selection_threshold/ladle_ml in preparation config, not legacy threshold/unit-ml")
        args.unit_ml = preparation["ladle_ml"]
    models_config = read_json(args.models_file) if not args.models else {"models": args.models, "source": "CLI"}
    models = list(dict.fromkeys(models_config["models"]))
    if not models or not all(isinstance(m, str) and m.strip() for m in models):
        parser.error("models must be a nonempty list of model IDs")
    if args.jev_only:
        models = [m for m in models if m.startswith("typesafe/jev") or m.startswith("~typesafe/jev")]
    profiles = read_json(args.profiles_file)
    ids = [p["id"] for p in profiles]
    if len(ids) != len(set(ids)):
        parser.error("profile IDs must be unique")
    if args.profile:
        if set(args.profile) - set(ids):
            parser.error("Unknown profile ID")
        profiles = [p for p in profiles if p["id"] in args.profile]
    for profile in profiles:
        if not isinstance(profile["preferences"], str) or not isinstance(profile["excluded"], list) or set(profile["excluded"]) - set(INGREDIENTS):
            parser.error("Invalid profile preferences or excluded ingredients")
    if not models or not profiles:
        parser.error("No models or profiles selected")
    try:
        key = "" if args.dry_run else get_api_key()
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    if not args.dry_run and not key:
        parser.error("Fill OPENROUTER_API_KEY in .env or export it before a live run")
    out = args.out or ROOT / "results" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    out.mkdir(parents=True, exist_ok=False)
    jobs = [(m, p, r) for m in models for p in profiles for r in range(1, args.repeats + 1)]
    random.Random(args.seed).shuffle(jobs)
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(), "endpoint": ENDPOINT,
        "models_config": models_config, "selected_models": models, "profiles": profiles,
        "ingredients": list(INGREDIENTS), "repeats": args.repeats, "unit_ml": args.unit_ml,
        "ingredient_catalog": INGREDIENT_CATALOG, "prompt_version": "7-practical-uncapped-ladle-equivalents" if preparation else "6-noul-with-sugar",
        "method": args.method, "preparation": preparation,
        "threshold": args.threshold, "seed": args.seed, "timeout": args.timeout,
        "workers": args.workers, "retries": args.retries, "dry_run": args.dry_run, "requests_planned": len(jobs),
    }
    write_json(out / "manifest.json", manifest)
    records = []
    stop_requested = threading.Event()
    def run_task(job):
        index, model, profile, repeat = job
        payload = build_payload(model, profile, args.unit_ml)
        if preparation:
            payload = selection_payload(payload, preparation)
        record = {
            "sample_id": f"S{index:04d}", "model": model, "profile_id": profile["id"],
            "repeat": repeat, "excluded": profile["excluded"], "request": payload,
            "request_sha256": hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
            "timestamp": datetime.now(timezone.utc).isoformat(), "attempts": 0,
        }
        started = time.perf_counter()
        if args.dry_run:
            record["status"] = "dry_run"
        else:
            try:
                if preparation:
                    record["stages"] = []
                    def ask(stage_payload):
                        if stop_requested.is_set():
                            raise InterruptedError("Run interrupted")
                        stage = {"request": stage_payload}
                        record["stages"].append(stage)
                        result, attempts = post_decisions(stage_payload, key, args.timeout, args.retries)
                        stage.update(response=result, attempts=attempts)
                        record["attempts"] += attempts
                        usage = result.get("usage", {}) if isinstance(result, dict) else {}
                        if not isinstance(usage, dict):
                            usage = {}
                        stage["usage"] = usage
                        costs = [r["usage"].get("cost") for r in record["stages"] if "usage" in r]
                        known = [c for c in costs if type(c) in (int, float) and math.isfinite(c)]
                        record["usage"] = {"cost": sum(known) if known else None, "cost_known_api_calls": len(known)}
                        return result
                    noul, selected, servings = generate_recipe(payload, profile, INGREDIENT_CATALOG, preparation, ask, parse_answers)
                    record.update(noul=noul, selected_ingredients=selected, servings=servings,
                                  removed_ingredients=[name for name in INGREDIENTS if noul[name] > 0 and servings[name]["amount"] == 0])
                    units = {name: dose["amount"] if dose["unit"] != "shake" else (0 if dose["amount"] == 0 else None) for name, dose in servings.items()}
                    volumes = {name: dose["volume_ml"] for name, dose in servings.items()}
                    response = record["stages"][0]["response"]
                    record["api_calls"] = len(record["stages"])
                else:
                    response, attempts = post_decisions(payload, key, args.timeout, args.retries)
                    record.update(response=response, attempts=attempts)
                    usage = response.get("usage", {}) if isinstance(response, dict) else {}
                    record["usage"] = usage if isinstance(usage, dict) else {}
                    noul = parse_answers(response)
                    units = {name: value if args.threshold is None else int(value >= args.threshold) for name, value in noul.items()}
                    volumes = {name: value * args.unit_ml for name, value in units.items()}
                record.update(
                    status="ok" if not preparation or any(d["amount"] > 0 for d in servings.values()) else "empty_recipe",
                    noul=noul, volume_units=units, volume_ml=volumes,
                    excluded_volume_units=sum(units[name] or 0 for name in profile["excluded"]),
                    resolved_model=response.get("model"), provider=response.get("provider"),
                )
            except APIError as exc:
                record.update(status="api_error", error=str(exc), attempts=record["attempts"] + exc.attempts)
            except InterruptedError as exc:
                record.update(status="interrupted", error=str(exc))
            except ValueError as exc:
                record.update(status="invalid_response", error=str(exc))
        if preparation:
            record["api_calls"] = len(record.get("stages", []))
        record["latency_seconds"] = time.perf_counter() - started
        return record
    pool = ThreadPoolExecutor(max_workers=args.workers)
    futures = [pool.submit(run_task, (index, model, profile, repeat)) for index, (model, profile, repeat) in enumerate(jobs, 1)]
    with (out / "results.jsonl").open("w", encoding="utf-8") as log:
        try:
            for future in (as_completed(futures) if args.workers > 1 else futures):
                record = future.result()
                records.append(record)
                log.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
                log.flush()
                print(f"[{len(records)}/{len(jobs)}] {record['model']} / {record['profile_id']} / {record['repeat']}: {record['status']}", flush=True)
        except KeyboardInterrupt:
            stop_requested.set()
            for future in futures:
                future.cancel()
            print("Interrupted; saved completed recipes. No new dose requests will start.", flush=True)
        finally:
            pool.shutdown(wait=True, cancel_futures=True)
            saved_ids = {r["sample_id"] for r in records}
            for future in futures:
                if future.cancelled() or not future.done() or future.exception() is not None:
                    continue
                record = future.result()
                if record["sample_id"] not in saved_ids:
                    records.append(record)
                    log.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
                    log.flush()
                    saved_ids.add(record["sample_id"])
    if not args.dry_run:
        export_reports(out, records)
    print(f"Saved: {out}")
    return int(stop_requested.is_set() or any(r["status"] in ("api_error", "invalid_response", "empty_recipe", "interrupted") for r in records))


if __name__ == "__main__":
    sys.exit(main())
