const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function app() {
  const elements = new Map();
  const context = vm.createContext({document:{getElementById(id) {
    if (!elements.has(id)) elements.set(id, {addEventListener(){}, value:null});
    return elements.get(id);
  }}});
  const source = fs.readFileSync('web/app.js','utf8').replace(/\ninit\(\);\s*$/, '');
  vm.runInContext(source + '\nthis.api = {state, hasRecipe, nearestBundle, loadVersion};', context);
  return context.api;
}
function bundle(number, profiles) {
  return {version:{id:`v${number}`,path:''},data:{unit_ml:25,profiles:[{id:'mild'},{id:'spicy'}], models:[{id:'chosen',recipes:profiles.map(profile_id => ({profile_id,variants:[{id:'r1'}]}))}]},scores:{}};
}
test('missing version keeps the selected model and chooses its closest recipe', async () => {
  const {state,loadVersion}=app();
  state.model='chosen';state.profile='mild';
  state.bundles.set('v1',bundle(1,['mild']));state.bundles.set('v2',bundle(2,[]));
  await loadVersion('v2');
  assert.equal(state.model,'chosen');assert.equal(state.version,'v1');
});
test('profile fallback chooses a version with that profile before another profile', () => {
  const {state,nearestBundle}=app();
  state.bundles.set('v1',bundle(1,['mild']));state.bundles.set('v2',bundle(2,['spicy']));
  assert.equal(nearestBundle('chosen','v2','mild').version.id,'v1');
  assert.equal(nearestBundle('chosen','v2','spicy').version.id,'v2');
});
test('equal-distance versions prefer the newer version and exclude empty recipes', () => {
  const {state,nearestBundle,hasRecipe}=app();
  state.bundles.set('v1',bundle(1,['mild']));state.bundles.set('v2',bundle(2,[]));state.bundles.set('v3',bundle(3,['mild']));
  assert.equal(nearestBundle('chosen','v2','mild').version.id,'v3');
  assert.equal(hasRecipe(state.bundles.get('v2'),'chosen'),false);
});

test('a model with no recipe for the requested profile opens one it actually has', async () => {
  const {state,loadVersion}=app();state.model='chosen';state.profile='spicy';
  state.bundles.set('v1',bundle(1,['mild']));state.bundles.set('v2',bundle(2,[]));
  await loadVersion('v2');
  assert.equal(state.model,'chosen');assert.equal(state.version,'v1');assert.equal(state.profile,'mild');
});
