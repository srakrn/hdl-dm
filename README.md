# Haidilao Decision Models Benchmark 🥢

ให้ decision models ออกแบบน้ำจิ้มสำหรับจิ้มอาหารที่ลวกใน **น้ำเปล่า** ของ Haidilao ตามความชอบผู้กินชาวไทย ผ่าน **OpenRouter Decisions API** โดยใช้ Noul คัดวัตถุดิบ และ Choice เลือกปริมาณที่ตัก บีบ หรือเขย่าได้จริง รวม 26 วัตถุดิบ (เพิ่มน้ำตาล)

โปรเจกต์นี้ใช้ Python 3.10+ และ standard library เท่านั้น ไม่ต้องติดตั้งแพ็กเกจเพิ่ม

## สูตรสำหรับปรุงจริง: ช้อนใหญ่ 25 mL

ใช้โหมด `practical` เป็นค่าเริ่มต้น (`--method practical`) สำหรับสูตรใหม่ กติกาอยู่ใน [`config/preparation.json`](config/preparation.json):

| อุปกรณ์ | วัตถุดิบ | ตัวเลือกปริมาณ |
|---|---|---|
| ช้อนใหญ่ ≈ 25 mL | วัตถุดิบทั่วไป | ไม่ใส่ / ⅛ / ¼ / ½ / 1 / 2 ช้อน |
| ขวดบีบ | น้ำปลา, เต้าหู้ยี้ | บีบโดยกะปริมาตรเทียบ ไม่ใส่ / ⅛ / ¼ / ½ / 1 / 2 ช้อนใหญ่ |
| Shaker | เกลือ, น้ำตาล, พริกไทยเสฉวน | ไม่ใส่ / เขย่าเบา ๆ 1 / 2 ครั้ง |
| ที่คีบ | ผักชี, ผักชีซอย, ต้นหอมซอย | กะปริมาตรหลวม ๆ เทียบเศษส่วนช้อนใหญ่ |

ขั้นต่ำของช้อน/ที่คีบคือ **⅛ ช้อน ≈ 3.125 mL** ขวดบีบกะปริมาตรเทียบช้อนใหญ่ ไม่ใช้จำนวนครั้งที่บีบ ส่วน shaker ไม่ติดขั้นต่ำนี้ ปริมาตรต่อการเขย่ายังไม่ได้วัด จึงบันทึก `volume_ml = null` สำหรับเครื่องปรุงที่ใช้ ไม่ตั้ง mL ต่อครั้งขึ้นเอง

ขั้นแรกถาม Noul ครบทุกวัตถุดิบ ตัดรายการที่โปรไฟล์ห้ามใช้และรายการต่ำกว่า `selection_threshold` (ปัจจุบัน 0.7) **ไม่จำกัดจำนวนวัตถุดิบ** เพื่อคงความซับซ้อนของสูตร เรียงค่าสูงก่อน โดย tie ใช้ English ID ขั้นที่สองถาม Choice **ทีละวัตถุดิบ** โดยส่งรายการที่เลือกและปริมาณที่เลือกไปแล้วกลับเข้า state โมเดลยังเลือกไม่ใส่ได้ ใช้ผล `choice` โดยตรง ไม่เฉลี่ย probabilities เป็นปริมาณ

ไม่มีเพดานจำนวนช้อนรวมที่ตัดวัตถุดิบออกเมื่อถ้วยเต็ม ให้โมเดลคำนึงถึงสัดส่วนทั้งสูตรและเลือกลดปริมาณหรือละเว้นเอง ปริมาณยังเป็นตัวเลือกที่ตักได้จริง ส่วนรายการที่ Noul ต่ำกว่าเกณฑ์หรือโปรไฟล์ห้ามใช้ถูกกรองก่อนขั้นเลือกปริมาณ

```bash
# ตรวจ prompt โดยไม่เรียก API
python3 scripts/benchmark.py --method practical --jev-only --repeats 1 --dry-run

# ทดสอบ Jev ทั้งสามสูตรหนึ่งรอบ
python3 scripts/benchmark.py --method practical --jev-only --repeats 1

# รันทุกโมเดลตาม config แล้ว refresh หน้าเว็บ
python3 scripts/benchmark.py --method practical --repeats 3 --workers 3
python3 scripts/refresh_site.py
```

แต่ละสูตรใช้ 1–27 API calls ก่อน retries ตาม 26 วัตถุดิบ: หนึ่งครั้งคัดวัตถุดิบ แล้วหนึ่งครั้งต่อวัตถุดิบที่ผ่านการคัดเลือก `--workers` รันสูตรอิสระพร้อมกัน แต่ขั้นเลือกปริมาณภายในสูตรยังเรียงทีละขั้น `requests_planned` ใน manifest นับ **สูตรที่วางแผน** ผลดิบเก็บ request/response ทุกขั้นใน `stages`, Noul ดิบใน `noul`, และปริมาณสำหรับชิมใน `servings` ถ้าเลือกไม่ใส่ทุกอย่างจะเป็น `empty_recipe` และไม่แสดงบนเว็บ ตรวจรายการที่ถูกตัดได้จาก `noul`, `selected_ingredients` และ `servings`

หน้าเว็บแสดงสูตรแต่ละรอบจริงเป็นรายการติ๊กว่าตักแล้ว ไม่มีสูตรเฉลี่ยสำหรับโหมดนี้ ซ่อนของที่ไม่ใส่เริ่มต้น และแสดง “ตัก ⅛ ช้อนใหญ่”, “บีบประมาณ ⅛ ช้อนใหญ่”, “เขย่าเบา ๆ 1 ครั้ง”, “คีบประมาณ ¼ ช้อนใหญ่” รหัส dataset รวมวิธีเตรียมและปริมาณไว้ด้วย จึงไม่ใช้คะแนนสูตรเดิมปนกับสูตรที่เปลี่ยนแล้ว

ผลเดิมยังอ่านได้และแสดงคำอธิบายว่าเป็นผลเดิม **ไม่เปลี่ยนหน่วยเดิม 5 mL เป็น 25 mL อัตโนมัติ** เพราะจะเปลี่ยนสูตร ต้องรันใหม่เพื่อให้โมเดลเลือกปริมาณจริง

## การทดลองเดิม: Noul → ปริมาตร

ส่วนนี้ใช้เฉพาะ `--method noul` เพื่อเทียบกับผลเก่า

[Noul](https://openrouter.ai/docs/guides/community/jev-tutorial) เป็นความน่าจะเป็นของคำตอบ “ใช่” ในช่วง `[0, 1]` โปรเจกต์นี้นำตัวเลขนั้นมาแปลงเป็นปริมาตรตามกติกาการทดลอง:

| Noul | ปริมาตร | เมื่อ 1 หน่วย = 5 mL |
|---|---|---|
| 0 | 0 หน่วย | ไม่ใส่ |
| 0.25 | 0.25 หน่วย | 1.25 mL |
| 0.5 | 0.5 หน่วย | 2.5 mL |
| 1 | 1 หน่วย | 5 mL |

ใช้ค่า Noul โดยตรงเป็นค่าเริ่มต้น **ไม่ normalize ผลรวมเป็น 1** และไม่ปัดเศษก่อนบันทึก กำหนดขนาดหน่วยด้วย `--unit-ml` สำหรับของแข็งให้ตวงปริมาตรด้วยช้อนเดียวกัน ไม่ถือว่าปริมาตรเท่ากันหมายถึงน้ำหนักเท่ากัน

การใช้ probability เป็นปริมาตรเป็นวิธีทดลองของโปรเจกต์นี้: Noul 0.5 หมายถึงโมเดลไม่แน่ใจว่าจะใส่ ไม่ใช่โมเดลยืนยันว่าครึ่งหน่วยคือสัดส่วนอร่อยที่สุด หากต้องการเฉพาะ 0/1 ใช้ `--threshold 0.5` ซึ่งแปลงค่า `>= 0.5` เป็น 1 หน่วย และค่าต่ำกว่านั้นเป็น 0 โดยยังเก็บ Noul ดิบไว้

## วัตถุดิบที่อนุญาต

เกลือ / น้ำตาล / งาขาว / พริกไทยเสฉวน / ซีอิ๊วดำ / ผักชี / ซอสบาร์บีคิวจีน / หมูสับ / พริกบด / น้ำมะนาว / น้ำส้มสายชู / ถั่วลิสงบด / น้ำจิ้มไก่ / น้ำมันงาผสม / กระเทียมบด / พริกป่น / ซอสงา / กระเทียมเจียว / เต้าหู้ยี้ / น้ำปลา / น้ำมันหอย / น้ำมันพริก / ซอสหมาล่า / เต้าซี่ปรุงรส / ซอสเห็ด / กระเทียม / ต้นหอมซอย / ผักชีซอย

คีย์คำถามและผลดิบจาก API เป็น English ID แบบ snake_case ตามตารางด้านล่างทุกตัว ส่วนไฟล์สูตรที่แสดงให้คนอ่าน (`recipes.json` และ `recipes.csv`) ใช้ชื่อวัตถุดิบไทย ชื่อวัตถุดิบ, prompt, preferences และคำอธิบายรสชาติที่ส่ง API เป็นภาษาอังกฤษทั้งหมด ส่วนชื่อไทยเก็บใน config/manifest เพื่อให้ผู้เตรียมสูตรเทียบรายการได้ โดยไม่ส่งชื่อไทยให้โมเดล ตัวตรวจผลจะปฏิเสธคำตอบที่ขาด/เกินวัตถุดิบ ผิดชนิด หรือ Noul อยู่นอกช่วง รวมถึง `true`/`false`, string และค่าที่ไม่ใช่ตัวเลข finite หมูสับในบริบทการทดลองหมายถึงหมูสับปรุงสุกพร้อมกิน

## English ingredient descriptions (draft for review)

แก้ชื่อและคำอธิบายภาษาอังกฤษได้ใน [`config/ingredients.json`](config/ingredients.json) สคริปต์ใช้ไฟล์นี้สร้าง payload โดยตรงและบันทึก catalog ใน manifest ของแต่ละรัน คำอธิบายด้านล่างเป็น draft ของรส กลิ่น และเนื้อสัมผัส ไม่ใช่ข้อมูลสูตรหรือส่วนประกอบจากผู้ผลิต ซอสบาร์บีคิวจีนยืนยันว่าเป็นซอสซาฉา น้ำจิ้มไก่มีน้ำตาลข้นช่วยเพิ่มความข้น และซอสเห็ดเป็นเห็ดหอมสับละเอียดในน้ำมัน รสเค็ม กลิ่นเห็ดหอมชัด ส่วนรายละเอียดอื่นที่ยังไม่ได้ยืนยันควรตรวจให้ตรงกับของจริงที่บาร์น้ำจิ้ม

| English ID | English name | ชื่อไทยสำหรับ output | Flavor and texture (English) |
|---|---|---|---|
| `salt` | Salt | เกลือ | Clean, direct saltiness with no sweetness, acidity, heat, or aroma. Intensifies savory flavors but can easily make the dip too salty. |
| `sugar` | Sugar | น้ำตาล | Clean sweetness; dissolving fine grains soften acidity and balance saltiness. Too much makes the dip cloying. |
| `white_sesame_seeds` | White sesame seeds | งาขาว | Mildly nutty with a delicate seed crunch. Toasting increases the roasted aroma; unroasted seeds are gentler. |
| `sichuan_pepper` | Sichuan pepper | พริกไทยเสฉวน | Citrusy, floral aroma and a distinctive tingling, numbing sensation. The numbing effect differs from chili heat. |
| `dark_soy_sauce` | Homemade soy sauce | ซีอิ๊วดำ | For this station, homemade soy sauce means dark soy sauce: deep soy savoriness, dark color, and a rounded, sometimes molasses-like sweetness. Saltiness and sweetness vary with the recipe. |
| `cilantro` | Cilantro | ผักชี | Fresh, leafy, citrusy herbal aroma. Some diners perceive it as soapy. Here this means larger leaf pieces, distinct from the finely chopped option. |
| `chinese_barbecue_sauce` | Barbecue sauce | ซอสบาร์บีคิวจีน | Shacha sauce (Chinese barbecue sauce): savory, roasted, oily, and aromatic, with deep umami and seafood notes. This condiment is confirmed to be shacha, rather than a sweet barbecue sauce. |
| `cooked_minced_pork` | Minced pork | หมูสับ | Meaty savoriness, mild pork sweetness, soft small pieces, and some richness from fat. Assumed fully cooked and only lightly seasoned. |
| `crushed_chili` | Ground chili | พริกบด | Bright chili heat with fresh, grassy pepper notes and a moist texture. Assumed fresh crushed chili without added salt or vinegar. |
| `lime_juice` | Lime juice | น้ำมะนาว | Sharp, fresh sourness with a citrus aroma. Adds brightness and cuts through oily or rich ingredients. |
| `vinegar` | Vinegar | น้ำส้มสายชู | Direct sourness with an acetic aroma, less fresh citrus fragrance than lime. Assumed plain vinegar; rice or dark vinegar would add different notes. |
| `crushed_peanuts` | Crushed peanuts | ถั่วลิสงบด | Roasted nuttiness, mild natural sweetness, and a coarse crunch. Adds body and richness; assumed roasted and unsalted. |
| `sweet_chili_sauce` | Thai chicken sauce | น้ำจิ้มไก่ | Sweet first, then gently tangy and mildly spicy, with garlic notes. Its thick, concentrated sugar syrup adds sweetness, gloss, viscosity, and body, thickening the dip. |
| `sesame_oil_blend` | Sesame oil blend | น้ำมันงาผสม | Nutty sesame aroma and a smooth, oily mouthfeel. Assumed a toasted sesame oil blend; aroma strength depends on the blend. |
| `crushed_garlic` | Crushed garlic | กระเทียมบด | Strong raw garlic pungency, sharp sulfurous aroma, and a fine moist texture that spreads through the dip. |
| `chili_powder` | Chilli powder | พริกป่น | Dry chili heat with earthy, sometimes roasted notes and a fine, slightly gritty texture. Assumed ground dried chili without a seasoning blend. |
| `sesame_sauce` | Sesame sauce | ซอสงา | Rich roasted sesame nuttiness, thick creamy body, and a slight bitter edge. Assumed sesame-paste-based sauce; added salt or sugar varies. |
| `fried_garlic` | Fried garlic | กระเทียมเจียว | Toasty, mellow garlic aroma, light sweetness, and crisp texture. Less raw pungency than fresh garlic; may carry some frying oil. |
| `fermented_bean_curd` | Fermented bean curd | เต้าหู้ยี้ | Concentrated saltiness, fermented funk, deep savoriness, and a soft creamy texture. Red and white varieties may differ in sweetness and aroma. |
| `fish_sauce` | Fish sauce | น้ำปลา | Intense saltiness and fermented fish umami with a distinctive aroma. Small amounts add savory depth familiar in many Thai dips. |
| `oyster_sauce` | Oyster sauce | น้ำมันหอย | Rounded savory umami, moderate saltiness, some sweetness, and a thick glossy texture. Oyster intensity varies by brand. |
| `chili_oil` | Chili oil | น้ำมันพริก | Chili heat in an oily base, often with toasted chili aroma. Adds richness; assumed no pronounced Sichuan-pepper numbness unless specified. |
| `mala_sauce` | Mala oil sauce | ซอสหมาล่า | Chili heat plus Sichuan-pepper tingling and numbness in an oily sauce, with savory spices. Adds both richness and a numbing sensation; intensity depends on the sauce. |
| `lao_gan_ma` | Flavoured bean sauce | เต้าซี่ปรุงรส | A Lao Gan Ma-style seasoned fermented black bean condiment: salty, deeply savory umami, fermented bean aroma, and soft bean pieces. Oil, chili heat, and roasted aromatics depend on the variety; do not assume it is the chili-crisp variant. |
| `mushroom_sauce` | Shiitake sauce | ซอสเห็ด | Finely minced shiitake mushrooms in oil: distinctly salty and savory, with a pronounced shiitake aroma, small mushroom pieces, and an oily texture. Adds mushroom umami and richness rather than a smooth creamy body. |
| `garlic` | Garlic | กระเทียม | Raw garlic pungency and a sharp sulfurous aroma with a firm bite. Here this means small fresh garlic pieces, distinct from crushed garlic and fried garlic. |
| `chopped_scallions` | Minced shallots | ต้นหอมซอย | The station label Minced shallots refers to chopped scallions (green onions), not bulb shallots. Fresh green onion aroma, gentle onion pungency, a little sweetness, and a light crisp bite. |
| `chopped_cilantro` | Parsley | ผักชีซอย | The station label Parsley refers to finely chopped cilantro (coriander), not European parsley. Fresh, citrusy, leafy herbal aroma distributed through the dip by fine chopping; some diners perceive cilantro as soapy. |

คง `cilantro` (ใบ/ชิ้นใหญ่) และเพิ่ม `chopped_cilantro` (ซอยละเอียด) ตามคำขอ เช่นเดียวกับ `garlic` (กระเทียมสดเป็นชิ้น), `crushed_garlic` (บด) และ `fried_garlic` (เจียว) ทั้งหมดเป็นคำถามแยก และ prompt เตือนให้หลีกเลี่ยงการใส่ซ้ำโดยไม่จำเป็น โปรไฟล์ `thai_no_vegetables` exclude ผักชีทั้งสองรูปแบบและต้นหอมซอย

ชื่อบนป้ายใช้ตามที่ยืนยัน: `Parsley` → ผักชีซอย (cilantro/coriander), `Minced shallots` → ต้นหอมซอย (scallions), `Homemade soy sauce` → ซีอิ๊วดำ และ `Flavoured bean sauce` → เต้าซี่ปรุงรส คำอธิบายอังกฤษระบุความหมายของชื่อบนป้ายไว้เพื่อไม่ให้โมเดลตีความเป็น parsley ฝรั่งหรือหอมแดง ส่วน `Fermented bean curd` คือเต้าหู้ยี้ ตัดซอสเต้าหู้นิ่มออกแล้ว ชื่อ `Parsley` ที่ซ้ำในรายการนับเป็นผักชีซอยตัวเดียว และแก้คำสะกด `sause` / `gound` เป็น `sauce` / `ground`

## English prompt and True/False criteria

แต่ละคำถามมี `instructions` ภาษาอังกฤษพร้อมคำอธิบายรสชาติของวัตถุดิบนั้น และมี `criteria.true` / `criteria.false` เสมอ โดยข้อความขึ้นต้นด้วย **True when** / **False when** ตามนี้:

```json
{
  "lime_juice": {
    "type": "noul",
    "instructions": "Should Lime juice be included in this dipping sauce for food cooked in plain water? Consider the diner's preferences, exclusions, and the full ingredient list. Flavor and texture: Sharp, fresh sourness with a citrus aroma. Adds brightness and cuts through oily or rich ingredients.",
    "criteria": {
      "true": "True when Lime juice contributes a desirable flavor or texture for this diner's profile, complements the unseasoned food, and is not excluded. Its contribution is useful without an unnecessary duplicate of another condiment.",
      "false": "False when Lime juice is excluded, conflicts with the diner's preferences, adds unnecessary duplicate seasoning, or makes the dip too salty, sour, sweet, spicy, numbing, oily, or overpowering for the food."
    }
  }
}
```

ใช้ฟิลด์ตาม [OpenRouter Decisions API](https://openrouter.ai/docs/api/api-reference/alphadecisions/submit-a-decisions-request) ไม่เพิ่มฟิลด์ `true_when` / `false_when` ที่ไม่ได้อยู่ใน contract

## โมเดล

ตรวจจาก [OpenRouter Decision Model Rankings](https://openrouter.ai/rankings/decisions) วันที่ **10 ตุลาคม 2026** ในช่วง **This Week** และขยาย **Show more** แล้ว พบ 19 โมเดล (ข้อมูลการใช้งานถึง 9 ตุลาคม 2026):

| Model ID |
|---|
| `typesafe/jev-1.13` |
| `openai/gpt-6-luna-decisions` |
| `cloudflare/clef-flash` |
| `cloudflare/clef` |
| `perplexity/pplx-decider-v1.1-27b` |
| `liquid/d1` |
| `inception/mercury-decide:free` |
| `jaredpalmer/kev-4b` |
| `perplexity/pplx-decider-v1-27b` |
| `upstage/solar-decide` |
| `respan/span-01` |
| `togethercomputer/tev1-4b-experimental` |
| `upstage/solar-decide-flash` |
| `respan/span-01-lite` |
| `inception/mercury-decide` |
| `microsoft/microsoft-decision-1` |
| `nace-ai/drex-v1.5` |
| `respan/span-01-lite:free` |
| `cloudflare/clef-omni` |

รายชื่ออยู่ใน [`config/models.json`](config/models.json) เป็น snapshot ที่แก้ไขได้ ไม่ได้ดึงใหม่อัตโนมัติทุกครั้ง รายการนี้ครอบคลุม leaderboard ที่ตรวจวันดังกล่าว ไม่ได้หมายถึงทุกรุ่นย้อนหลังของ Jev หรือทุกรุ่นใน catalog อันดับหน้าเว็บวัดปริมาณใช้งาน ไม่ใช่คะแนนรสชาติ การมี model ID บนหน้าเว็บยังไม่รับประกันว่าทุกโมเดลจะเรียกได้ด้วยบัญชีของคุณในวันรัน; สคริปต์จะบันทึกข้อผิดพลาดและทดสอบตัวถัดไป

ที่มารายการและอันดับ: OpenRouter, [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/); ไม่ได้แก้ไขข้อมูลอันดับ แต่ดึงเฉพาะรายชื่อและ model ID สำหรับ config

## เริ่มใช้งาน

ตรวจ payload แบบไม่เรียก API และไม่ต้องมี key:

```bash
python3 scripts/benchmark.py --dry-run --out results/preview
```

สร้าง [OpenRouter API key](https://openrouter.ai/settings/keys) แล้วกรอกใน `.env` ที่ root ของโปรเจกต์ สคริปต์อ่านไฟล์นี้อัตโนมัติ และ `.gitignore` กันไฟล์นี้ออกจาก Git:

```dotenv
OPENROUTER_API_KEY=your-openrouter-api-key
```

ถ้ายังไม่มี `.env` ให้คัดลอกจาก `.env.example` ได้ หรือ export ใน shell แทน (ค่าจาก shell มีลำดับความสำคัญสูงกว่า `.env`):

```bash
export OPENROUTER_API_KEY='your-openrouter-api-key'
```

เริ่มทดลอง Jev เพียง 1 คำขอ:

```bash
python3 scripts/benchmark.py --jev-only --profile thai_spicy --repeats 1
```

ทดสอบครบ 19 โมเดล × 3 โปรไฟล์ × 3 รอบ = **171 สูตร** โหมด practical ใช้ไม่เกิน 4,959 API calls ก่อน retry ขึ้นกับจำนวนวัตถุดิบที่ผ่านการคัดเลือก:

```bash
python3 scripts/benchmark.py --out results/all-models
```

การรันจริงใช้เครดิต OpenRouter ตามโมเดลและจำนวน retry ตรวจราคาปัจจุบันที่หน้าโมเดล สคริปต์ไม่สมมติราคาคงที่

เลือกโมเดล/โปรไฟล์เอง หรือปรับปริมาตรและโหมด 0/1:

```bash
python3 scripts/benchmark.py --models typesafe/jev-1.13 cloudflare/clef --repeats 2
python3 scripts/benchmark.py --method noul --jev-only --profile thai_spicy thai_mild --unit-ml 2.5
python3 scripts/benchmark.py --method noul --jev-only --threshold 0.5 --out results/binary
```

`--out` ต้องเป็นโฟลเดอร์ใหม่เพื่อป้องกันการเขียนทับผลเดิม ถ้าไม่ระบุจะสร้างโฟลเดอร์ชื่อเวลารัน UTC ใต้ `results/` ใช้ `python3 scripts/benchmark.py --help` ดูตัวเลือกทั้งหมด

## บริบทและโปรไฟล์ไทย

[`config/profiles.json`](config/profiles.json) มี 3 โปรไฟล์ที่ตั้งขึ้นเพื่อทดสอบ:

- `thai_spicy`: เผ็ดได้ — รสไทยเปรี้ยว เค็มอูมามิ หวานนิด เลือกใช้ความเผ็ดได้
- `thai_mild`: ไม่เผ็ด — ไม่ใส่พริกหรือเครื่องปรุงที่ทำให้เผ็ด/ชาลิ้น รวมถึงน้ำจิ้มไก่ที่มีพริก
- `thai_no_vegetables`: ไม่ใส่ผัก — ไม่ใส่ผักชีและต้นหอมทุกแบบ แต่ยังใช้กระเทียม พริก เห็ด และซอสได้ตามนิยามการทดลองนี้


อาหารลวกในน้ำเปล่าที่ไม่เติมเกลือ น้ำสต๊อก หรือฐานซุป ให้น้ำจิ้มเป็นตัวปรุงรสหลักโดยยังรับรู้รสของอาหาร โปรไฟล์เหล่านี้ไม่ได้แทนความชอบคนไทยทั้งหมด

ทุกโมเดลได้รับ state และคำถามชุดเดียวกัน สุ่มลำดับงานด้วย `--seed 42` เพื่อลดการผูกโมเดลกับเวลารัน แต่ seed นี้ไม่ได้ควบคุมการสุ่มภายในโมเดล รันคำขอทีละงานเพื่อให้อ่าน latency ได้ง่าย ไม่ส่ง temperature หรือพารามิเตอร์ chat ที่ไม่อยู่ใน Decisions contract

คำถาม Noul ตอบแยกกันและไม่เห็นคำตอบกัน จึงไม่ได้รับประกันว่าสูตรรวมจะสมดุล โปรไฟล์ระบุวัตถุดิบที่ไม่ต้องการใน `excluded`; สคริปต์เก็บค่าที่โมเดลคืนจริงโดยไม่บังคับเป็นศูนย์ แล้ววัด `excluded_volume_units` เพื่อเห็นการทำตามข้อกำหนด สำหรับการชิมโปรไฟล์ที่ไม่ใส่วัตถุดิบบางอย่าง เลือกสูตรที่ตรงข้อกำหนดหรือบันทึกการแก้สูตรแยกจากผลดิบ

## ผลที่บันทึก

| ไฟล์ | เนื้อหา |
|---|---|
| `manifest.json` | config, catalog รสชาติ, prompt version, โปรไฟล์, หน่วย, threshold, seed, timeout, retry และจำนวนงาน |
| `results.jsonl` | หนึ่งแถวต่อคำขอ: payload, hash, response ดิบ, model/provider ที่ตอบจริง, usage, latency, สูตร และ error |
| `recipes.json` | สูตรที่ใช้ชื่อวัตถุดิบไทยในคีย์ Noul/หน่วย/mL; แปลงชื่อหลังได้รับผลจาก API |
| `recipes.csv` | หนึ่งแถวต่อวัตถุดิบต่อสูตร: ชื่อไทย, Noul, หน่วย, mL และสถานะ excluded; UTF-8 BOM เปิดใน Excel ได้ |
| `summary.json` | ความสำเร็จ, median/p95 latency, ค่าใช้จ่ายที่ทราบ, ความสม่ำเสมอ และปริมาตรวัตถุดิบที่ไม่ต้องการ |
| `tasting.csv` | แบบฟอร์มคะแนนชิมที่ใช้รหัสตัวอย่างโดยไม่แสดงชื่อโมเดล |

ตัวอย่างรูปแบบเฉพาะส่วนสูตร (เป็นค่าตัวอย่าง ไม่ใช่ผล benchmark):

```json
{
  "noul": {"น้ำมะนาว": 0.8, "น้ำปลา": 0.6},
  "volume_units": {"น้ำมะนาว": 0.8, "น้ำปลา": 0.6},
  "volume_ml": {"น้ำมะนาว": 4.0, "น้ำปลา": 3.0}
}
```

ผลจริงของโหมดเดิมที่รันด้วย catalog ปัจจุบันต้องมีครบ 26 วัตถุดิบ รวมค่าศูนย์ API คืน `answers[English ingredient ID] = {"type": "noul", "noul": ...}` แล้วสคริปต์เก็บผลดิบด้วย English ID ใน `results.jsonl` และแปลงเป็นชื่อไทยเฉพาะไฟล์สูตรข้างต้น

`valid_rate` วัดรูปแบบคำตอบ ไม่ใช่ความอร่อย `mean_noul_stddev` คือค่าเฉลี่ยส่วนเบี่ยงเบนมาตรฐานประชากรของ Noul แต่ละวัตถุดิบข้ามรอบในโปรไฟล์เดียวกัน (ต่ำ = สม่ำเสมอ; `null` เมื่อไม่มีรอบซ้ำที่สำเร็จ) ไม่ถือว่าความสม่ำเสมอแปลว่าถูกต้อง `excluded_volume_units` เป็นผลรวมทุกงานที่สำเร็จ จึงควรดูร่วมกับจำนวนงานที่สำเร็จ

Latency รวม network และ retry/backoff ของงานนั้น รวมงานล้มเหลวด้วย ไม่ใช่เวลาคำนวณโมเดลล้วน p95 ใช้ nearest rank; จำนวนตัวอย่างน้อยทำให้สถิติยังไม่นิ่ง ค่าใช้จ่ายรวมเฉพาะ `usage.cost` ที่ API คืน พร้อม `cost_known_requests`; `null` หมายถึงไม่มีข้อมูล ไม่ใช่ฟรี ค่า retry ที่ล้มเหลวและอาจถูกคิดเงินไม่รวมอยู่ในยอดนี้

## วัดว่าอร่อยจริง

ให้ผู้เตรียมสูตรใช้ `recipes.csv` แล้วติดรหัส `sample_id` บนถ้วย ผู้ชิมใช้ `tasting.csv` และไม่เห็นไฟล์จับคู่ชื่อโมเดล ใช้หน่วยตวงเดียวกัน อาหารชนิดเดียวกันที่ลวกในน้ำเปล่าด้วยวิธีเดียวกัน และสุ่มลำดับชิม ควรมีหลายคนชิมทุกโมเดลในโปรไฟล์ที่ตรงกับความชอบของตน

กรอก `taster_id` และคะแนน 1–5 ทั้งสามช่อง: ความชอบรวม (`overall`), ความเข้ากันกับอาหารลวกน้ำเปล่า (`food_pairing`), สมดุลรส (`balance`) โดย 1 = ไม่ชอบเลย และ 5 = ชอบมาก เพิ่มแถวได้หากหลายคนชิมตัวอย่างเดียวกัน ห้ามรหัสผู้ชิมเดียวกันให้คะแนน sample เดิมซ้ำ

รวมคะแนนเข้าผลสรุป:

```bash
python3 scripts/summarize.py results/all-models --ratings results/all-models/tasting.csv
```

สคริปต์เพิ่ม `human_tasting` ให้แต่ละโมเดล (ค่าเฉลี่ยต่อแถวคะแนนและจำนวนตัวอย่างที่ชิม); โมเดลที่ยังไม่ชิมเป็น `null` คะแนนนี้เป็นผลของกลุ่มผู้ชิมและชุดสูตรที่ชิมเท่านั้น ต้องใช้จำนวนผู้ชิม/โปรไฟล์ใกล้เคียงกันก่อนเทียบโมเดล ไม่มีสูตร gold ที่อ้างว่าเป็นสูตรถูกปากคนไทยทุกคน

สร้างสรุปใหม่จาก JSONL ที่บันทึกแล้ว รวมถึงเมื่อหยุดรันกลางทาง:

```bash
python3 scripts/summarize.py results/all-models
```

คำสั่งนี้เขียน `summary.json` ใหม่ ถ้าต้องการคงคะแนนชิมไว้ให้ส่ง `--ratings` ทุกครั้ง ผลใหม่ใช้ prompt version `5-three-requested-recipes` และช่อง `food_pairing_1_to_5`; สรุปผลเก่าที่มี 25 วัตถุดิบและคะแนน `broth_pairing_1_to_5` ยังอ่านได้ แต่บริบทและชุดวัตถุดิบต่างกันจึงไม่ควรรวมกับรันใหม่เพื่อเทียบโมเดล

## ข้อผิดพลาดและทดสอบ

ค่าเริ่มต้น timeout 60 วินาที และ retry สูงสุด 2 ครั้งเฉพาะ HTTP 429/500/502/503/504/524/529 ใช้ backoff และเคารพ `Retry-After` ที่เป็นจำนวนวินาทีไม่เกิน 60 วินาที ไม่ retry timeout ที่ไม่ทราบว่าฝั่งเซิร์ฟเวอร์รับงานแล้วหรือไม่เพื่อเลี่ยงการส่งซ้ำ งานที่ล้มเหลวไม่ทำให้หยุดทดสอบโมเดลถัดไป; exit code เป็น 1 หากมี API error หรือคำตอบผิดรูปแบบ ผล JSONL flush หลังทุกงาน ไม่บันทึก API key

ทดสอบ offline โดยจำลอง API รวมกรณี schema ผิด, authentication, retry, สูตร/CSV, ต้นทุนที่ไม่ทราบ และคะแนนชิม:

```bash
python3 -m unittest discover -s tests -v
```

Dry run และ unit tests ไม่ใช้เครดิตและไม่ได้ยืนยันว่าโมเดลทั้งหมดเรียกสำเร็จจริง ต้องมี API key และรัน live เพื่อยืนยันการเชื่อมต่อของบัญชีนั้น

## เอกสารอ้างอิง

- [OpenRouter Decisions API request/response](https://openrouter.ai/docs/api/api-reference/alphadecisions/submit-a-decisions-request)
- [Jev และ Noul/Choice/Score](https://openrouter.ai/docs/guides/community/jev)
- [ตัวอย่าง HTTP และรูปแบบ Noul response](https://openrouter.ai/docs/guides/community/jev-tutorial)
- [Decision Model Rankings](https://openrouter.ai/rankings/decisions)

## เว็บรีวิว: Haidilao x Decisions Model

ไฟล์เว็บอยู่ใน [`web/`](web/) เป็น HTML/CSS/JavaScript แบบ static พร้อมข้อมูลจากรัน benchmark ที่สำเร็จล่าสุด ไม่ต้องมี Node, build step หรือ API key บนเว็บ

- เลือกโมเดลด้วยชื่อเล่นสุ่มที่ไม่มีชื่อค่ายหรือรุ่นเป็นคำใบ้
- เลือกสูตรเผ็ดได้ / ไม่เผ็ด / ไม่ใส่ผัก
- ดูสูตรเฉลี่ยของรอบที่สำเร็จ หรือเลือกรอบที่ 1–3 แยกกันได้
- เปิด/ซ่อนชื่อโมเดลจริงได้ ค่าเริ่มต้นซ่อนชื่อทุกครั้งที่เปิดหน้า
- ดูปริมาตรหน่วย/mL เปลี่ยนขนาดหนึ่งหน่วย และแชร์ลิงก์สูตรได้
- Dropdown แสดงเฉพาะโมเดลที่มีสูตรสำเร็จ โมเดลที่ไม่มีสูตรจะไม่ปรากฏ
- มีช่องคะแนน LLM baseline และคนชิมแยกกัน ยังไม่มีคะแนนในขั้นนี้

ชื่อเล่นสุ่มด้วย `secrets` ไม่ได้คำนวณจากชื่อโมเดลหรืออันดับ และเก็บ mapping ใน `.local/blind-map.json` เพื่อคงชื่อเมื่อ refresh ถ้าเป็น checkout ใหม่ที่ไม่มี `.local/` สคริปต์กู้ mapping จาก `web/data/recipes.json` และ `reveal.json` ได้ ปุ่มเปิดเผยชื่อใช้ `reveal.json` ที่เป็นไฟล์สาธารณะ: blind review นี้คือการซ่อนชื่อจากหน้าเริ่มต้น ไม่ได้ป้องกันผู้ใช้ที่ตั้งใจเปิดไฟล์ข้อมูลเพื่อดูชื่อ

เปิดดูในเครื่อง:

```bash
python3 -m http.server 8765 --bind 127.0.0.1 --directory web
```

แล้วเปิด `http://127.0.0.1:8765` ต้องเปิดผ่าน HTTP เพื่อโหลด JSON ห้ามเปิด `index.html` แบบ `file://`

### GitHub Actions และ Pages

มีสอง Actions:

| Action | เริ่มเมื่อ | ทำอะไร |
|---|---|---|
| **Regenerate Recipes** | กด Run workflow บน `main` | เรียก OpenRouter สร้างสูตร practical ทุกโมเดล/สามโปรไฟล์ ให้กรรมการ AI วิจารณ์ แล้ว commit และ push เฉพาะ `web/data/` |
| **Refresh Site** | ทุก push เข้า `main`, หลัง Regenerate Recipes สำเร็จ หรือกด Run workflow | ดึง CSV รีวิวล่าสุด คำนวณคะแนน และ build เว็บเป็น artifact `review-site` โดยไม่เรียกโมเดล |

ตั้ง repository secret **`OPENROUTER_API_KEY`** ที่ **Settings → Secrets and variables → Actions** ก่อนกด Regenerate Recipes ค่าเริ่มต้นคือหนึ่งรอบต่อโมเดล/โปรไฟล์และสามงานพร้อมกัน ปรับ `repeats` ได้ 1–5 และ `workers` ได้ 1–8 การสร้างสูตรใช้เครดิตจริง ไม่รันอัตโนมัติตอน push

Regenerate Recipes ยอมรับรันที่ครบทุกงานและมีสูตรสำเร็จอย่างน้อยหนึ่งสูตร แม้บางโมเดลจะ error; แสดง warning และเก็บผลดิบเป็น artifact `benchmark-results` เจ็ดวัน รันที่ไม่ครบหรือไม่มีสูตรสำเร็จจะไม่แทนสูตรเดิม ไม่ commit `.env`, `.local/` หรือ `results/` และไม่ force push หาก `main` เปลี่ยนระหว่างรัน push จะ fail เพื่อไม่เขียนทับงานใหม่

Refresh Site ใช้สูตรสาธารณะที่ commit ไว้ จึงทำงานใน fresh checkout ได้โดยไม่ต้องมี `results/` และเก็บเว็บที่ build แล้ว 14 วัน การ push โดย `GITHUB_TOKEN` ไม่ทำให้เกิด push workflow อีกรอบ จึงใช้ `workflow_run` ต่อจาก Regenerate Recipes ตาม [GitHub workflow triggers](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow)

ค่าเริ่มต้น **build อัตโนมัติ แต่ publish เอง**:

1. ตั้ง **Settings → Pages → Build and deployment → Source → GitHub Actions**
2. ไป **Actions → Refresh Site → Run workflow** เลือก `main` และติ๊ก `publish`
3. เปิด URL จาก deployment ที่สำเร็จ ปกติคือ `https://srakrn.github.io/hdl-dm/`

หากต้องการ publish ทุกครั้งที่ Refresh Site ทำงาน ตั้ง repository variable **`PAGES_AUTO_DEPLOY`** เป็น `true` เว็บใช้ relative paths รองรับ repository subpath และ deploy เฉพาะ `web/`

### ดึงรีวิวและ build เว็บ

```bash
python3 scripts/build_site.py
```

คำสั่งนี้อัปเดตข้อมูลฟอร์มจาก config และดาวน์โหลด CSV ของ Google Sheet ที่ให้มาใน `review_import.csv_url` ของ [`config/review.json`](config/review.json) โดยไม่ต้อง login ซึ่งตรวจแล้วว่าอ่านได้ หากเปลี่ยนแหล่งข้อมูล ใช้ environment variable / repository secret **`REVIEW_CSV_URL`** แทน URL ใน config; URL ต้องเป็น HTTPS และเปิดอ่าน CSV ได้จาก runner โดยไม่มี Google session ไม่ใช้ URL `viewform` เป็นแหล่งคำตอบ

ฟอร์มปัจจุบันมีคะแนนรวมช่องเดียว **0–10** จึงหารสองเป็น **0–5 ดาว** (`0` คือกินไม่ได้, `2.5` คือเฉย ๆ, `5` คืออร่อยมาก) ไม่สร้างคะแนนความเข้ากันกับอาหาร/สมดุลรสที่ฟอร์มไม่ได้ถาม รหัสชุดสูตรและสูตรอ่านจาก JSON ในช่องที่ฟอร์มกรอกอัตโนมัติ ไม่มีรหัสผู้ชิม จึงนับจำนวน **รีวิว** ไม่อ้างว่าเป็นจำนวนคนที่ไม่ซ้ำ รหัสคำตอบภายในมาจาก hash ของลำดับแถว timestamp และรหัสสูตร (สองรีวิวที่เวลาเดียวกันยังนับแยกกัน)

ชื่อคอลัมน์จริงของ Sheet ถูก map ใน `review_import.columns`, `review_id_column` และ `response_id_column` ตั้งไว้แล้ว หากแก้คำถามในฟอร์มให้แก้ mapping นี้ด้วย รีวิวชุดสูตรเก่าจะถูกข้าม ส่วนรหัสสูตรผิดของชุดปัจจุบัน คะแนนเกินช่วง และรหัสผู้ประเมินซ้ำใน CSV มาตรฐานจะทำให้ build fail เพื่อไม่เผยแพร่คะแนนผิด เมื่อดึง source ใดใหม่จะคำนวณ source นั้นจากข้อมูลทั้งหมดแทนของเดิม; source ที่ไม่ได้ส่งเข้ามาจะคงคะแนนเดิมไว้ การเปลี่ยน weights ต้องมี raw ratings ครบทุก source ที่มีคะแนน

ดึงรีวิวไม่สำเร็จจะหยุด build และไม่ deploy คะแนนเก่าเป็นข้อมูลใหม่ ไม่บันทึกหรือ upload CSV คำตอบส่วนบุคคลลง artifact เว็บ ส่งออกเฉพาะคะแนนรวมและจำนวนรีวิว ส่วน LLM baseline ใช้บทวิจารณ์ที่บันทึกไว้ ไม่เรียกโมเดลซ้ำตอน Refresh

ทดสอบด้วย CSV ในเครื่องหรือเพิ่ม baseline ที่เตรียมไว้แล้ว:

```bash
python3 scripts/build_site.py --reviews-csv .local/form-responses.csv
python3 scripts/build_site.py --ratings .local/llm-ratings.csv
```

### Refresh ข้อมูลเว็บ

หลังรัน benchmark ใหม่:

```bash
python3 scripts/refresh_site.py
```

สคริปต์เลือก **รันล่าสุดที่ครบจำนวนคำขอ** และไม่ใช่ dry run จึงไม่หยิบรันที่ถูกหยุดกลางทางโดยอัตโนมัติ ระบุรันเองได้:

```bash
python3 scripts/refresh_site.py --run-dir results/20261010T062327726884Z
```

อ่าน catalog, ขนาดหน่วย, exclusions และ prompt version จาก manifest ของรันนั้น ไม่อ่านวัตถุดิบ config ปัจจุบันไปปนกับผลเก่า ส่งออก:

| ไฟล์ | ใช้ทำอะไร |
|---|---|
| `web/data/recipes.json` | ชื่อเล่น, สูตรเฉลี่ย/แต่ละรอบ, วัตถุดิบไทย และ `dataset_id` |
| `web/data/reveal.json` | mapping รหัสสุ่ม → ชื่อโมเดลจริง ใช้เมื่อเปิดเผยชื่อ |
| `web/data/scores.json` | คะแนนแยก LLM/human ไม่มีคะแนนจะเป็นข้อมูลว่าง |
| `web/data/ratings-template.csv` | template คะแนนสำหรับ recipe ID ของทุกสูตรเฉลี่ยและแต่ละรอบ |

การ refresh โดยไม่ส่ง `--ratings` จะล้างคะแนนเว็บเป็นว่าง ให้ส่งไฟล์คะแนนเดิมทุกครั้งที่ต้องการคงไว้ หากสูตรหรือ constraints เปลี่ยน `dataset_id` จะเปลี่ยน และสคริปต์ปฏิเสธคะแนนของ dataset เก่าเพื่อไม่ให้คะแนนติดสูตรผิด

### คำนวณคะแนนสำหรับขั้นถัดไป

เชื่อมลิงก์ Google Forms สำหรับให้คะแนนแล้ว คะแนน offline เดิมยังรองรับ CSV รูปแบบนี้ ส่วนกรรมการ AI สี่ด้านใช้ `judge_recipes.py` และ `judgments.json` ตามหัวข้อถัดไป:

```csv
dataset_id,recipe_id,source,judge_id,overall,food_pairing,balance,notes
```

คัดลอก `ratings-template.csv` ไปไฟล์ใหม่ (เช่น `.local/llm-ratings.csv` หรือ `.local/human-ratings.csv`) แล้วกรอก:

- `dataset_id`, `recipe_id`: ใช้ค่าจาก template ห้ามสลับสูตรเฉลี่ยกับสูตรของรอบใดรอบหนึ่ง
- `source`: `llm` หรือ `human`
- `judge_id`: รหัสผู้ประเมิน เช่น `judge-a` / `judge-b` / `judge-c` สำหรับ LLM; ใช้รหัสคนชิมโดยไม่ใส่ชื่อหรืออีเมล
- `overall`, `food_pairing`, `balance`: คะแนน LLM 1–5 ครบทั้งสามช่อง; คะแนน human ใช้ `overall` 0–5 ตามฟอร์มปัจจุบัน (หารสองจาก 0–10 ก่อน) แถวที่คะแนนทั้งสามช่องว่างถือว่ายังไม่มีคะแนน ไม่ถือเป็นศูนย์ หากเริ่มกรอกต้องกรอกครบทั้งสามช่อง

คำนวณจากไฟล์ที่กรอกแล้วโดยไม่เรียกบริการภายนอก:

```bash
python3 scripts/calculate_scores.py --ratings .local/llm-ratings.csv .local/human-ratings.csv
```

หรือ refresh สูตรและคะแนนพร้อมกัน:

```bash
python3 scripts/refresh_site.py --ratings .local/llm-ratings.csv .local/human-ratings.csv
```

สูตรคะแนน LLM เริ่มต้น: `overall × 0.5 + food_pairing × 0.3 + balance × 0.2` แล้วเฉลี่ยคะแนนผู้ประเมินภายใน source เดียวกัน; รีวิวคนชิมปัจจุบันใช้ `overall` ช่องเดียวตาม `rating_contracts.human` **ไม่รวม baseline LLM กับคะแนนคนชิม** ปรับ weights และจำนวน LLM judges ที่คาดหวังได้ใน [`config/review.json`](config/review.json) baseline จะระบุว่ายังไม่ครบหากมีผู้ประเมินน้อยกว่า 3 ตัว แถวซ้ำ `(recipe_id, source, judge_id)`, คะแนนผิดช่วง หรือ dataset เก่าจะถูกปฏิเสธ ไฟล์คะแนนเว็บมีเพียงค่าเฉลี่ยและจำนวนผู้ประเมิน ไม่เผย `judge_id` หรือ notes

Google Forms ที่ผู้ใช้ให้มาเชื่อมแล้วผ่าน `form_fields.review_id = entry.1302023336` ใน `config/review.json` ปุ่ม “ให้คะแนนสูตรนี้” แทนค่า prefill ด้วยสตริง JSON เช่น `{"dataset_id":"…","recipe_id":"176e96f9c165-thai_spicy-average"}` โดย `recipe_id` ระบุ alias โมเดล + สูตร + รอบที่เลือก และ `dataset_id` ระบุชุดข้อมูล ปุ่มเปลี่ยนค่าตามสูตร/รอบที่แสดงเสมอ ชื่อจริงไม่อยู่ในค่าที่ส่ง เพื่อรักษา blind review

เมื่อนำคำตอบกลับมาคำนวณคะแนน ให้ adapter parse JSON ในช่องนี้เพื่อได้ `dataset_id` และ `recipe_id` แล้ว map alias ผ่าน `web/data/reveal.json` เมื่อต้องการชื่อโมเดลจริง ปรับหัวคอลัมน์คะแนนเป็น contract ข้างต้นก่อนเรียก `calculate_scores.py` ยังไม่ได้ส่งคำตอบไปยังฟอร์ม ส่วนการดึงคำตอบอัตโนมัติทำผ่าน `build_site.py` และ Refresh Site แล้ว หากเปลี่ยนฟอร์ม ใส่ `form_url` และ entry ใน config แล้ว refresh; ยังรองรับ `form_fields.dataset_id` / `form_fields.recipe_id` สำหรับฟอร์มที่แยกสองช่อง


### กรรมการ AI สามตัว

```bash
python3 scripts/judge_recipes.py --limit 1   # pilot สูตรแรกด้วยทั้งสามกรรมการ
python3 scripts/judge_recipes.py             # วิจารณ์สูตรที่เหลือ และใช้ผลที่ทำแล้ว
python3 scripts/build_site.py               # รวมบทวิจารณ์/ดาวกับรีวิวคนชิม
```

ใช้ OpenRouter chat completions ผ่าน API key เดิมใน `.env` ไม่ใช้ Decisions endpoint สำหรับข้อความวิจารณ์ [`config/judges.json`](config/judges.json) กำหนดกรรมการ คาแรกเตอร์ และ rubric เดียวกันทั้งสามคน:

- **DeepSeek V4.1 Flash**: ป้าหน้าบาร์ — โมเดลจีนที่เลือกให้สมดุลคุณภาพกับราคา รองรับ structured outputs
- **GPT Sol Latest**: กรรมการถ้วยทอง — อ่าน catalog แล้วเลือก Sol รุ่นปกติล่าสุด ไม่ใช้ Pro, Decisions หรือ batch (รอบนี้ GPT-6.1 Sol)
- **Gemini Flash Latest**: นักสืบน้ำจิ้ม — อ่าน catalog แล้วเลือก Flash รุ่นล่าสุด ไม่ใช้ Lite, Preview, Image หรือ batch (รอบนี้ Gemini 3.8 Flash)

ชื่อรุ่นที่ร้องขอและชื่อรุ่นที่ API ตอบจริงถูกบันทึกไว้ ไม่เปลี่ยนไปใช้คนละโมเดลแบบเงียบ ๆ คาแรกเตอร์ต่างกันเฉพาะลีลาการพูด ใช้เกณฑ์ให้คะแนนเดียวกัน:

| ด้าน | น้ำหนัก | สิ่งที่ประเมิน |
|---|---:|---|
| ความอร่อย (`taste`) | 40% | รสที่คาดว่าจะถูกปากคนไทยในโปรไฟล์นั้น และเข้ากับอาหารลวกน้ำเปล่า |
| ความกลมกล่อม (`balance`) | 30% | สัดส่วนเปรี้ยว เค็ม หวาน เผ็ด มัน โดยไม่มีรสหนึ่งท่วมทั้งหมด |
| ความซับซ้อน (`complexity`) | 15% | ชั้นรสที่มีหน้าที่และเข้ากัน ไม่ใช่นับจำนวนวัตถุดิบ |
| ความแปลกใหม่ (`novelty`) | 15% | ไอเดียใหม่ที่น่าจะใช้ได้จริง ไม่ให้รางวัลการใส่มั่ว |

เกณฑ์ใหม่ตรวจหน้าที่น้ำจิ้มก่อน ให้ 0 ได้จริง ไม่มีคะแนนปลอบใจ: หมูสับปรุงอ่อนอย่างเดียวได้ 0 ทุกด้าน เพราะไม่ใช่น้ำจิ้ม แต่ไม่เหมารวมวัตถุดิบเดียวทั้งหมด (ซอสสำเร็จจริงอาจใช้ได้) ประเมินสูตรเดิมก่อนแก้ ไม่ให้ความรกหรือความแปลกที่ไม่น่ากินชดเชยความอร่อย/สมดุล ตัวอย่างน้ำมะนาวกับน้ำปลาอาจอร่อยแบบเรียบง่ายโดยไม่ต้องมีคะแนนความซับซ้อนสูง

แต่ละด้าน 0–5 ดาว แล้วถัวเฉลี่ยตามน้ำหนักเป็นดาวของกรรมการคนนั้น คะแนนรวมเป็นค่าเฉลี่ยของกรรมการที่ตอบสำเร็จ แสดงจำนวน `/3` ชัดเจนเมื่อยังไม่ครบ คะแนนนี้ **คาดการณ์จากการอ่านสูตร ไม่ใช่การชิมจริง** และแยกจากคะแนนคนชิมเสมอ

ส่งสูตร คำอธิบายรสชาติ และปริมาณเป็นไทย พร้อมชื่อวัตถุดิบอังกฤษในวงเล็บ โดยยึดชื่อไทยที่ตรวจแล้ว ไม่แปลชื่อบนบาร์ใหม่ คำอธิบายไทยสำหรับกรรมการอยู่ใน `config/judge_flavors.th.json` (ฝั่งโมเดลสร้างสูตรยังใช้ภาษาอังกฤษตามเดิม) ปริมาณตามช้อนใหญ่ 25 mL รวมขวดบีบที่กะเทียบช้อนและ shaker ที่ยังไม่ทราบ mL ไม่ส่งชื่อจริงหรือชื่อเล่นของโมเดลผู้สร้าง ไม่ส่งคะแนนคนชิมหรือความเห็นของกรรมการคนอื่น คำวิจารณ์ภาษาไทยมีมุกตามคาแรกเตอร์ จุดดี จุดห่วง และข้อเสนอปรับสูตร; ตรวจ JSON ช่วงคะแนน ภาษาไทย และหน่วยที่ไม่รองรับก่อนส่งออก

ผลดิบและ usage เก็บที่ `.local/llm-judging/<dataset_id>/` (หรือ `--out`) ซึ่งถูก ignore แต่ละคำขอมี hash ของ dataset, prompt, rubric, โมเดล และสูตร บันทึกสถานะเริ่มส่งก่อนเรียก API และ flush คำตอบทุกครั้ง รันซ้ำจะใช้ cache ไม่คิดเงินซ้ำ ไม่ retry HTTP/transport/คำตอบผิดรูปแบบอัตโนมัติ ใช้ `--retry-failed` เมื่อเลือกลองคำขอที่ล้มเหลวหรือค้างเอง; การ retry อาจใช้เครดิตเพิ่ม

`web/data/judgments.json` เก็บเฉพาะบทวิจารณ์และคะแนนที่ตรวจแล้ว ผูกกับ `dataset_id` และ prompt version; `build_site.py` คำนวณดาวจากไฟล์นี้ทุกครั้ง หากเปลี่ยนสูตรจะไม่เอาคะแนนชุดเก่ามาติดสูตรใหม่ หากเปลี่ยน rubric ต้องรันกรรมการใหม่ เว็บให้กดอ่านรายกรรมการพร้อมดาวทั้งสี่ด้าน

Regenerate Recipes จะสร้างสูตรและรันกรรมการทั้งสามด้วย secret `OPENROUTER_API_KEY` ใน Action เดิม เก็บผลดิบใน artifact `benchmark-results` หากกรรมการบางคำขอไม่สำเร็จจะเตือนและเก็บเฉพาะบทวิจารณ์ที่ผ่าน Refresh Site ดึงรีวิวคนชิมและรวม baseline ที่บันทึกไว้โดยไม่เรียก LLM เพิ่ม

### สูตร v2

ใช้วัตถุดิบ 26 อย่างตามของบนบาร์: กระเทียมบดและผักชีซอย ไม่มีตัวเลือกกระเทียมกลีบหรือผักชีต้น ทั้งขั้น Noul คัดวัตถุดิบ (threshold 0.7) และ Choice เลือกปริมาณเห็น rubric ภาษาอังกฤษใน `config/preparation.json`: อร่อย 40%, กลมกล่อม 30%, ซับซ้อน 15%, แปลกใหม่ 15% น้ำหนักต้องตรงกับกรรมการ ซอสหมาล่า ซอสเห็ด เต้าซี่ปรุงรส ซาฉา น้ำมันพริก และเต้าหู้ยี้เป็นโอกาสสร้างรสที่แตกต่าง ไม่มีโบนัสจากการใส่เฉย ๆ ต้องเข้ากันและกินได้จริง รันใหม่แทนสูตรชุดก่อน ไม่ผสมผลข้ามชุดข้อมูล สคริปต์ regenerate ใช้ timeout 180 วินาทีต่อคำขอและไม่ retry อัตโนมัติ

ข้อจำกัดที่ตรวจในการรัน v2: Respan ต้องส่ง state เป็นข้อความ (สคริปต์แปลงโดยคงบริบทเดิม) และ API ปัจจุบันรับเฉพาะ Noul จึงยังสร้างปริมาณแบบ Choice ไม่ได้; Mercury รุ่นฟรีอาจติด privacy setting เรื่องใช้ข้อมูลฝึกโมเดลแม้ปิด ZDR แล้ว และ Perplexity `pplx-decider-v1-27b` ไม่มี endpoint ณ รอบนี้ เก็บ failure ไว้ในผลดิบและไม่แสดงโมเดลที่ไม่มีสูตรสำเร็จ

รอบ v2 วันที่ 10 ตุลาคม 2026 เรียกครบ 19 โมเดล × 3 โปรไฟล์ ได้สูตรพร้อมชิม 34 สูตรจาก 12 โมเดล อีก 20 งานเรียก API ไม่สำเร็จ และ 3 งานเป็นสูตรว่าง ชุดข้อมูล `77482f658baf2373f099` แทนชุดก่อนหน้า

### เก็บสูตรแต่ละรุ่นบนเว็บ

`web/data/versions.json` ระบุรุ่นปัจจุบันและชุดข้อมูลย้อนหลัง รุ่นที่ 1 คือชุดเดิมที่ใช้ threshold 0.5 (37 สูตร, dataset `8addfc43b935cfcd08f5`), รุ่นที่ 2 คือชุด v2 (34 สูตร) dropdown เลือกรุ่นแยกจากรอบทดลอง และ URL ใช้ `v=v1` / `v=v2` คะแนนและ Google Forms ยังผูก `dataset_id` เดิมของแต่ละรุ่น เมื่อสร้างชุดใหม่ `refresh_site.py` เก็บชุดปัจจุบันไว้ก่อนเพิ่มรุ่นใหม่ และ Refresh Site ดึงรีวิวคนให้ทุกรุ่นโดยคง rubric และคะแนนกรรมการเดิมของรุ่นเก่า

Dropdown โมเดลรวมทุกตัวที่มีสูตรในรุ่นใดก็ได้ หากโมเดลไม่มีสูตรในรุ่นที่เลือก จะคงโมเดลไว้และเลือกรุ่นที่ใกล้ที่สุดซึ่งมีสูตรของโปรไฟล์นั้น หากไม่มีโปรไฟล์ที่เลือกในทุกรุ่น จะเปิดโปรไฟล์ที่มีจริงและแสดงตัวเลือกใหม่ในหน้าเว็บ หากระยะเท่ากันเลือกรุ่นใหม่กว่า คะแนนเฉลี่ยใน dropdown ใช้สูตรจากรุ่นที่โมเดลนั้นจะเปิดให้ดู

รุ่นที่ 1 บนเว็บกู้จากชุด threshold 0.5 ไม่ใช่ชุด threshold 0.7 ที่สร้างระหว่างทาง เก็บคะแนนกรรมการเดิมด้วยน้ำหนัก 40/30/20/10 ส่วนรุ่นที่ 2 ใช้ threshold 0.7 และน้ำหนัก 40/30/15/15

### Leaderboard

`leaderboard.html` โหลดเฉพาะชุดที่ `versions.json.current` ระบุ แยกอันดับตามสามโปรไฟล์ด้วยคะแนนเฉลี่ยกรรมการเอไอครบสามคน ไม่รวมรุ่นเก่า หากมีหลายรอบในรุ่นเดียวกันใช้ค่าเฉลี่ยทุกรอบของโมเดล ไม่เลือกรอบที่ดีที่สุด คะแนนศูนย์จัดอันดับได้ คะแนนไม่ครบแสดงท้ายตารางโดยไม่มีอันดับ คะแนนเท่ากันได้อันดับร่วมกัน ชื่อเล่นเป็นค่าเริ่มต้น และกดเปิดชื่อจริงหรือไปดูสูตรได้

### การแสดงปริมาณเป็นช้อนเล็ก

หน้าสูตรทั้งรุ่นที่ 1 และรุ่นที่ 2 แปลงจำนวนช้อนเดิมเป็นช้อนเล็กด้วยตัวคูณ 4: ⅛ → ½, ¼ → 1, ½ → 2, 1 → 4 และ 2 → 8 ช้อนเล็ก รวมทั้งขวดบีบและที่คีบที่กะเทียบช้อน ยอดรวมใช้หน่วยเดียวกัน ส่วน shaker คงจำนวนครั้งเดิม ไม่ระบุ mL ของช้อนเล็กเพราะยังไม่ได้วัดจริง ข้อมูลคำตอบโมเดลต้นฉบับ รหัสสูตร คะแนน และรีวิวคงเดิม จึงไม่ต้องเรียก LLM ใหม่ การแปลงอยู่ใน `web/app.js` และยังใช้ได้หลัง Refresh Site ผ่าน Actions
