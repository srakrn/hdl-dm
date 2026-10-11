"use strict";
const rankingState = {data:null, scores:null, version:null, reveal:null};
const byId = id => document.getElementById(id);
const starsText = stars => new Intl.NumberFormat('th-TH', {minimumFractionDigits:2, maximumFractionDigits:2}).format(stars);
async function boardData(file) {
  const response = await fetch(`./data/${file}`, {cache:'no-cache'});
  if (!response.ok) throw new Error('Cannot load leaderboard');
  return response.json();
}
function buildBoard(data, scores, profileId) {
  if (scores.dataset_id !== data.dataset_id) throw new Error('Scores belong to another recipe version');
  const rows = [];
  for (const model of data.models) {
    const recipe = model.recipes.find(r => r.profile_id === profileId && r.variants.length);
    if (!recipe) continue;
    const reviews = recipe.variants.map(v => scores.recipes[v.recipe_id]?.llm);
    const complete = reviews.every(s => s?.complete && s.expected_judges === 3 && s.count === s.expected_judges && Number.isFinite(s.stars) && s.stars >= 0 && s.stars <= 5);
    rows.push({model, variant:recipe.variants[0], samples:recipe.variants.length,
      stars:complete ? reviews.reduce((sum,s) => sum + s.stars, 0) / reviews.length : null});
  }
  rows.sort((a,b) => (b.stars ?? -1) - (a.stars ?? -1) || a.model.nickname.localeCompare(b.model.nickname,'th'));
  let previous = null, rank = 0;
  return rows.map((row,index) => {
    if (row.stars !== null && row.stars !== previous) rank = index + 1;
    previous = row.stars;
    return {...row, rank:row.stars === null ? null : rank};
  });
}
function boardNode(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}
function renderBoards() {
  const sections = rankingState.data.profiles.map(profile => {
    const section = boardNode('section','leaderboard-card');
    const title = boardNode('h2','',profile.label);
    title.id = `board-${profile.id}`;
    section.setAttribute('aria-labelledby',title.id);
    section.append(title);
    const rows = buildBoard(rankingState.data, rankingState.scores, profile.id);
    if (!rows.length) {section.append(boardNode('p','muted','รุ่นล่าสุดยังไม่มีสูตรนี้'));return section;}
    const table = boardNode('table','leaderboard-table');
    const head = document.createElement('thead');
    const headers = document.createElement('tr');
    for (const label of ['อันดับ','โมเดล','คะแนน / 5']) {const th=boardNode('th','',label);th.scope='col';headers.append(th);}
    head.append(headers);table.append(head);
    const body = document.createElement('tbody');
    for (const row of rows) {
      const tr = boardNode('tr',row.rank === 1 ? 'is-first' : '');
      const name = document.createElement('td');
      const link = boardNode('a','',row.model.nickname);
      const url = new URL('./', location.href);
      for (const [key,value] of Object.entries({m:row.model.id,p:profile.id,r:row.variant.id,v:rankingState.version.id})) url.searchParams.set(key,value);
      link.href = url.href;
      name.append(link);
      if (byId('leaderboard-reveal').checked) name.append(boardNode('small','leaderboard-model-id',rankingState.reveal.models[row.model.id]));
      if (row.samples > 1) name.append(boardNode('small','muted',`เฉลี่ย ${row.samples} สูตร`));
      tr.append(boardNode('td','leaderboard-rank',row.rank === null ? '—' : row.rank),name,
        boardNode('td','leaderboard-stars',row.stars === null ? 'รอคะแนนครบ' : starsText(row.stars)));
      body.append(tr);
    }
    table.append(body);section.append(table);return section;
  });
  byId('leaderboards').replaceChildren(...sections);
}
byId('leaderboard-reveal').addEventListener('change', async event => {
  const toggle = event.target;
  try {
    if (toggle.checked && !rankingState.reveal) {
      toggle.disabled = true;
      const reveal = await boardData(`${rankingState.version.path}reveal.json`);
      if (reveal.dataset_id !== rankingState.data.dataset_id) throw new Error('Stale names');
      rankingState.reveal = reveal;
    }
    byId('leaderboard-error').hidden = true;renderBoards();
  } catch {toggle.checked=false;byId('leaderboard-error').textContent='เปิดชื่อไม่สำเร็จ ลองอีกครั้งได้เลย';byId('leaderboard-error').hidden=false;}
  finally {toggle.disabled=false;}
});
async function initBoard() {
  try {
    const versions = await boardData('versions.json');
    const version = versions.versions.find(v => v.id === versions.current);
    if (!version) throw new Error('Unknown latest version');
    const [data,scores] = await Promise.all([boardData(`${version.path}recipes.json`),boardData(`${version.path}scores.json`)]);
    if (data.dataset_id !== version.dataset_id) throw new Error('Stale latest version');
    Object.assign(rankingState,{version,data,scores});
    byId('latest-version').textContent = `(${version.label})`;
    renderBoards();byId('leaderboards').hidden=false;byId('leaderboard-status').hidden=true;byId('leaderboard-reveal').disabled=false;
  } catch {byId('leaderboard-status').hidden=true;byId('leaderboard-error').textContent='โหลดอันดับไม่สำเร็จ ลองโหลดหน้าใหม่อีกครั้ง';byId('leaderboard-error').hidden=false;}
}
initBoard();
