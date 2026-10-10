import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from benchmark import ROOT, read_json, write_json
from refresh_site import build_dataset, load_mapping
from calculate_scores import calculate_scores


class ReviewSiteTests(unittest.TestCase):
    def setUp(self):
        self.config = read_json(ROOT / "config/review.json")
        self.manifest = {
            "ingredient_catalog": [{"id": "lime", "name": "Lime juice", "thai_name": "น้ำมะนาว", "flavor": "sour"}],
            "unit_ml": 5, "threshold": None, "prompt_version": "test-v1", "requests_planned": 3,
            "profiles": [{"id": "thai_spicy", "excluded": []}], "selected_models": ["vendor/a", "vendor/b"],
        }
        self.records = [{"model": "vendor/a", "profile_id": "thai_spicy", "status": "ok", "repeat": i,
                         "volume_units": {"lime": value}} for i, value in ((1, .2), (2, .8))]
        self.records.append({"model": "vendor/b", "profile_id": "thai_spicy", "status": "api_error"})
        self.mapping = {"vendor/a": {"id": "random-a", "nickname": "ดาวเด้ง"}, "vendor/b": {"id": "random-b", "nickname": "เมฆม้วน"}}
        self.data, self.reveal = build_dataset(self.manifest, self.records, self.mapping, self.config)

    def test_blind_export_and_averaging(self):
        serialized = json.dumps(self.data)
        self.assertNotIn("vendor/a", serialized)
        self.assertNotIn("vendor/b", serialized)
        available = next(m for m in self.data["models"] if m["recipes"])
        self.assertEqual(available["recipes"][0]["variants"][0]["units"]["lime"], .5)
        self.assertEqual(self.reveal["models"]["random-a"], "vendor/a")
        self.assertEqual(sum(len(m["recipes"]) for m in self.data["models"]), 1)
        self.assertEqual(self.data["successful"], 2)

    def test_dataset_changes_when_recipe_or_constraints_change(self):
        self.records[0]["volume_units"]["lime"] = .3
        changed, _ = build_dataset(self.manifest, self.records, self.mapping, self.config)
        self.assertNotEqual(changed["dataset_id"], self.data["dataset_id"])

    def test_alias_persistence_and_recovery_from_public_files(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "map.json"
            mapping = load_mapping(path, ["vendor/a", "vendor/b"])
            write_json(path, mapping)
            self.assertEqual(load_mapping(path, ["vendor/b", "vendor/a"]), mapping)
            public = Path(temp) / "public"
            public.mkdir()
            write_json(public / "recipes.json", self.data)
            write_json(public / "reveal.json", self.reveal)
            self.assertEqual(load_mapping(Path(temp) / "missing.json", ["vendor/a", "vendor/b"], public), self.mapping)

    def write_ratings(self, path, entries):
        recipe = next(m for m in self.data["models"] if m["recipes"])["recipes"][0]["variants"][0]["recipe_id"]
        with path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["dataset_id", "recipe_id", "source", "judge_id", "overall", "food_pairing", "balance"])
            for source, judge, overall, pairing, balance in entries:
                writer.writerow([self.data["dataset_id"], recipe, source, judge, overall, pairing, balance])
        return recipe

    def test_score_weights_sources_and_three_judges(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "ratings.csv"
            recipe = self.write_ratings(path, [("llm", f"judge{i}", 5, 4, 3) for i in range(3)] + [("human", "person1", 1, 1, 1)])
            scores = calculate_scores(self.data, [path], self.config)["recipes"][recipe]
            self.assertAlmostEqual(scores["llm"]["stars"], 4.3)
            self.assertTrue(scores["llm"]["complete"])
            self.assertEqual(scores["human"]["stars"], 1)

    def test_reject_stale_duplicate_and_invalid_scores(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "ratings.csv"
            for entries in (
                [("human", "person", 5, 5, 5), ("human", "person", 4, 4, 4)],
                [("llm", "judge", 6, 5, 5)],
                [("llm", "judge", float("nan"), 5, 5)],
                [("llm", f"j{i}", 4, 4, 4) for i in range(4)],
            ):
                self.write_ratings(path, entries)
                with self.assertRaises(ValueError):
                    calculate_scores(self.data, [path], self.config)
            self.write_ratings(path, [("human", "p", 4, 4, 4)])
            stale = {**self.data, "dataset_id": "old"}
            with self.assertRaises(ValueError):
                calculate_scores(stale, [path], self.config)

    def test_no_ratings_never_invents_stars(self):
        self.assertEqual(calculate_scores(self.data, [], self.config)["recipes"], {})


if __name__ == "__main__":
    unittest.main()
