import csv
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from benchmark import ROOT, read_json, write_json
from recipe_versions import prepare_versions
import build_site


class RecipeVersionTests(unittest.TestCase):
    def test_published_v1_is_the_original_fifty_percent_dataset(self):
        root = ROOT / 'web/data'
        index = read_json(root / 'versions.json')
        version = next(v for v in index['versions'] if v['id'] == 'v1')
        data = read_json(root / version['path'] / 'recipes.json')
        self.assertEqual(data['preparation']['selection_threshold'], .5)
        self.assertEqual(version['dataset_id'], '8addfc43b935cfcd08f5')
        self.assertEqual(data['dataset_id'], version['dataset_id'])
        for name in ('scores.json', 'judgments.json', 'reveal.json'):
            self.assertEqual(read_json(root / version['path'] / name)['dataset_id'], data['dataset_id'])

    def test_new_dataset_archives_existing_recipes_and_bound_scores(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            old = {'dataset_id': 'old', 'recipe': 'original'}
            score = {'dataset_id': 'old', 'stars': 4}
            write_json(root / 'recipes.json', old)
            write_json(root / 'scores.json', score)
            index = prepare_versions(root, 'new')
            self.assertEqual(read_json(root / 'versions/v1/recipes.json'), old)
            self.assertEqual(read_json(root / 'versions/v1/scores.json'), score)
            self.assertEqual(index['current'], 'v2')
            self.assertEqual([v['label'] for v in index['versions']], ['รุ่นที่ 1', 'รุ่นที่ 2'])
            write_json(root / 'versions.json', index)
            write_json(root / 'recipes.json', {'dataset_id': 'new'})
            self.assertEqual(prepare_versions(root, 'new'), index)
            next_index = prepare_versions(root, 'third')
            self.assertEqual(next_index['current'], 'v3')
            self.assertEqual(read_json(root / 'versions/v2/recipes.json')['dataset_id'], 'new')
            self.assertEqual(read_json(root / 'versions/v1/recipes.json'), old)

    def test_build_refreshes_reviews_for_each_version_without_mixing_scores(self):
        config = read_json(ROOT / 'config/review.json')
        settings = config['review_import']
        stream = io.StringIO()
        writer = csv.writer(stream)
        writer.writerow([settings['response_id_column'], settings['columns']['overall'], settings['columns']['notes'], settings['review_id_column']])
        writer.writerow(['old-rating', 2, '', '{"dataset_id":"old","recipe_id":"same-id"}'])
        writer.writerow(['new-rating', 10, '', '{"dataset_id":"new","recipe_id":"same-id"}'])
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / 'versions/v1'
            archive.mkdir(parents=True)
            for folder, dataset in [(root, 'new'), (archive, 'old')]:
                write_json(folder / 'recipes.json', {'dataset_id': dataset, 'models': [{'recipes': [{'variants': [{'recipe_id': 'same-id'}]}]}]})
                write_json(folder / 'reveal.json', {'dataset_id': dataset, 'models': {}})
                write_json(folder / 'scores.json', {'dataset_id': dataset, 'weights': config['score_weights'], 'recipes': {'same-id': {'llm': {'stars': 3.7}}}})
            write_json(root / 'versions.json', {'current': 'v2', 'versions': [
                {'id': 'v1', 'path': 'versions/v1/', 'dataset_id': 'old'},
                {'id': 'v2', 'path': '', 'dataset_id': 'new'}]})
            with patch.object(sys, 'argv', ['build_site.py', '--data-dir', str(root)]), patch.object(build_site, 'download_reviews', return_value=stream.getvalue()):
                build_site.main()
            old_score = read_json(archive / 'scores.json')['recipes']['same-id']
            new_score = read_json(root / 'scores.json')['recipes']['same-id']
            self.assertEqual(old_score['human']['stars'], 1)
            self.assertEqual(new_score['human']['stars'], 5)
            self.assertEqual(old_score['llm']['stars'], 3.7)
