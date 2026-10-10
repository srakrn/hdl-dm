#!/usr/bin/env python3
"""Export benchmark records for the static blind-review site, without API calls."""

import argparse
import csv
import hashlib
import json
from pathlib import Path
import secrets
import statistics

from benchmark import ROOT, read_json, write_json
from calculate_scores import calculate_scores

NICKNAMES = (
    "เมฆม้วน", "ดาวเด้ง", "น้องละมุน", "พุดดิ้งพอง", "ก้อนฟู", "จันทร์จิ๋ว",
    "กระต่ายง่วง", "แก้มกลม", "สายไหมยิ้ม", "บัวลอยบิน", "ปุยนุ่ม", "ลูกโป่งลอย",
    "มะลิซน", "หมีละเมอ", "แมวแต้ม", "ดาวหอม", "ฝันฟุ้ง", "ไข่มุกวิงค์",
    "ฟองสบู่", "น้องมุ้งมิ้ง", "กลีบแก้ว", "จุ๊บแจง", "กล่องดนตรี", "โมจิหลับ",
    "วาฬน้อย", "น้องพองพอง", "จิ้งจอกจิ๋ว", "พระอาทิตย์อุ่น", "แพนด้าปุย", "ยิ้มแฉ่ง",
)
PROFILES = {
    "thai_spicy": {"label": "เผ็ดได้", "icon": "🌶️", "description": "เปรี้ยว เค็ม กลมกล่อม เพิ่มความเผ็ดได้ตามใจ"},
    "thai_mild": {"label": "ไม่เผ็ด", "icon": "☁️", "description": "รสนุ่มนวล ไม่มีความเผ็ดหรือชาลิ้น"},
    "thai_no_vegetables": {"label": "ไม่ใส่ผัก", "icon": "🥣", "description": "ไม่มีผักชีและต้นหอม ยังใช้กระเทียม พริก เห็ด และซอสได้"},
}


def load_mapping(path, model_ids, public_dir=None):
    mapping = read_json(path) if path.exists() else {}
    # A fresh clone can recover stable aliases from the committed public files.
    if not mapping and public_dir and (public_dir / "recipes.json").exists() and (public_dir / "reveal.json").exists():
        prior, names = read_json(public_dir / "recipes.json"), read_json(public_dir / "reveal.json")
        if prior["dataset_id"] != names["dataset_id"]:
            raise ValueError("Public aliases and reveal file belong to different datasets")
        mapping = {names["models"][model["id"]]: {"id": model["id"], "nickname": model["nickname"]} for model in prior["models"]}
    unused = [name for name in NICKNAMES if name not in {v["nickname"] for v in mapping.values()}]
    secrets.SystemRandom().shuffle(unused)
    for model in model_ids:
        if model not in mapping:
            if not unused:
                raise ValueError("Add more nicknames before refreshing additional models")
            mapping[model] = {"id": secrets.token_hex(6), "nickname": unused.pop()}
    if len({v["id"] for v in mapping.values()}) != len(mapping) or len({v["nickname"] for v in mapping.values()}) != len(mapping):
        raise ValueError("Blind aliases must be unique")
    return mapping


def build_dataset(manifest, records, mapping, config):
    catalog = manifest["ingredient_catalog"]
    ingredients = [i["id"] for i in catalog]
    practical = manifest.get("method") == "practical"
    preparation = manifest.get("preparation") or {}
    public = {
        "schema_version": 2, "prompt_version": manifest.get("prompt_version"),
        "method": "practical" if practical else "noul", "preparation": preparation,
        "unit_ml": manifest["unit_ml"], "threshold": manifest["threshold"],
        "planned": manifest["requests_planned"], "completed": len(records),
        "successful": sum(r["status"] == "ok" for r in records),
        "profiles": [{"id": p["id"], **PROFILES[p["id"]], "excluded": p["excluded"]} for p in manifest["profiles"]],
        "ingredients": [{"id": i["id"], "label": i["thai_name"], "dispenser": preparation.get("dispensers", {}).get(i["id"], "ladle")} for i in catalog],
        "review": {"form_url": config.get("form_url"), "form_fields": config.get("form_fields", {})},
        "models": [],
    }
    reveal = {}
    for model_id in manifest["selected_models"]:
        alias = mapping[model_id]
        reveal[alias["id"]] = model_id
        model = {**alias, "recipes": []}
        for profile in manifest["profiles"]:
            successes = sorted((r for r in records if r["model"] == model_id and r["profile_id"] == profile["id"] and r["status"] == "ok"), key=lambda r: r["repeat"])
            if not successes:
                continue
            base = f"{alias['id']}-{profile['id']}"
            variants = [] if practical else [{
                "recipe_id": f"{base}-average", "id": "average", "label": f"เฉลี่ย {len(successes)} รอบ",
                "samples": len(successes),
                "units": {name: statistics.mean(r["volume_units"][name] for r in successes) for name in ingredients},
            }]
            for record in successes:
                variants.append({
                    "recipe_id": f"{base}-r{record['repeat']}", "id": f"r{record['repeat']}",
                    "label": f"รอบที่ {record['repeat']}", "samples": 1,
                    "units": {name: record["volume_units"][name] for name in ingredients},
                    **({"servings": record["servings"]} if practical else {}),
                })
            model["recipes"].append({"profile_id": profile["id"], "variants": variants})
        public["models"].append(model)
    public["models"].sort(key=lambda m: m["nickname"])
    # Scores are bound to recipe content, aliases, units, prompt and profile constraints.
    digest_input = {key: public[key] for key in ("prompt_version", "method", "preparation", "unit_ml", "threshold", "profiles", "ingredients", "models")}
    public["dataset_id"] = hashlib.sha256(json.dumps(digest_input, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:20]
    reveal = {"dataset_id": public["dataset_id"], "models": reveal}
    return public, reveal


def find_latest_run():
    candidates = []
    for path in (ROOT / "results").glob("*/manifest.json"):
        manifest = read_json(path)
        result_file = path.parent / "results.jsonl"
        if manifest.get("dry_run") or not result_file.exists():
            continue
        count = sum(bool(line.strip()) for line in result_file.read_text(encoding="utf-8").splitlines())
        if count == manifest["requests_planned"]:
            candidates.append(path.parent)
    if not candidates:
        raise ValueError("No completed benchmark found; use --run-dir for a partial run")
    return max(candidates, key=lambda p: p.name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--out", type=Path, default=ROOT / "web/data")
    parser.add_argument("--mapping", type=Path, default=ROOT / ".local/blind-map.json")
    parser.add_argument("--config", type=Path, default=ROOT / "config/review.json")
    parser.add_argument("--ratings", nargs="*", type=Path, default=[])
    args = parser.parse_args()
    try:
        run_dir = args.run_dir or find_latest_run()
        manifest = read_json(run_dir / "manifest.json")
        if manifest.get("dry_run"):
            raise ValueError("Cannot publish a dry run")
        records = [json.loads(line) for line in (run_dir / "results.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        config = read_json(args.config)
        mapping = load_mapping(args.mapping, manifest["selected_models"], args.out)
        public, reveal = build_dataset(manifest, records, mapping, config)
        scores = calculate_scores(public, args.ratings, config)
        args.mapping.parent.mkdir(parents=True, exist_ok=True)
        args.out.mkdir(parents=True, exist_ok=True)
        write_json(args.mapping, mapping)
        write_json(args.out / "recipes.json", public)
        write_json(args.out / "reveal.json", reveal)
        write_json(args.out / "scores.json", scores)
        with (args.out / "ratings-template.csv").open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f, lineterminator="\n")
            writer.writerow(["dataset_id", "recipe_id", "source", "judge_id", "overall", "food_pairing", "balance", "notes"])
            for model in public["models"]:
                for recipe in model["recipes"]:
                    for variant in recipe["variants"]:
                        writer.writerow([public["dataset_id"], variant["recipe_id"], "", "", "", "", "", ""])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    print(f"Refreshed {len(public['models'])} blind aliases from {run_dir}: {args.out}")


if __name__ == "__main__":
    main()
