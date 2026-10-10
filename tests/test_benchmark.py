import csv
from io import BytesIO
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import benchmark as b
from summarize import tasting_scores


def response(value=0.7):
    return {"model": "typesafe/jev-snapshot", "answers": {
        name: {"type": "noul", "noul": value} for name in b.INGREDIENTS
    }, "usage": {"cost": 0.01}}


class BenchmarkTests(unittest.TestCase):
    def test_env_file_key_and_shell_priority(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / ".env"
            with patch.dict(b.os.environ, {}, clear=True):
                self.assertEqual(b.get_api_key(path), "")
                for value in ("", "file-key", "'file-key' # comment", '"file-key"'):
                    path.write_text(f"# template\nOPENROUTER_API_KEY={value}\n", encoding="utf-8")
                    self.assertEqual(b.get_api_key(path), "file-key" if value else "")
                path.write_text("OPENROUTER_API_KEY='unterminated\n", encoding="utf-8")
                with self.assertRaises(ValueError):
                    b.get_api_key(path)
            with patch.dict(b.os.environ, {"OPENROUTER_API_KEY": "shell-key"}):
                self.assertEqual(b.get_api_key(path), "shell-key")

    def test_native_contract_and_exact_ingredients(self):
        profile = b.read_json(b.ROOT / "config/profiles.json")[0]
        payload = b.build_payload("typesafe/jev-1.13", profile, 5)
        self.assertEqual(len(payload["questions"]), 26)
        self.assertTrue(all(q["type"] == "noul" for q in payload["questions"].values()))
        self.assertEqual(set(payload["questions"]), set(b.INGREDIENTS))
        self.assertEqual(b.parse_answers(response())["lime_juice"], .7)

    def test_english_prompt_flavors_and_exclusions(self):
        self.assertEqual(len(set(b.INGREDIENTS)), 26)
        self.assertTrue({"chopped_scallions", "chopped_cilantro", "crushed_garlic"}.issubset(b.INGREDIENTS))
        profiles = b.read_json(b.ROOT / "config/profiles.json")
        for profile in profiles:
            payload = b.build_payload("test/model", profile, 5)
            self.assertTrue(json.dumps(payload, ensure_ascii=False).isascii())
            self.assertIn("plain, unseasoned water", payload["state"]["cooking_context"])
            descriptions = payload["state"]["ingredient_descriptions"]
            self.assertEqual(set(descriptions), set(b.INGREDIENTS))
            for ingredient, question in payload["questions"].items():
                self.assertTrue(question["criteria"]["true"].startswith("True when "))
                self.assertTrue(question["criteria"]["false"].startswith("False when "))
                self.assertIn(descriptions[ingredient]["flavor"], question["instructions"])
                self.assertTrue(descriptions[ingredient]["name"])
        no_cilantro = next(p for p in profiles if p["id"] == "thai_no_vegetables")
        self.assertEqual(set(no_cilantro["excluded"]), {"chopped_cilantro", "chopped_scallions"})

    def test_reject_malformed_nouls(self):
        for value in (True, "0.7", None, -0.01, 1.01, float("nan"), float("inf")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                b.parse_answers(response(value))
        for change in ("missing", "extra", "wrong_type"):
            data = response()
            if change == "missing":
                del data["answers"]["salt"]
            elif change == "extra":
                data["answers"]["unknown_ingredient"] = {"type": "noul", "noul": 1}
            else:
                data["answers"]["salt"]["type"] = "score"
            with self.assertRaises(ValueError):
                b.parse_answers(data)

    def test_confirmed_station_name_mapping(self):
        catalog = {item["id"]: item for item in b.INGREDIENT_CATALOG}
        self.assertEqual(catalog["chopped_cilantro"]["name"], "Parsley")
        self.assertEqual(catalog["chopped_cilantro"]["thai_name"], "ผักชีซอย")
        self.assertEqual(catalog["chopped_scallions"]["name"], "Minced shallots")
        self.assertEqual(catalog["chopped_scallions"]["thai_name"], "ต้นหอมซอย")
        self.assertEqual(catalog["dark_soy_sauce"]["name"], "Homemade soy sauce")
        self.assertEqual(catalog["lao_gan_ma"]["name"], "Flavoured bean sauce")
        self.assertEqual(catalog["lao_gan_ma"]["thai_name"], "เต้าซี่ปรุงรส")
        self.assertEqual(catalog["fermented_bean_curd"]["name"], "Fermented bean curd")
        self.assertNotIn("soft_tofu_sauce", catalog)
        self.assertEqual(len(set(b.THAI_NAMES.values())), len(b.INGREDIENTS))

    def test_post_contract_retry_and_auth(self):
        throttled = HTTPError(b.ENDPOINT, 429, "Too Many Requests", {"Retry-After": "0"}, None)
        data = BytesIO(json.dumps(response()).encode())
        with patch.object(b, "urlopen", side_effect=[throttled, data]) as call, patch.object(b.time, "sleep"):
            result, attempts = b.post_decisions({"model": "test"}, "secret-test", 10, 2)
        self.assertEqual(attempts, 2)
        self.assertEqual(result["model"], "typesafe/jev-snapshot")
        request = call.call_args.args[0]
        self.assertEqual(request.full_url, b.ENDPOINT)
        self.assertEqual(request.get_header("Authorization"), "Bearer secret-test")
        self.assertEqual(json.loads(request.data), {"model": "test"})

    def test_respan_text_state_preserves_complete_context(self):
        original = {"model": "respan/span-01", "state": {"evaluation_rubric": {"taste": .4}, "doses_already_chosen": {"lime_juice": .125}}}
        adapted = b.wire_payload(original)
        self.assertEqual(json.loads(adapted["state"]), original["state"])
        self.assertIsInstance(original["state"], dict)
        other = {**original, "model": "other/model"}
        self.assertIs(b.wire_payload(other), other)

    def test_no_retry_on_auth_or_ambiguous_transport(self):
        for error in (HTTPError(b.ENDPOINT, 401, "Unauthorized", {}, None), URLError("timeout")):
            with patch.object(b, "urlopen", side_effect=error) as call:
                with self.assertRaises(b.APIError):
                    b.post_decisions({}, "key", 10, 2)
                self.assertEqual(call.call_count, 1)

    def test_api_error_body_and_nonstandard_json_are_failures(self):
        for body in (b'{"error":{"code":400}}', b'{"answers":{"salt":{"noul":NaN}}}'):
            with patch.object(b, "urlopen", return_value=BytesIO(body)) as call:
                with self.assertRaises(b.APIError):
                    b.post_decisions({}, "key", 10, 2)
                self.assertEqual(call.call_count, 1)

    def test_cli_success_error_and_exports(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "run"
            argv = ["benchmark.py", "--method", "noul", "--models", "test/a", "test/b", "--profile", "thai_no_vegetables", "--repeats", "1", "--out", str(out)]
            with patch.object(sys, "argv", argv), patch.dict(b.os.environ, {"OPENROUTER_API_KEY": "secret-test"}), patch.object(b, "post_decisions", side_effect=[(response(), 1), b.APIError("HTTP 404", 1)]):
                self.assertEqual(b.main(), 1)
            records = [json.loads(line) for line in (out / "results.jsonl").read_text().splitlines()]
            self.assertEqual(records[0]["volume_ml"]["lime_juice"], 3.5)
            self.assertAlmostEqual(records[0]["excluded_volume_units"], 1.4)
            rows = b.read_json(out / "summary.json")
            self.assertEqual(sum(row["valid"] for row in rows), 1)
            self.assertIsNone(rows[1]["reported_cost_usd"])
            self.assertNotIn("secret-test", (out / "results.jsonl").read_text())
            with (out / "recipes.csv").open(encoding="utf-8-sig") as f:
                recipes = list(csv.DictReader(f))
                self.assertEqual(len(recipes), 26)
                self.assertEqual({r["ingredient"] for r in recipes}, set(b.THAI_NAMES.values()))
            recipe = b.read_json(out / "recipes.json")[0]
            self.assertEqual(recipe["volume_ml"]["น้ำมะนาว"], 3.5)
            self.assertEqual(set(recipe["noul"]), set(b.THAI_NAMES.values()))
            self.assertNotIn("น้ำมะนาว", records[0]["request"]["questions"])

    def test_binary_mapping_and_dry_run(self):
        with tempfile.TemporaryDirectory() as temp:
            base = ["benchmark.py", "--method", "noul", "--models", "test/a", "--profile", "thai_spicy", "--repeats", "1"]
            out = Path(temp) / "binary"
            with patch.object(sys, "argv", base + ["--threshold", ".7", "--out", str(out)]), patch.dict(b.os.environ, {"OPENROUTER_API_KEY": "test"}), patch.object(b, "post_decisions", return_value=(response(), 1)):
                self.assertEqual(b.main(), 0)
            record = json.loads((out / "results.jsonl").read_text())
            self.assertEqual(record["volume_units"]["salt"], 1)
            dry = Path(temp) / "dry"
            with patch.object(sys, "argv", base + ["--dry-run", "--out", str(dry)]), patch.object(b, "post_decisions") as call:
                self.assertEqual(b.main(), 0)
                call.assert_not_called()
            self.assertFalse((dry / "summary.json").exists())

    def test_stability_and_unknown_cost(self):
        records = [{"model": "test", "profile_id": "p", "status": "ok", "latency_seconds": i + 1,
                    "noul": b.parse_answers(response(value)), "excluded_volume_units": 0, "usage": {}}
                   for i, value in enumerate((0, 1))]
        row = b.summary(records)[0]
        self.assertEqual(row["mean_noul_stddev"], .5)
        self.assertEqual(row["latency_p95_seconds"], 2)
        self.assertIsNone(row["reported_cost_usd"])

    def test_old_run_ingredient_keys_remain_summarizable(self):
        records = [{"model": "old", "profile_id": "p", "status": "ok", "latency_seconds": 1,
                    "noul": {"เกลือ": value, "น้ำมะนาว": value}, "excluded_volume_units": 0, "usage": {}}
                   for value in (0, 1)]
        self.assertEqual(b.summary(records)[0]["mean_noul_stddev"], .5)

    def test_human_ratings_and_duplicates(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "ratings.csv"
            header = "sample_id,taster_id,overall_1_to_5,food_pairing_1_to_5,balance_1_to_5\n"
            path.write_text(header + "S1,P1,5,4,3\n", encoding="utf-8")
            records = [{"sample_id": "S1", "model": "test", "status": "ok"}]
            self.assertEqual(tasting_scores(path, records)["test"]["mean_overall_1_to_5"], 5)
            path.write_text(header + "S1,P1,5,4,3\nS1,P1,4,3,2\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                tasting_scores(path, records)
            path.write_text(header.replace("food_pairing", "broth_pairing") + "S1,P1,5,4,3\n", encoding="utf-8")
            self.assertEqual(tasting_scores(path, records)["test"]["mean_broth_pairing_1_to_5"], 4)


if __name__ == "__main__":
    unittest.main()
