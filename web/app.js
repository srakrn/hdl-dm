"use strict";
const $ = (id) => document.getElementById(id);
const state = {data:null, scores:null, reveal:null, model:null, profile:null, round:"r1", showZero:false, unit:25, checked:new Map(), versions:null, version:null, dataPath:"", bundles:new Map(), allModels:[], names:new Map()};
const format = (value) => new Intl.NumberFormat("th-TH", {maximumFractionDigits:3}).format(value);
function ladleAmount(value) {
  const eighths = Math.round(value * 8);
  if (Math.abs(eighths / 8 - value) > 1e-6) return format(value);
  const whole = Math.floor(eighths / 8);
  const fraction = ["","⅛","¼","⅜","½","⅝","¾","⅞"][eighths % 8];
  return whole ? `${whole}${fraction ? " " + fraction : ""}` : fraction || "0";
}

// Original model answers use large-spoon units; display each as four small spoons.
const smallSpoonAmount = largeSpoons => ladleAmount(largeSpoons * 4);
function doseLabel(dose) {
  if (!dose.amount) return "ไม่ใส่";
  if (dose.unit === "shake") return `เขย่าเบา ๆ ${dose.amount} ครั้ง`;
  if (dose.unit === "squeeze" && dose.volume_ml === null) return `บีบสั้น ๆ ${dose.amount} ครั้ง`;
  const action = dose.unit === "squeeze" ? "บีบประมาณ" : dose.unit === "tongs" ? "คีบประมาณ" : "ตัก";
  return `${action} ${smallSpoonAmount(dose.amount)} ช้อนเล็ก`;
}

async function readData(file) {
  const response = await fetch(`./data/${file}`, {cache:"no-cache"});
  if (!response.ok) throw new Error(`Cannot load ${file}`);
  return response.json();
}
function node(tag, className, text) {
  const result = document.createElement(tag);
  if (className) result.className = className;
  if (text !== undefined) result.textContent = String(text).replace(/\bAI\b/g, "เอไอ");
  return result;
}
function modelName(model) {
  return $("reveal-toggle").checked ? state.names.get(model.id) : null;
}
function updateURL() {
  const url = new URL(location.href);
  url.searchParams.set("m", state.model);
  url.searchParams.set("p", state.profile);
  url.searchParams.set("r", state.round);
  url.searchParams.set("v", state.version);
  history.replaceState(null, "", url);
}
function renderModels() {
  $("model-select").replaceChildren(...state.allModels.map(model => {
    const realName = modelName(model);
    const bundle = nearestBundle(model.id, state.version, state.profile);
    const candidate = bundle.data.models.find(m => m.id === model.id);
    const scores = bundle.scores?.dataset_id === bundle.data.dataset_id ? candidate.recipes.flatMap(recipe => recipe.variants.map(variant => bundle.scores.recipes[variant.recipe_id]?.llm)).filter(score => score?.complete && Number.isFinite(score.stars)) : [];
    const average = scores.length ? scores.reduce((sum, score) => sum + score.stars, 0) / scores.length : null;
    const rating = average === null ? "ยังไม่มีคะแนนเฉลี่ย" : `★ ${format(Math.round(average * 10) / 10)} / 5`;
    const option = node("option", "", `${model.nickname} · ${rating}${realName ? ` — ${realName}` : ""}`);
    option.value = model.id;
    option.selected = model.id === state.model;
    return option;
  }));
}
function renderProfiles() {
  const focused = document.activeElement?.dataset.profileId;
  $("profiles").replaceChildren(...state.data.profiles.map((profile) => {
    const button = node("button", "profile-button");
    button.type = "button";
    button.dataset.profileId = profile.id;
    button.setAttribute("aria-pressed", String(profile.id === state.profile));
    button.textContent = profile.label;
    button.addEventListener("click", async () => {state.profile = profile.id; state.round = "r1"; await loadVersion(state.version); render();});
    return button;
  }));
  if (focused) [...$("profiles").children].find(button => button.dataset.profileId === focused)?.focus({preventScroll:true});
}
function showScore(source, prefix, recipeId) {
  const score = state.scores?.dataset_id === state.data.dataset_id ? state.scores.recipes[recipeId]?.[source] : null;
  if (!score) {
    $(`${prefix}-stars`).textContent = "☆☆☆☆☆";
    $(`${prefix}-note`).textContent = source === "llm" ? "ยังไม่มีคะแนนจากเอไอ" : "รอเพื่อน ๆ มาชิม";
    return;
  }
  $(`${prefix}-stars`).textContent = `★ ${format(Math.round(score.stars * 10) / 10)} / 5`;
  $(`${prefix}-note`).textContent = source === "llm" ? `ผู้ประเมิน ${score.count}/${score.expected_judges} ตัว${score.complete ? "" : " · ยังไม่ครบ"}` : `จากรีวิว ${score.count} รายการ`;
}
function renderHumanReviews(recipeId) {
  const score = state.scores?.dataset_id === state.data.dataset_id ? state.scores.recipes[recipeId]?.human : null;
  const reviews = (score?.reviews || []).filter(review => typeof review.text === "string" && review.text.trim());
  $("human-panel").hidden = !reviews.length;
  $("human-reviews").replaceChildren(...reviews.map(review => {
    const card = node("article", "human-review");
    card.append(node("p", "human-review-stars", `★ ${format(Math.round(review.stars * 10) / 10)} / 5`), node("p", "human-review-text", review.text));
    return card;
  }));
}
function renderJudges(recipeId) {
  const score = state.scores?.dataset_id === state.data.dataset_id ? state.scores.recipes[recipeId]?.llm : null;
  const reviews = score?.reviews || [];
  $("judge-panel").hidden = !reviews.length;
  $("judge-reviews").replaceChildren(...reviews.map(review => {
    const details = node("details", "judge-review");
    const summary = node("summary", "judge-summary");
    summary.append(node("span", "judge-character", review.character), node("span", "judge-stars", `★ ${format(Math.round(review.stars * 10) / 10)} / 5`));
    const content = node("div", "judge-content");
    content.append(node("p", "judge-model", review.judge_label || review.requested_model));
    content.append(node("p", "judge-critique", review.critique));
    const metrics = node("dl", "judge-metrics");
    for (const [axis, label] of Object.entries({taste:"ความอร่อย", balance:"ความกลมกล่อม", complexity:"ความซับซ้อน", novelty:"ความแปลกใหม่"})) {
      const metric = node("div", "");
      metric.append(node("dt", "", label), node("dd", "", `${format(review.metrics[axis])} / 5`));
      metrics.append(metric);
    }
    content.append(metrics);
    for (const [field, label] of Object.entries({strength:"จุดที่เข้าท่า", concern:"จุดที่น่าห่วง", suggestion:"ลองปรับแบบนี้"})) {
      const paragraph = node("p", "judge-observation");
      paragraph.append(node("strong", "", `${label}: `), document.createTextNode(review[field]));
      content.append(paragraph);
    }
    details.append(summary, content);
    return details;
  }));
}
function renderForm(recipeId) {
  const review = state.data.review;
  $("form-link").hidden = true;
  $("form-pending").hidden = false;
  if (!review.form_url) return;
  try {
    const url = new URL(review.form_url);
    if (url.protocol !== "https:" || !["docs.google.com", "forms.gle"].includes(url.hostname)) return;
    for (const [key, value] of Object.entries({dataset_id:state.data.dataset_id, recipe_id:recipeId, review_id:JSON.stringify({dataset_id:state.data.dataset_id, recipe_id:recipeId})})) {
      if (review.form_fields[key]) url.searchParams.set(review.form_fields[key], value);
    }
    $("form-link").href = url.href;
    $("form-link").hidden = false;
    $("form-pending").hidden = true;
  } catch { /* An unset or invalid form URL leaves the placeholder visible. */ }
}
function renderRecipe() {
  const model = state.data.models.find(m => m.id === state.model);
  const profile = state.data.profiles.find(p => p.id === state.profile);
  const recipe = model.recipes.find(r => r.profile_id === state.profile);
  $("recipe-title").textContent = `สูตรของ${model.nickname}`;
  $("recipe-real-name").textContent = modelName(model) || "";
  $("recipe-real-name").hidden = !modelName(model);
  $("empty-recipe").hidden = Boolean(recipe);
  $("recipe-content").hidden = !recipe;
  $("round-select").replaceChildren(...state.versions.versions.map(version => {
    const option = node("option", "", version.label);
    option.value = version.id;
    option.selected = version.id === state.version;
    return option;
  }));
  if (!recipe) return;
  if (!recipe.variants.some(v => v.id === state.round)) state.round = recipe.variants.find(v => v.id !== "average")?.id || recipe.variants[0].id;
  const variant = recipe.variants.find(v => v.id === state.round);
  const practical = state.data.method === "practical";
  $("unit-control").hidden = practical;
  $("preparation-note").textContent = practical ? "ช้อนเล็กในที่นี้ คือช้อนเล็กที่ใช้ตักส่วนผสมบาร์น้ำจิ้ม แต่ในบางสาขา ช้อนของน้ำจิ้มงาจะใหญ่กว่าเพื่อน ให้กะให้เท่าช้อนเล็กที่ใช้ตวงเครื่องปรุงอื่นๆ (ใส่แล้วติ๊กไว้ได้ จะได้ไม่ต้องจำเอง)" : "ผลการทดลองเดิม แสดงปริมาณเป็นหน่วย";
  const items = state.data.ingredients.map(i => ({...i, units:variant.units[i.id], dose:practical ? variant.servings[i.id] : null}));
  const included = item => practical ? item.dose.amount > 0 : item.units > 0;
  if (practical) {
    const order = {ladle:0, squeeze:1, shake:2, tongs:3};
    items.sort((a,b) => order[a.dose.unit] - order[b.dose.unit] || b.dose.amount - a.dose.amount || a.label.localeCompare(b.label,"th"));
  } else items.sort((a,b) => b.units - a.units || a.label.localeCompare(b.label, "th"));
  const checkKey = `${state.data.dataset_id}:${variant.recipe_id}`;
  if (!state.checked.has(checkKey)) state.checked.set(checkKey,new Set());
  const checked = state.checked.get(checkKey);
  $("ingredients").replaceChildren(...items.filter(i => state.showZero || included(i)).map(item => {
    const row = node(practical ? "label" : "div", `ingredient-row${included(item) ? "" : " is-zero"}${checked.has(item.id) ? " is-added" : ""}`);
    const name = node("div", "ingredient-name", item.label);
    if (practical && included(item)) {
      const checkbox = node("input", "ingredient-check");
      checkbox.type = "checkbox";
      checkbox.checked = checked.has(item.id);
      checkbox.setAttribute("aria-label", `ใส่${item.label}แล้ว`);
      checkbox.addEventListener("change", () => {if (checkbox.checked) checked.add(item.id); else checked.delete(item.id); row.classList.toggle("is-added",checkbox.checked);});
      name.prepend(checkbox);
    }
    if (profile.excluded.includes(item.id) && included(item)) name.append(node("span", "excluded-tag", "โจทย์ไม่ใช้"));
    const amount = node("div", "ingredient-amount", practical ? doseLabel(item.dose) : `${format(item.units)} หน่วย`);
    if (!practical) amount.append(node("small", "", `${format(item.units * state.unit)} mL`));
    row.append(name, amount);
    return row;
  }));
  const zeros = items.filter(i => !included(i)).length;
  $("show-zero").hidden = !zeros;
  $("show-zero").textContent = state.showZero ? "ซ่อนวัตถุดิบที่ไม่ใส่" : `ดูวัตถุดิบที่ไม่ใส่ (${zeros})`;
  $("show-zero").setAttribute("aria-expanded", String(state.showZero));
  if (practical) {
    const measured = items.filter(i => i.dose.volume_ml !== null).reduce((sum,i) => sum + i.dose.volume_ml / state.data.unit_ml,0);
    $("total-label").textContent = "รวมส่วนที่กะเป็นช้อน";
    $("total-volume").textContent = `${smallSpoonAmount(measured)} ช้อนเล็ก`;
  } else {
    $("total-label").textContent = "รวมหนึ่งถ้วย";
    $("total-volume").textContent = `${format(items.reduce((sum,i) => sum + i.units * state.unit, 0))} mL`;
  }
  const excluded = items.filter(i => profile.excluded.includes(i.id) && included(i));
  $("constraint-note").hidden = !excluded.length;
  $("constraint-note").textContent = `สูตรนี้ยังให้ปริมาตรกับวัตถุดิบที่โจทย์ไม่ต้องการ: ${excluded.map(i => i.label).join(", ")} เก็บคำตอบโมเดลไว้ตามจริง กรุณาตรวจสูตรก่อนชิม`;
  showScore("llm", "llm", variant.recipe_id);
  showScore("human", "human", variant.recipe_id);
  renderHumanReviews(variant.recipe_id);
  renderJudges(variant.recipe_id);
  renderForm(variant.recipe_id);
}
function render() {
  renderModels(); renderProfiles(); renderRecipe(); updateURL();
}

function hasRecipe(bundle, modelId, profileId = null) {
  const model = bundle.data.models.find(m => m.id === modelId);
  return Boolean(model?.recipes.some(recipe => (!profileId || recipe.profile_id === profileId) && recipe.variants.length));
}
function nearestBundle(modelId, versionId, profileId = null) {
  const requested = Number(versionId.slice(1));
  const all = [...state.bundles.values()];
  let candidates = all.filter(bundle => hasRecipe(bundle, modelId, profileId));
  if (!candidates.length && profileId) candidates = all.filter(bundle => hasRecipe(bundle, modelId));
  return candidates.sort((a,b) => Math.abs(Number(a.version.id.slice(1)) - requested) - Math.abs(Number(b.version.id.slice(1)) - requested) || Number(b.version.id.slice(1)) - Number(a.version.id.slice(1)))[0];
}
async function loadVersion(versionId) {
  const bundle = nearestBundle(state.model, versionId, state.profile);
  if (!bundle) throw new Error("No recipe for model");
  const {data, scores, version} = bundle;
  Object.assign(state, {data, scores, version:version.id, dataPath:version.path});
  if (!hasRecipe(bundle, state.model, state.profile)) {
    state.profile = data.models.find(m => m.id === state.model).recipes.find(recipe => recipe.variants.length).profile_id;
  }
  state.unit = data.unit_ml;
  $("unit-ml").value = state.unit;
}
async function init() {
  try {
    state.versions = await readData("versions.json");
    await Promise.all(state.versions.versions.map(async version => {
      const [data, scores] = await Promise.all([readData(`${version.path}recipes.json`), readData(`${version.path}scores.json`).catch(() => null)]);
      if (data.dataset_id !== version.dataset_id) throw new Error("Stale version data");
      state.bundles.set(version.id, {version, data, scores});
    }));
    const models = new Map();
    for (const bundle of state.bundles.values()) {
      for (const model of bundle.data.models) if (hasRecipe(bundle, model.id)) models.set(model.id, model);
    }
    state.allModels = [...models.values()].sort((a,b) => a.nickname.localeCompare(b.nickname, "th"));
    if (!state.allModels.length) throw new Error("No data");
    const params = new URL(location.href).searchParams;
    state.model = state.allModels.some(m => m.id === params.get("m")) ? params.get("m") : state.allModels[0].id;
    state.profile = params.get("p");
    state.round = params.get("r") || "r1";
    await loadVersion(state.versions.versions.some(v => v.id === params.get("v")) ? params.get("v") : state.versions.current);
    $("loading-status").hidden = true;
    $("workspace").hidden = false;
    render();
  } catch {
    $("loading-status").hidden = true;
    $("load-error").hidden = false;
    $("load-error").textContent = "เปิดสมุดสูตรไม่สำเร็จ ลองโหลดหน้าใหม่อีกครั้ง หากเปิดจากไฟล์โดยตรง ให้เปิดเว็บผ่าน HTTP server หรือ GitHub Pages";
  }
}
$("model-select").addEventListener("change", async event => {state.model = event.target.value; state.round = "r1"; await loadVersion(state.version); render();});
$("round-select").addEventListener("change", async event => {
  const version = event.target.value;
  event.target.disabled = true;
  $("share-status").textContent = "";
  try {await loadVersion(version); render();}
  catch {event.target.value = state.version; $("share-status").textContent = "เปิดสูตรรุ่นนี้ไม่สำเร็จ ลองอีกครั้งได้เลย";}
  finally {event.target.disabled = false;}
});
$("unit-ml").addEventListener("input", event => {
  const value = Number(event.target.value);
  if (Number.isFinite(value) && value >= .1 && value <= 100) {state.unit = value; renderRecipe();}
});
$("show-zero").addEventListener("click", () => {state.showZero = !state.showZero; renderRecipe();});
$("share-button").addEventListener("click", async () => {
  try {await navigator.clipboard.writeText(location.href); $("share-status").textContent = "คัดลอกลิงก์สูตรแล้ว";}
  catch {$("share-status").textContent = "คัดลอก URL จากแถบที่อยู่เพื่อแชร์สูตรนี้ได้เลย";}
});
$("reveal-toggle").addEventListener("change", async event => {
  const toggle = event.target;
  $("reveal-error").hidden = true;
  if (toggle.checked && !state.names.size) {
    toggle.disabled = true;
    try {
      const mappings = await Promise.all([...state.bundles.values()].map(async bundle => {
        const reveal = await readData(`${bundle.version.path}reveal.json`);
        if (reveal.dataset_id !== bundle.data.dataset_id) throw new Error("Stale mapping");
        return reveal.models;
      }));
      for (const mapping of mappings) for (const [id, name] of Object.entries(mapping)) state.names.set(id, name);
    } catch {
      toggle.checked = false;
      $("reveal-error").textContent = "เปิดชื่อไม่สำเร็จ ลองอีกครั้งได้เลย";
      $("reveal-error").hidden = false;
    } finally {toggle.disabled = false;}
  }
  renderModels(); renderRecipe();
});
for (const [linkId, dialogId] of [["process-link", "recipe-process"], ["versions-link", "recipe-versions"]]) {
  const dialog = $(dialogId);
  $(linkId).addEventListener("click", event => {
    event.preventDefault();
    if (!dialog.open) dialog.showModal();
  });
  dialog.addEventListener("click", event => {
    if (event.target !== dialog) return;
    const bounds = dialog.getBoundingClientRect();
    if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) dialog.close();
  });
  dialog.addEventListener("close", () => $(linkId).focus());
}
init();
