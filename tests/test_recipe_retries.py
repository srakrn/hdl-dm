import json
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from retry_failed_recipes import retry_jobs
class RetryTests(unittest.TestCase):
 def test_preserves_success_and_stops_when_failed_job_succeeds(self):
  self.run_case(2,2)
 def test_never_exceeds_five_additional_attempts(self):
  self.run_case(99,5)
 def run_case(self,succeed_after,expected_calls):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);manifest={'requests_planned':2,'repeats':1,'ingredient_catalog':[],'preparation':{},'prompt_version':'fixture','unit_ml':5}
   (root/'manifest.json').write_text(json.dumps(manifest))
   success={'model':'kept','profile_id':'thai_mild','status':'ok','original':'untouched'}
   failure={'model':'retry','profile_id':'thai_mild','status':'api_error'}
   (root/'results.jsonl').write_text(json.dumps(success)+'\n'+json.dumps(failure)+'\n')
   calls=[]
   def attempt(argv,**kwargs):
    calls.append(argv);folder=Path(argv[argv.index('--out')+1]);folder.mkdir()
    (folder/'manifest.json').write_text(json.dumps(manifest))
    row={**failure,'status':'ok' if len(calls)>=succeed_after else 'api_error'}
    (folder/'results.jsonl').write_text(json.dumps(row)+'\n')
    return SimpleNamespace(returncode=0)
   with patch('retry_failed_recipes.subprocess.run',side_effect=attempt),patch('retry_failed_recipes.export_reports'),patch('retry_failed_recipes.summary',return_value={}):
    remaining=retry_jobs(root,rounds=5,workers=1)
   rows=[json.loads(l) for l in (root/'results.jsonl').read_text().splitlines()]
   self.assertEqual(rows[0],success);self.assertEqual(len(calls),expected_calls)
   self.assertEqual(remaining,int(succeed_after>5))
   self.assertTrue((root/'initial-results.jsonl').exists())
