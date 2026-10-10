import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from benchmark import ROOT, read_json, write_json
import judge_recipes
from judge_recipes import AXES, aggregate_judgments, build_payload, parse_review, recipe_inputs, resolve_judges


def review(metrics=None):
    return {'metrics': metrics or {'taste': 4, 'balance': 3, 'complexity': 2, 'novelty': 1},
            'critique': 'มะนาวมาเป็นกรรมการห้ามทัพน้ำปลา คาดว่าพอเข้ากันได้',
            'strength': 'มะนาวช่วยตัดความมัน', 'concern': 'ซอสเค็มหลายตัวอาจกลบรสอาหาร',
            'suggestion': 'ลดน้ำมันงาลงเป็นหนึ่งในแปดช้อนใหญ่'}


def response(value=None, model='test/model'):
    return {'model': model, 'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(value or review())}}],
            'usage': {'cost': 0.001}}


class JudgeTests(unittest.TestCase):
    def setUp(self):
        self.data = read_json(ROOT / 'web/data/recipes.json')
        self.catalog = read_json(ROOT / 'config/ingredients.json')
        self.config = read_json(ROOT / 'config/judges.json')

    def test_inputs_are_blind_thai_bilingual_and_preserve_station_doses(self):
        recipe_id, recipe = next(recipe_inputs(self.data, self.catalog))
        raw = json.dumps(recipe, ensure_ascii=False)
        self.assertNotIn(recipe_id, raw)
        self.assertNotIn('nickname', raw)
        for true_model in read_json(ROOT / 'web/data/reveal.json')['models'].values():
            self.assertNotIn(true_model, raw)
        self.assertEqual(recipe['ladle_ml'], 25)
        self.assertTrue(all(i['name'] and i['flavor'] for i in recipe['ingredients']))
        for ingredient in recipe['ingredients']:
            if ingredient['unit'] == 'shake':
                self.assertIsNone(ingredient['approximate_volume_ml'])
            else:
                self.assertEqual(ingredient['approximate_volume_ml'], ingredient['amount'] * 25)
        by_id = {i['id']: i for i in self.catalog}
        for ingredient in recipe['allowed_ingredients']:
            item = by_id[ingredient['id']]
            self.assertEqual(ingredient['name'], f"{item['thai_name']} ({item['name']})")
            self.assertRegex(ingredient['flavor'], r'[ก-๙]')
        self.assertRegex(recipe['cooking_context'], r'[ก-๙]')
        self.assertTrue(all('ช้อนใหญ่' in i['measurement_explanation'] or 'เขย่า' in i['measurement_explanation'] for i in recipe['ingredients']))
        payload = build_payload(self.config['judges'][0], recipe)
        self.assertEqual(payload['response_format']['type'], 'json_schema')
        self.assertIn('ภาษาไทย', payload['messages'][0]['content'])
        self.assertNotIn('Authorization', str(payload))

    def test_strict_validation_language_ranges_and_truncation(self):
        self.assertEqual(parse_review(response()), review())
        for invalid in (review({**review()['metrics'], 'taste': True}),
                        review({**review()['metrics'], 'taste': float('nan')}),
                        review({**review()['metrics'], 'taste': 6}),
                        {**review(), 'critique': 'English-only commentary'},
                        {**review(), 'extra': 'unexpected'}):
            with self.assertRaises(ValueError):
                parse_review(response(invalid))
        truncated = response()
        truncated['choices'][0]['finish_reason'] = 'length'
        with self.assertRaises(ValueError):
            parse_review(truncated)

    def test_latest_families_exclude_batch_lite_and_preview(self):
        catalog = [
            {'id': 'openai/gpt-6-sol', 'name': 'Sol 6', 'created': 1},
            {'id': 'openai/gpt-6.1-sol', 'name': 'Sol 6.1', 'created': 2},
            {'id': 'openai/gpt-6.1-sol-pro', 'name': 'Pro', 'created': 3},
            {'id': 'openai/gpt-6.1-sol:batch', 'name': 'Batch', 'created': 4},
            {'id': 'openai/gpt-6.1-sol-decisions', 'name': 'Decisions', 'created': 4},
            {'id': 'google/gemini-3.8-flash', 'name': 'Flash', 'created': 2},
            {'id': 'google/gemini-4-flash-lite', 'name': 'Lite', 'created': 4},
            {'id': 'google/gemini-4-flash-preview', 'name': 'Preview', 'created': 4},
            {'id': self.config['judges'][0]['model'], 'name': 'DeepSeek', 'created': 2},
        ]
        resolved = resolve_judges(self.config, catalog)
        self.assertEqual(resolved[0]['model'], 'deepseek/deepseek-v4.1-flash')
        self.assertEqual(resolved[1]['model'], 'openai/gpt-6.1-sol')
        self.assertEqual(resolved[2]['model'], 'google/gemini-3.8-flash')

    def public(self, count=3):
        recipe_id = next(recipe_inputs(self.data, self.catalog))[0]
        return {'dataset_id': self.data['dataset_id'], 'prompt_version': self.config['prompt_version'],
                'weights': self.config['weights'], 'judges': self.config['judges'],
                'recipes': {recipe_id: [{'judge_id': j['id'], 'requested_model': j['model'], **review()} for j in self.config['judges'][:count]]}}

    def test_four_axis_average_and_partial_coverage(self):
        public = self.public()
        scores = next(iter(aggregate_judgments(self.data, public, self.config).values()))
        self.assertAlmostEqual(scores['stars'], 3.3)
        self.assertEqual(scores['count'], 3)
        self.assertTrue(scores['complete'])
        self.assertEqual(set(scores['metrics']), set(AXES))
        partial = next(iter(aggregate_judgments(self.data, self.public(2), self.config).values()))
        self.assertFalse(partial['complete'])
        self.assertEqual(partial['count'], 2)
        stale = {**public, 'dataset_id': 'old'}
        self.assertEqual(aggregate_judgments(self.data, stale, self.config), {})

    def test_zero_scores_survive_validation_and_aggregation(self):
        zero = review({axis: 0 for axis in AXES})
        self.assertEqual(parse_review(response(zero)), zero)
        public = self.public()
        for rows in public['recipes'].values():
            for row in rows:
                row.update(zero)
        score = next(iter(aggregate_judgments(self.data, public, self.config).values()))
        self.assertEqual(score['stars'], 0)
        self.assertTrue(score['complete'])

    def test_duplicate_judge_wrong_model_or_changed_rubric_rejected(self):
        for kind in ('duplicate', 'model', 'rubric'):
            public = self.public()
            rows = next(iter(public['recipes'].values()))
            if kind == 'duplicate':
                rows.append(rows[0])
            elif kind == 'model':
                rows[0]['requested_model'] = 'other/model'
            else:
                public['weights'] = {a: 1 for a in AXES}
            with self.assertRaises(ValueError):
                aggregate_judgments(self.data, public, self.config)

    def test_resuming_skips_completed_api_calls_and_keeps_raw_usage(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            config = copy.deepcopy(self.config)
            for index, judge in enumerate(config['judges']):
                judge.pop('latest_family', None)
                judge['model'] = f'test/model{index}'
            write_json(path / 'config.json', config)
            catalog = [{'id': j['model'], 'name': j['model'], 'created': 1} for j in config['judges']]
            arguments = ['judge_recipes.py', '--config', str(path / 'config.json'), '--limit', '1',
                         '--out', str(path / 'run'), '--public', str(path / 'public.json')]
            def model_catalog(*args, **kwargs):
                return io.BytesIO(json.dumps({'data': catalog}).encode())
            with patch.object(sys, 'argv', arguments), patch('judge_recipes.get_api_key', return_value='fake-secret-key'), \
                    patch('judge_recipes.urlopen', side_effect=model_catalog), \
                    patch('judge_recipes.post', side_effect=lambda payload, key, timeout: response(model=payload['model'])) as api:
                self.assertEqual(judge_recipes.main(), 0)
                self.assertEqual(judge_recipes.main(), 0)
                self.assertEqual(api.call_count, 3)
            public = read_json(path / 'public.json')
            self.assertEqual(sum(len(r) for r in public['recipes'].values()), 3)
            raw = (path / 'run/results.jsonl').read_text()
            self.assertNotIn('fake-secret-key', raw)
            self.assertNotIn('fake-secret-key', json.dumps(public))
            self.assertEqual(read_json(path / 'run/summary.json')['reported_cost_usd'], .003)
            self.assertIn('started', raw)
            self.assertIn('usage', raw)


if __name__ == '__main__':
    unittest.main()
