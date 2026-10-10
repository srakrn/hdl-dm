import copy
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import benchmark as b
from practical import amount_payload, dose_options, generate_recipe, parse_choice, selection_payload, shortlist, validate_config
from refresh_site import build_dataset


class PracticalTests(unittest.TestCase):
    def setUp(self):
        self.config = b.read_json(b.ROOT / "config/preparation.json")
        self.profile = b.read_json(b.ROOT / "config/profiles.json")[1]
        self.base = selection_payload(b.build_payload("test/model", self.profile, 25), self.config)

    def test_station_and_selection_never_treat_probability_as_amount(self):
        validate_config(self.config, b.INGREDIENTS)
        self.assertNotIn("volume_mapping", self.base["state"])
        self.assertTrue(json.dumps(self.base, ensure_ascii=False).isascii())
        self.assertIn("Sugar", self.base["questions"]["sugar"]["instructions"])
        noul = {name: .99 for name in b.INGREDIENTS}
        noul["lime_juice"] = .49
        selected = shortlist(noul, self.profile, self.config)
        self.assertEqual(len(selected), len(b.INGREDIENTS) - len(self.profile["excluded"]) - 1)
        self.assertFalse(set(selected) & set(self.profile["excluded"]))
        self.assertNotIn("lime_juice", selected)

    def test_v2_rubric_reaches_both_stages_and_catalog_matches_station(self):
        rubric = self.base['state']['evaluation_rubric']
        self.assertEqual(rubric['weights'], b.read_json(b.ROOT / 'config/judges.json')['weights'])
        payload, _ = amount_payload(self.base, 'lime_juice', ['lime_juice'], {}, b.INGREDIENT_CATALOG, self.config)
        self.assertEqual(payload['state']['evaluation_rubric'], rubric)
        self.assertEqual(len(b.INGREDIENTS), 26)
        for removed in ('garlic', 'cilantro'):
            self.assertNotIn(removed, self.base['questions'])
            self.assertNotIn(removed, self.config['dispensers'])
        for profile in b.read_json(b.ROOT / 'config/profiles.json'):
            self.assertFalse(set(profile['excluded']) - set(b.INGREDIENTS))

    def test_selection_threshold_includes_boundary_and_rejects_lower(self):
        config = {**self.config, "selection_threshold": .7}
        noul = {name: 0 for name in b.INGREDIENTS}
        noul.update(lime_juice=.7, fish_sauce=.699999, sugar=.71)
        selected = shortlist(noul, self.profile, config)
        self.assertIn("lime_juice", selected)
        self.assertIn("sugar", selected)
        self.assertNotIn("fish_sauce", selected)

    def test_ladle_tongs_squeeze_and_uncalibrated_shaker(self):
        choices = dose_options("lime_juice", self.config)
        self.assertIn("ladle_eighths_1", choices)
        self.assertEqual(choices["ladle_eighths_1"]["volume_ml"], 3.125)
        self.assertEqual(dose_options("chopped_cilantro", self.config)["ladle_eighths_1"]["unit"], "tongs")
        self.assertEqual(dose_options("fish_sauce", self.config)["ladle_eighths_1"]["volume_ml"], 3.125)
        self.assertIsNone(dose_options("sugar", self.config)["shake_1"]["volume_ml"])
        changed = copy.deepcopy(self.config)
        changed["ladle_amounts"] = [0, .01]
        with self.assertRaises(ValueError):
            validate_config(changed, b.INGREDIENTS)

    def test_conditional_doses_without_caps_and_with_exclusions(self):
        seen = []
        def ask(payload):
            seen.append(payload)
            if payload["questions"].get("salt", {}).get("type") == "noul":
                values = {name: (.9 if name in ("lime_juice", "sesame_sauce", "crushed_garlic", "fish_sauce", "sugar", "crushed_chili") else .01) for name in b.INGREDIENTS}
                return {"answers": {name: {"type": "noul", "noul": value} for name, value in values.items()}}
            name = next(iter(payload["questions"]))
            keys = list(payload["questions"][name]["criteria"])
            selected = keys[-1]
            return {"answers": {name: {"type": "choice", "choice": selected, "probabilities": {key: int(key == selected) for key in keys}}}}
        noul, selected, servings = generate_recipe(self.base, self.profile, b.INGREDIENT_CATALOG, self.config, ask, b.parse_answers)
        self.assertEqual(servings["crushed_chili"]["amount"], 0)
        self.assertEqual(servings["fish_sauce"]["amount"], 2)
        self.assertEqual(servings["sugar"]["amount"], 2)
        self.assertGreater(sum(d["amount"] for d in servings.values() if d["unit"] != "shake"), 3)
        self.assertTrue(any(p["state"].get("doses_already_chosen") for p in seen[2:]))
        self.assertEqual(len(noul), len(b.INGREDIENTS))

    def test_choice_rejects_fabricated_or_nonfinite_quantities(self):
        options = dose_options("lime_juice", self.config)
        for value in ({"type": "choice", "choice": "ladle_eighths_999", "probabilities": {}}, {"type": "noul", "noul": .1}, {"type": "choice", "choice": "omit", "probabilities": {key: float("nan") for key in options}}):
            with self.assertRaises(ValueError):
                parse_choice({"answers": {"lime_juice": value}}, "lime_juice", options)

    def test_live_pipeline_retains_stages_and_exports_uncalibrated_dose(self):
        def post(payload, *args):
            if payload["questions"].get("salt", {}).get("type") == "noul":
                response = {"answers": {name: {"type": "noul", "noul": .9 if name in ("lime_juice", "fish_sauce") else .01} for name in b.INGREDIENTS}}
            else:
                name = next(iter(payload["questions"]))
                keys = list(payload["questions"][name]["criteria"])
                chosen = keys[1]
                response = {"answers": {name: {"type": "choice", "choice": chosen, "probabilities": {key: int(key == chosen) for key in keys}}}}
            response["usage"] = {"cost": .01}
            return response, 1
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "run"
            argv = ["benchmark.py", "--method", "practical", "--models", "test/model", "--profile", "thai_mild", "--repeats", "1", "--out", str(out)]
            with patch.object(sys, "argv", argv), patch.object(b, "get_api_key", return_value="test-key"), patch.object(b, "post_decisions", side_effect=post):
                self.assertEqual(b.main(), 0)
            record = json.loads((out / "results.jsonl").read_text())
            self.assertEqual(record["api_calls"], 3)
            self.assertEqual(record["attempts"], 3)
            self.assertAlmostEqual(record["usage"]["cost"], .03)
            self.assertEqual(record["volume_ml"]["fish_sauce"], 3.125)
            self.assertEqual(record["volume_ml"]["lime_juice"], 3.125)
            self.assertEqual(len(record["stages"]), 3)
            recipe = b.read_json(out / "recipes.json")[0]
            self.assertEqual(recipe["servings"]["น้ำปลา"]["unit"], "squeeze")
            self.assertNotIn("test-key", (out / "results.jsonl").read_text())

    def test_parallel_recipes_keep_selection_and_stages_isolated(self):
        barrier = threading.Barrier(2)
        def post(payload, *args):
            ingredient = "lime_juice" if payload["model"] == "test/a" else "fish_sauce"
            if payload["questions"].get("salt", {}).get("type") == "noul":
                barrier.wait(timeout=2)
                response = {"answers": {name: {"type": "noul", "noul": .9 if name == ingredient else .01} for name in b.INGREDIENTS}}
            else:
                self.assertEqual(set(payload["questions"]), {ingredient})
                keys = list(payload["questions"][ingredient]["criteria"])
                selected = keys[1]
                response = {"answers": {ingredient: {"type": "choice", "choice": selected, "probabilities": {key: int(key == selected) for key in keys}}}}
            response["usage"] = {"cost": .01}
            return response, 1
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "parallel"
            argv = ["benchmark.py", "--method", "practical", "--models", "test/a", "test/b", "--profile", "thai_mild", "--repeats", "1", "--workers", "2", "--out", str(out)]
            with patch.object(sys, "argv", argv), patch.object(b, "get_api_key", return_value="test-key"), patch.object(b, "post_decisions", side_effect=post):
                self.assertEqual(b.main(), 0)
            records = [json.loads(line) for line in (out / "results.jsonl").read_text().splitlines()]
            self.assertEqual(len(records), 2)
            for record in records:
                self.assertTrue(all(stage["request"]["model"] == record["model"] for stage in record["stages"]))
                used = {name for name, dose in record["servings"].items() if dose["amount"]}
                self.assertEqual(used, {"lime_juice"} if record["model"] == "test/a" else {"fish_sauce"})

    def test_public_recipe_has_real_rounds_and_shaker_has_no_fake_volume(self):
        catalog = [{"id": "sugar", "thai_name": "น้ำตาล"}]
        manifest = {"ingredient_catalog": catalog, "unit_ml": 25, "threshold": None, "requests_planned": 1,
                    "profiles": [{"id": "thai_spicy", "excluded": []}], "selected_models": ["test/model"],
                    "method": "practical", "preparation": self.config}
        record = {"model": "test/model", "status": "ok", "profile_id": "thai_spicy", "repeat": 1,
                  "volume_units": {"sugar": None}, "servings": {"sugar": {"amount": 1, "unit": "shake", "volume_ml": None}}}
        data, _ = build_dataset(manifest, [record], {"test/model": {"id": "blind", "nickname": "ดาวเด้ง"}}, {})
        variants = data["models"][0]["recipes"][0]["variants"]
        self.assertEqual([v["id"] for v in variants], ["r1"])
        self.assertIsNone(variants[0]["servings"]["sugar"]["volume_ml"])
        record["servings"]["sugar"]["amount"] = 2
        changed, _ = build_dataset(manifest, [record], {"test/model": {"id": "blind", "nickname": "ดาวเด้ง"}}, {})
        self.assertNotEqual(data["dataset_id"], changed["dataset_id"])


if __name__ == "__main__":
    unittest.main()
