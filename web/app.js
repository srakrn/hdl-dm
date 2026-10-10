"use strict";
const $ = (id) => document.getElementById(id);
const state = {data:null, scores:null, reveal:null, model:null, profile:null, round:"r1", showZero:false, unit:25, checked:new Map()};
const format = (value) => new Intl.NumberFormat("th-TH", {maximumFractionDigits:3}).format(value);
function ladleAmount(value) {
  const eighths = Math.round(value * 8);
  if (Math.abs(eighths / 8 - value) > 1e-6) return format(value);
  const whole = Math.floor(eighths / 8);
  const fraction = ["","⅛","¼","⅜","½","⅝","¾","⅞"][eighths % 8];
  return whole ? `${whole}${fraction ? " " + fraction : ""}` : fraction || "0";
}

async function readData(file) {
  const response = await fetch(`./data/${file}`, {cache:"no-cache"});
  if (!response.ok) throw new Error(`Cannot load ${file}`);
  return response.json();
}
function node(tag, className, text) {
  const result = document.createElement(tag);
  if (className) result.className = className;
  if (text !== undefined) result.textContent = text;
  return result;
}
function modelName(model) {
  return $("reveal-toggle").checked ? state.reveal?.models[model.id] : null;
}
function updateURL() {
  const url = new URL(location.href);
  url.searchParams.set("m", state.model);
  url.searchParams.set("p", state.profile);
  url.searchParams.set("r", state.round);
  history.replaceState(null, "", url);
}
function renderModels() {
  $("model-select").replaceChildren(...state.data.models.filter(model => model.recipes.length).map(model => {
    const realName = modelName(model);
    const option = node("option", "", realName ? `${model.nickname} — ${realName}` : model.nickname);
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
    button.addEventListener("click", () => {state.profile = profile.id; state.round = "r1"; render();});
    return button;
  }));
  if (focused) [...$("profiles").children].find(button => button.dataset.profileId === focused)?.focus({preventScroll:true});
}
function showScore(source, prefix, recipeId) {
  const score = state.scores?.dataset_id === state.data.dataset_id ? state.scores.recipes[recipeId]?.[source] : null;
  if (!score) {
    $(`${prefix}-stars`).textContent = "☆☆☆☆☆";
    $(`${prefix}-note`).textContent = source === "llm" ? "ยังไม่มีคะแนนจาก LLM" : "รอเพื่อน ๆ มาชิม";
    return;
  }
  $(`${prefix}-stars`).textContent = `★ ${format(Math.round(score.stars * 10) / 10)} / 5`;
  $(`${prefix}-note`).textContent = source === "llm" ? `ผู้ประเมิน ${score.count}/${score.expected_judges} ตัว${score.complete ? "" : " · ยังไม่ครบ"}` : `จากรีวิว ${score.count} รายการ`;
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
  $("round-select").disabled = !recipe;
  $("round-select").replaceChildren();
  if (!recipe) return;
  if (!recipe.variants.some(v => v.id === state.round)) state.round = recipe.variants.find(v => v.id !== "average")?.id || recipe.variants[0].id;
  for (const variant of recipe.variants) {
    const option = node("option", "", variant.label);
    option.value = variant.id;
    option.selected = variant.id === state.round;
    $("round-select").append(option);
  }
  const variant = recipe.variants.find(v => v.id === state.round);
  const practical = state.data.method === "practical";
  $("unit-control").hidden = practical;
  $("preparation-note").textContent = practical ? `ช้อนใหญ่ ≈ ${format(state.data.unit_ml)} mL · ตักอย่างน้อย ⅛ ช้อน · ติ๊กเมื่อใส่แล้ว` : "ผลการทดลองเดิม ยังไม่ได้สร้างสูตรตามช้อนใหญ่ 25 mL";
  const amountLabel = dose => {
    if (!dose.amount) return "ไม่ใส่";
    if (dose.unit === "squeeze" && dose.volume_ml === null) return `บีบสั้น ๆ ${dose.amount} ครั้ง`;
    if (dose.unit === "squeeze") return `บีบประมาณ ${ladleAmount(dose.amount)} ช้อนใหญ่`;
    if (dose.unit === "shake") return `เขย่าเบา ๆ ${dose.amount} ครั้ง`;
    return `${dose.unit === "tongs" ? "คีบประมาณ" : "ตัก"} ${ladleAmount(dose.amount)} ช้อนใหญ่`;
  };
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
    const amount = node("div", "ingredient-amount", practical ? amountLabel(item.dose) : `${format(item.units)} หน่วย`);
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
    const unmeasured = items.some(i => i.dose.volume_ml === null && included(i));
    $("total-label").textContent = "รวมส่วนที่กะเป็นช้อน";
    $("total-volume").textContent = `${ladleAmount(measured)} ช้อนใหญ่`;
    $("recipe-note").textContent = `คนให้เข้ากันก่อนจิ้ม อาหารลวกน้ำเปล่า · สูตรนี้ใช้ ${items.filter(included).length} วัตถุดิบ${unmeasured ? " · ยังไม่รวมปริมาตรจาก shaker" : ""}`;
    $("technical-note").textContent = `ช้อนใหญ่ ${format(state.data.unit_ml)} mL; ⅛ ช้อน ≈ ${format(state.data.unit_ml / 8)} mL. ส่วนที่กะเป็นช้อนรวมประมาณ ${format(measured * state.data.unit_ml)} mL. ขวดบีบกะปริมาณเทียบช้อนใหญ่ ปริมาตรต่อครั้งของ shaker ยังไม่ได้วัด จึงไม่แปลงจำนวนครั้งเป็น mL. สูตรเป็นคำตอบของรอบที่เลือก ไม่เฉลี่ยข้ามรอบ.`;
  } else {
    $("total-label").textContent = "รวมหนึ่งถ้วย";
    $("total-volume").textContent = `${format(items.reduce((sum,i) => sum + i.units * state.unit, 0))} mL`;
    $("recipe-note").textContent = "ตัวเลขเดิมเป็นค่า Noul ที่นำมาใช้เป็นปริมาตร ยังต้องลองชิมจริง";
    $("technical-note").textContent = "ผลเดิมไม่ได้เลือกจำนวนช้อนด้วย Choice; อย่าเปลี่ยนหน่วยเดิมเป็นช้อน 25 mL โดยตรง เพราะจะเปลี่ยนสูตร ต้องรันด้วย --method practical เพื่อสร้างสูตรใหม่";
  }
  const excluded = items.filter(i => profile.excluded.includes(i.id) && included(i));
  $("constraint-note").hidden = !excluded.length;
  $("constraint-note").textContent = `สูตรนี้ยังให้ปริมาตรกับวัตถุดิบที่โจทย์ไม่ต้องการ: ${excluded.map(i => i.label).join(", ")} เก็บคำตอบโมเดลไว้ตามจริง กรุณาตรวจสูตรก่อนชิม`;
  showScore("llm", "llm", variant.recipe_id);
  showScore("human", "human", variant.recipe_id);
  renderJudges(variant.recipe_id);
  renderForm(variant.recipe_id);
}
function render() {
  renderModels(); renderProfiles(); renderRecipe(); updateURL();
}

async function init() {
  try {
    state.data = await readData("recipes.json");
    state.scores = await readData("scores.json").catch(() => null);
    const available = state.data.models.filter(m => m.recipes.length);
    if (!available.length || !state.data.profiles.length) throw new Error("No data");
    const params = new URL(location.href).searchParams;
    state.model = available.some(m => m.id === params.get("m")) ? params.get("m") : available[0].id;
    state.profile = state.data.profiles.some(p => p.id === params.get("p")) ? params.get("p") : state.data.profiles[0].id;
    state.round = params.get("r") || "r1";
    state.unit = state.data.unit_ml;
    $("unit-ml").value = state.unit;
    $("hero-stats").replaceChildren(...[`${available.length} โมเดล`, `${state.data.profiles.length} สูตร`, `${state.data.ingredients.length} วัตถุดิบ`].map(text => node("span", "", text)));
    $("workspace").hidden = false;
    render();
  } catch {
    $("load-error").hidden = false;
    $("load-error").textContent = "เปิดสมุดสูตรไม่สำเร็จ ลองโหลดหน้าใหม่อีกครั้ง หากเปิดจากไฟล์โดยตรง ให้เปิดเว็บผ่าน HTTP server หรือ GitHub Pages";
    $("hero-stats").replaceChildren(node("span", "", "รอเปิดสมุดสูตร"));
  }
}
$("model-select").addEventListener("change", event => {state.model = event.target.value; state.round = "r1"; render();});
$("round-select").addEventListener("change", event => {state.round = event.target.value; renderRecipe(); updateURL();});
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
  if (toggle.checked && !state.reveal) {
    toggle.disabled = true;
    try {
      const reveal = await readData("reveal.json");
      if (reveal.dataset_id !== state.data.dataset_id) throw new Error("Stale mapping");
      state.reveal = reveal;
    } catch {
      toggle.checked = false;
      $("reveal-error").textContent = "เปิดชื่อไม่สำเร็จ ลองอีกครั้งได้เลย";
      $("reveal-error").hidden = false;
    } finally {toggle.disabled = false;}
  }
  renderModels(); renderRecipe();
});
init();
