import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import benchmark as b
from practical import validate_config,selection_payload,amount_payload,dose_options,parse_choice
class PartsTests(unittest.TestCase):
 def test_options_units_and_rejection(self):
  c=b.read_json(b.ROOT/'config/preparation.json');validate_config(c,b.INGREDIENTS)
  for name in b.INGREDIENTS:
   o=dose_options(name,c);self.assertEqual(len(o),20)
   self.assertEqual(o['parts_quarters_1'],{'amount':.25,'unit':'part','volume_ml':1.25})
   self.assertIn('parts_quarters_11',o);self.assertIn('parts_quarters_18',o)
   for key in ['parts_quarters_13','parts_quarters_22']:
    with self.assertRaises(ValueError):parse_choice({'answers':{name:{'type':'choice','choice':key,'probabilities':{}}}},name,o)
   key='parts_quarters_11';self.assertEqual(parse_choice({'answers':{name:{'type':'choice','choice':key,'probabilities':{k:int(k==key) for k in o}}}},name,o)['amount'],2.75)
 def test_payloads_have_no_physical_units_and_keep_prior_parts(self):
  c=b.read_json(b.ROOT/'config/preparation.json');p=selection_payload(b.build_payload('test/model',b.read_json(b.ROOT/'config/profiles.json')[0],5),c)
  previous={'salt':{'amount':.25,'unit':'part','volume_ml':1.25}}
  q,_=amount_payload(p,'lime_juice',['salt','lime_juice'],previous,b.INGREDIENT_CATALOG,c)
  for payload in [p,q]:
   text=json.dumps(payload).lower()
   for token in ['ml','ladle','squeeze','shaker','tongs','spoon','chinese_barbecue_sauce','chili_oil']:
    self.assertNotIn(token,text)
  self.assertEqual(q['state']['doses_already_chosen'],{'salt':{'amount':.25,'unit':'part'}})

 def test_judges_receive_calibrated_units_without_unavailable_sauces(self):
  from judge_recipes import build_payload
  recipe={'measurement_mode':'volume_parts','ingredients':[{'name':'น้ำปลา (Fish sauce)','amount':.25,'approximate_volume_ml':1.25}]}
  c=b.read_json(b.ROOT/'config/judges.json');payload=build_payload(c['judges'][0],recipe)
  text=payload['messages'][0]['content']
  self.assertIn('ช้อนตวง 5 mL',text)
  for token in ['ช้อนใหญ่คือ','ซอสบาร์บีคิวจีน','น้ำมันพริก']:
   self.assertNotIn(token,text)
