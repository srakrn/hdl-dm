#!/usr/bin/env python3
"""Refresh an existing public dataset and import ratings, without model calls."""

import argparse
import csv
import io
import hashlib
import math
import json
import os
import re
from pathlib import Path
import tempfile
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from benchmark import ROOT, read_json, write_json
from calculate_scores import METRICS, calculate_scores
from judge_recipes import aggregate_judgments

FIELDS = ('dataset_id', 'recipe_id', 'source', 'judge_id', *METRICS, 'notes')
MAX_CSV_BYTES = 10 * 1024 * 1024


def download_reviews(url):
    if urlparse(url).scheme != 'https':
        raise ValueError('REVIEW_CSV_URL must be an HTTPS CSV export URL')
    try:
        with urlopen(Request(url, headers={'Accept': 'text/csv'}), timeout=60) as response:
            if urlparse(response.geturl()).scheme != 'https':
                raise ValueError('Review export redirected outside HTTPS')
            body = response.read(MAX_CSV_BYTES + 1)
    except URLError:
        # Export URLs may contain credentials; never echo the URL or server error.
        raise ValueError('Could not download review CSV; check export access and REVIEW_CSV_URL') from None
    if len(body) > MAX_CSV_BYTES:
        raise ValueError('Review CSV exceeds 10 MiB')
    return body.decode('utf-8-sig')


def normalize_reviews(text, dataset, settings):
    columns = {field: field for field in FIELDS}
    columns.update(settings.get('columns', {}))
    reference_column = settings.get('review_id_column')
    reader = csv.DictReader(io.StringIO(text))
    metrics = settings.get('metrics', ['overall'] if settings.get('response_id_column') else list(METRICS))
    required = {columns[field] for field in metrics}
    required.add(settings['response_id_column'] if settings.get('response_id_column') else columns['judge_id'])
    required.update({reference_column} if reference_column else {columns['dataset_id'], columns['recipe_id']})
    if not required.issubset(reader.fieldnames or []):
        raise ValueError('Review CSV is missing configured columns; check config/review.json review_import')
    recipes = {v['recipe_id'] for m in dataset['models'] for r in m['recipes'] for v in r['variants']}
    rows, skipped = [], 0
    for row_number, row in enumerate(reader, 2):
        if not any((row.get(columns[m]) or '').strip() for m in METRICS):
            continue
        try:
            ref = json.loads(row[reference_column]) if reference_column else {
                'dataset_id': row[columns['dataset_id']], 'recipe_id': row[columns['recipe_id']]}
            if not isinstance(ref, dict) or not all(isinstance(ref.get(k), str) and ref[k] for k in ('dataset_id', 'recipe_id')):
                raise ValueError()
        except (ValueError, TypeError, KeyError):
            raise ValueError(f'Invalid recipe reference at CSV row {row_number}') from None
        if ref['dataset_id'] != dataset['dataset_id']:
            skipped += 1
            continue
        if ref['recipe_id'] not in recipes:
            raise ValueError(f'Unknown recipe reference at CSV row {row_number}')
        entry = {**ref, 'source': settings.get('source', 'human'),
                 **{field: row.get(columns[field], '') for field in ('judge_id', *METRICS, 'notes')}}
        if settings.get('response_id_column'):
            response_id = row[settings['response_id_column']].strip()
            if not response_id:
                raise ValueError(f'Missing response timestamp at CSV row {row_number}')
            entry['judge_id'] = hashlib.sha256(json.dumps([row_number, response_id, ref], sort_keys=True).encode()).hexdigest()[:24]
        divisor = settings.get('score_divisor', 1)
        if type(divisor) not in (int, float) or not math.isfinite(divisor) or divisor <= 0:
            raise ValueError('score_divisor must be finite and positive')
        for metric in metrics:
            entry[metric] = str(float(entry[metric]) / divisor)
        rows.append(entry)
    return rows, skipped


def refresh_scores(dataset, config, old_scores, rating_paths, review_text=None):
    paths = list(rating_paths)
    imported_sources = set()
    if paths:
        for path in paths:
            with Path(path).open(encoding='utf-8-sig', newline='') as f:
                for row in csv.DictReader(f):
                    if any((row.get(m) or '').strip() for m in METRICS):
                        imported_sources.add(row.get('source'))
    skipped = 0
    with tempfile.TemporaryDirectory() as temp:
        if review_text is not None:
            settings = config.get('review_import', {})
            source = settings.get('source', 'human')
            if source not in ('human', 'llm'):
                raise ValueError('review_import.source must be human or llm')
            imported_sources.add(source)
            rows, skipped = normalize_reviews(review_text, dataset, settings)
            path = Path(temp) / 'reviews.csv'
            with path.open('w', encoding='utf-8', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=FIELDS)
                writer.writeheader()
                writer.writerows(rows)
            paths.append(path)
        scores = calculate_scores(dataset, paths, config)
    if old_scores:
        if old_scores['dataset_id'] != dataset['dataset_id']:
            raise ValueError('Existing scores belong to another dataset')
        if old_scores['weights'] != scores['weights'] and any(
                source not in imported_sources for sources in old_scores['recipes'].values() for source in sources):
            raise ValueError('Score weights changed; provide raw ratings for every existing source')
        for recipe, sources in old_scores['recipes'].items():
            for source, score in sources.items():
                if source not in imported_sources:
                    scores['recipes'].setdefault(recipe, {})[source] = score
    return scores, skipped


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=ROOT / 'web/data')
    parser.add_argument('--config', type=Path, default=ROOT / 'config/review.json')
    parser.add_argument('--ratings', nargs='*', type=Path, default=[])
    parser.add_argument('--reviews-csv', type=Path, help='Local CSV, instead of REVIEW_CSV_URL')
    args = parser.parse_args()
    try:
        dataset = read_json(args.data_dir / 'recipes.json')
        config = read_json(args.config)
        reveal = read_json(args.data_dir / 'reveal.json')
        if reveal['dataset_id'] != dataset['dataset_id']:
            raise ValueError('Recipes and reveal belong to different datasets')
        url = os.environ.get('REVIEW_CSV_URL', '').strip() or config.get('review_import', {}).get('csv_url', '')
        text = args.reviews_csv.read_text(encoding='utf-8-sig') if args.reviews_csv else download_reviews(url) if url else None
        old_path = args.data_dir / 'scores.json'
        scores, skipped = refresh_scores(dataset, config, read_json(old_path) if old_path.exists() else None, args.ratings, text)
        judgments_path = args.data_dir / 'judgments.json'
        if judgments_path.exists():
            judgments = read_json(judgments_path)
            llm_scores = aggregate_judgments(dataset, judgments, read_json(ROOT / 'config/judges.json'))
            for sources in scores['recipes'].values():
                sources.pop('llm', None)
            for recipe_id, score in llm_scores.items():
                scores['recipes'].setdefault(recipe_id, {})['llm'] = score
            scores['recipes'] = {recipe: sources for recipe, sources in scores['recipes'].items() if sources}
        versions_path = args.data_dir / 'versions.json'
        if versions_path.exists():
            versions = read_json(versions_path)
            for version in versions['versions']:
                if not version['path']:
                    if version['dataset_id'] != dataset['dataset_id']:
                        raise ValueError('Current version points to another dataset')
                    continue
                archive = args.data_dir / version['path']
                historical = read_json(archive / 'recipes.json')
                if historical['dataset_id'] != version['dataset_id']:
                    raise ValueError('Archived version points to another dataset')
                # Historical critics keep their original rubric and scores.
                archived_scores, _ = refresh_scores(historical, config, read_json(archive / 'scores.json'), [], text)
                historical['review'] = {'form_url': config.get('form_url'), 'form_fields': config.get('form_fields', {})}
                write_json(archive / 'scores.json', archived_scores)
                write_json(archive / 'recipes.json', historical)
        dataset['review'] = {'form_url': config.get('form_url'), 'form_fields': config.get('form_fields', {})}
        write_json(args.data_dir / 'recipes.json', dataset)
        write_json(old_path, scores)
        for page, assets in [('index.html', ('app.js', 'styles.css')), ('leaderboard.html', ('leaderboard.js', 'styles.css'))]:
            index_path = args.data_dir.parent / page
            if index_path.exists():
                html = index_path.read_text(encoding='utf-8')
                for asset in assets:
                    version = hashlib.sha256((index_path.parent / asset).read_bytes()).hexdigest()[:12]
                    html = re.sub(r'\./' + re.escape(asset) + r'(?:\?v=[^"]*)?', f'./{asset}?v={version}', html)
                index_path.write_text(html, encoding='utf-8')
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    print(f"Built site data: {len(scores['recipes'])} scored recipes; skipped {skipped} retired-dataset reviews")
    if text is None:
        print('No review export configured; retained existing scores. No model calls were made.')


if __name__ == '__main__':
    main()
