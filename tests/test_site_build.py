import csv
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from benchmark import ROOT, read_json, write_json
from build_site import download_reviews, normalize_reviews, refresh_scores
from regenerate_recipes import validate_run


class SiteBuildTests(unittest.TestCase):
    def setUp(self):
        self.config = read_json(ROOT / 'config/review.json')
        self.data = {'dataset_id': 'current', 'models': [{'recipes': [{'variants': [{'recipe_id': 'recipe'}]}]}]}
        self.settings = self.config['review_import']

    def reviews(self, entries):
        stream = io.StringIO()
        writer = csv.writer(stream)
        writer.writerow([self.settings['response_id_column'], self.settings['columns']['overall'],
                         self.settings['columns']['notes'], self.settings['review_id_column']])
        writer.writerows(entries)
        return stream.getvalue()

    def test_actual_form_single_score_zero_to_ten(self):
        text = self.reviews([['time1', 0, 'private note', '{"dataset_id":"current","recipe_id":"recipe"}'],
                             ['time2', 10, '', '{"dataset_id":"current","recipe_id":"recipe"}']])
        scores, skipped = refresh_scores(self.data, self.config, None, [], text)
        human = scores['recipes']['recipe']['human']
        self.assertEqual(human['stars'], 2.5)
        self.assertEqual(human['metrics'], {'overall': 2.5})
        self.assertEqual(human['count'], 2)
        self.assertEqual(skipped, 0)
        self.assertNotIn('private note', str(scores))
        self.assertNotIn('time1', str(scores))

    def test_stale_reviews_skip_but_current_invalid_reference_fails(self):
        text = self.reviews([['t', 8, '', '{"dataset_id":"retired","recipe_id":"old"}']])
        scores, skipped = refresh_scores(self.data, self.config, None, [], text)
        self.assertEqual(skipped, 1)
        self.assertEqual(scores['recipes'], {})
        for ref in ('bad json', '{"dataset_id":"current","recipe_id":"unknown"}'):
            with self.assertRaises(ValueError):
                normalize_reviews(self.reviews([['t', 8, '', ref]]), self.data, self.settings)

    def test_bad_scores_rejected(self):
        ref = '{"dataset_id":"current","recipe_id":"recipe"}'
        for entries in ([['t', 11, '', ref]], [['t', -1, '', ref]], [['t', 'nan', '', ref]]):
            with self.assertRaises(ValueError):
                refresh_scores(self.data, self.config, None, [], self.reviews(entries))

    def test_anonymous_responses_with_same_timestamp_are_distinct(self):
        ref = '{"dataset_id":"current","recipe_id":"recipe"}'
        scores, _ = refresh_scores(self.data, self.config, None, [],
                                  self.reviews([['t', 8, '', ref], ['t', 8, '', ref]]))
        self.assertEqual(scores['recipes']['recipe']['human']['count'], 2)

    def test_refresh_preserves_missing_sources_and_replaces_human(self):
        old = {'dataset_id': 'current', 'weights': self.config['score_weights'],
               'recipes': {'recipe': {'llm': {'stars': 4}, 'human': {'stars': 1}}}}
        preserved, _ = refresh_scores(self.data, self.config, old, [])
        self.assertEqual(preserved, old)
        rebuilt, _ = refresh_scores(self.data, self.config, old, [], self.reviews([]))
        self.assertEqual(rebuilt['recipes']['recipe'], {'llm': {'stars': 4}})
        changed = {**self.config, 'score_weights': {'overall': 1, 'food_pairing': 1, 'balance': 1}}
        with self.assertRaises(ValueError):
            refresh_scores(self.data, changed, old, [])

    def test_download_errors_do_not_leak_secret_urls(self):
        url = 'https://example.com/reviews?token=secret-token'
        with patch('build_site.urlopen', side_effect=URLError(url)):
            with self.assertRaises(ValueError) as error:
                download_reviews(url)
        self.assertNotIn('secret-token', str(error.exception))
        with self.assertRaises(ValueError):
            download_reviews('http://example.com/reviews')

    def test_regeneration_requires_complete_run_with_usable_recipes(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            write_json(path / 'manifest.json', {'requests_planned': 2, 'dry_run': False})
            results = path / 'results.jsonl'
            results.write_text('{"status":"ok"}\n')
            with self.assertRaises(ValueError):
                validate_run(path)
            results.write_text('{"status":"ok"}\n{"status":"api_error"}\n')
            self.assertEqual(validate_run(path), (1, 1))
            results.write_text('{"status":"api_error"}\n{"status":"api_error"}\n')
            with self.assertRaises(ValueError):
                validate_run(path)


if __name__ == '__main__':
    unittest.main()
