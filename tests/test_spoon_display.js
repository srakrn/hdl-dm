const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const context = vm.createContext({document:{getElementById:()=>({addEventListener(){}})}});
vm.runInContext(fs.readFileSync('web/app.js','utf8').replace(/\ninit\(\);\s*$/, '')+'\nthis.api={smallSpoonAmount,doseLabel};',context);
const {smallSpoonAmount,doseLabel}=context.api;
test('original portions convert to small spoons for every measured dispenser',()=>{
  for (const [old,converted] of [[.125,'½'],[.25,'1'],[.5,'2'],[1,'4'],[2,'8']]) {
    assert.equal(smallSpoonAmount(old),converted);
    for (const [unit,action] of [['ladle','ตัก'],['squeeze','บีบประมาณ'],['tongs','คีบประมาณ']]) {
      assert.equal(doseLabel({amount:old,unit,volume_ml:old*25}),`${action} ${converted} ช้อนเล็ก`);
    }
  }
  assert.equal(doseLabel({amount:2.75,unit:'part',volume_ml:13.75}),'ตัก 2 ¾ ช้อนตวง');
  assert.equal(doseLabel({amount:.25,unit:'part',volume_ml:1.25}),'ตัก ¼ ช้อนตวง');
  assert.equal(smallSpoonAmount(1.375),'5 ½');
  assert.equal(doseLabel({amount:0,unit:'ladle',volume_ml:0}),'ไม่ใส่');
  assert.equal(doseLabel({amount:2,unit:'shake',volume_ml:null}),'เขย่าเบา ๆ 2 ครั้ง');
  assert.equal(doseLabel({amount:1,unit:'squeeze',volume_ml:null}),'บีบสั้น ๆ 1 ครั้ง');
});
test('both published versions convert without changing original answers or review IDs',()=>{
  for(const path of ['web/data/recipes.json','web/data/versions/v1/recipes.json']) {
    const data=JSON.parse(fs.readFileSync(path,'utf8'));
    const before=JSON.stringify(data);
    let converted=0;
    for(const model of data.models) for(const recipe of model.recipes) for(const variant of recipe.variants) {
      for(const dose of Object.values(variant.servings)) {
        if(dose.amount>0 && ['part','ladle','squeeze','tongs'].includes(dose.unit) && dose.volume_ml!==null) {
          assert.equal(doseLabel(dose).includes(dose.unit==='part' ? 'ช้อนตวง' : 'ช้อนเล็ก'),true);converted++;
        }
      }
    }
    assert.ok(converted>0);
    assert.equal(JSON.stringify(data),before);
  }
});
