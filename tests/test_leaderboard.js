const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const context = vm.createContext({document:{getElementById(){return {addEventListener(){}}}}});
vm.runInContext(fs.readFileSync('web/leaderboard.js','utf8').replace(/\ninitBoard\(\);\s*$/,'') + '\nthis.buildBoard=buildBoard;',context);
const score = stars => ({stars,complete:true,count:3,expected_judges:3});
const model = (id,profile='mild',variants=['r1']) => ({id,nickname:id,recipes:[{profile_id:profile,variants:variants.map(v => ({id:v,recipe_id:`${id}-${v}`}))}]});
test('profile-specific ranking supports zero, tied ranks, and incomplete reviews',()=>{
 const data={dataset_id:'latest',models:[model('a'),model('b'),model('zero'),model('pending'),model('other','spicy')]};
 const scores={dataset_id:'latest',recipes:{'a-r1':{llm:score(4)},'b-r1':{llm:score(4)},'zero-r1':{llm:score(0)},'pending-r1':{llm:{...score(5),count:2,complete:false}},'other-r1':{llm:score(5)}}};
 const rows=context.buildBoard(data,scores,'mild');
 assert.deepEqual(Array.from(rows,r=>r.model.id),['a','b','zero','pending']);
 assert.deepEqual(Array.from(rows,r=>r.rank),[1,1,3,null]);assert.equal(rows[2].stars,0);
});
test('multiple rounds are averaged rather than selecting the best round',()=>{
 const data={dataset_id:'latest',models:[model('a','mild',['r1','r2'])]};
 const scores={dataset_id:'latest',recipes:{'a-r1':{llm:score(1)},'a-r2':{llm:score(5)}}};
 assert.equal(context.buildBoard(data,scores,'mild')[0].stars,3);
 delete scores.recipes['a-r2'];assert.equal(context.buildBoard(data,scores,'mild')[0].rank,null);
});
test('scores from an older version cannot enter the latest leaderboard',()=>{
 assert.throws(()=>context.buildBoard({dataset_id:'latest',models:[]},{dataset_id:'old',recipes:{}},'mild'),/another recipe version/);
});
