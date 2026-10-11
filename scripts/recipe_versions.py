"""Keep published recipe datasets and their bound scores available by version."""
import shutil
from benchmark import read_json

PUBLIC_FILES = ('recipes.json', 'reveal.json', 'scores.json', 'judgments.json', 'ratings-template.csv')


def prepare_versions(data_dir, dataset_id):
    index_path = data_dir / 'versions.json'
    if index_path.exists():
        index = read_json(index_path)
    else:
        old = data_dir / 'recipes.json'
        index = {'current': 'v1', 'versions': [{'id': 'v1', 'label': 'รุ่นที่ 1', 'path': '',
                  'dataset_id': read_json(old)['dataset_id'] if old.exists() else dataset_id}]}
    current = next(v for v in index['versions'] if v['id'] == index['current'])
    if current['dataset_id'] == dataset_id:
        return index
    archive = data_dir / 'versions' / current['id']
    archive.mkdir(parents=True, exist_ok=True)
    for name in PUBLIC_FILES:
        source = data_dir / name
        if source.exists():
            shutil.copy2(source, archive / name)
    current['path'] = f"versions/{current['id']}/"
    number = max(int(v['id'][1:]) for v in index['versions']) + 1
    version = {'id': f'v{number}', 'label': f'รุ่นที่ {number}', 'path': '', 'dataset_id': dataset_id}
    index['versions'].append(version)
    index['current'] = version['id']
    return index
