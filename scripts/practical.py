"""Discrete station doses: Noul selects ingredients, Choice selects actual amounts."""

import copy
import math


def validate_config(config, ingredient_ids):
    if type(config["ladle_ml"]) not in (int, float) or not math.isfinite(config["ladle_ml"]) or config["ladle_ml"] <= 0:
        raise ValueError("ladle_ml must be positive and finite")
    amounts = config["ladle_amounts"]
    if (not isinstance(amounts, list) or not amounts or amounts[0] != 0
            or any(type(x) not in (int, float) or not math.isfinite(x) or x < 0 or x * 8 != int(x * 8) for x in amounts)
            or amounts != sorted(set(amounts)) or len(amounts) < 2):
        raise ValueError("ladle_amounts must start at zero and contain increasing eighth-ladle steps")
    if type(config["selection_threshold"]) not in (int, float) or not 0 <= config["selection_threshold"] <= 1:
        raise ValueError("selection_threshold must be in [0, 1]")
    if set(config["dispensers"]) - set(ingredient_ids) or any(x not in ("ladle", "squeeze", "shake", "tongs") for x in config["dispensers"].values()):
        raise ValueError("Unknown ingredient or dispenser")
    for key in ("shake_counts",):
        counts = config[key]
        if not isinstance(counts, list) or not counts or counts[0] != 0 or counts != sorted(set(counts)) or any(type(x) is not int or x < 0 for x in counts) or len(counts) < 2:
            raise ValueError(f"{key} must contain zero and increasing positive integer counts")


def selection_payload(base, config):
    payload = copy.deepcopy(base)
    state = payload["state"]
    state.pop("volume_mapping", None)
    state["preparation"] = f"Minced pork is fully cooked. Condiments are ready to eat. A station ladle holds approximately {config['ladle_ml']:g} mL; squeeze bottles, shakers, and tongs are also available as specified below."
    state["station"] = config
    state["selection_rule"] = "Choose a coherent dip without an ingredient-count cap. Complex recipes are allowed when each addition contributes useful flavor, aroma, or texture. Noul means probability of inclusion, never an amount. A separate stage will choose discrete doses."
    return payload


def shortlist(noul, profile, config):
    allowed = [name for name, value in noul.items() if name not in profile["excluded"] and value >= config["selection_threshold"]]
    return sorted(allowed, key=lambda name: (-noul[name], name))


def dose_options(name, config):
    dispenser = config["dispensers"].get(name, "ladle")
    choices = {"omit": {"amount": 0, "unit": dispenser, "volume_ml": 0}}
    if dispenser == "shake":
        for count in config[f"{dispenser}_counts"]:
            if count:
                choices[f"{dispenser}_{count}"] = {"amount": count, "unit": dispenser, "volume_ml": None}
    else:
        for amount in config["ladle_amounts"]:
            if amount:
                choices[f"ladle_eighths_{int(amount * 8)}"] = {"amount": amount, "unit": dispenser, "volume_ml": amount * config["ladle_ml"]}
    return choices


def amount_payload(base, name, selected, prepared, catalog, config):
    options = dose_options(name, config)
    item = next(i for i in catalog if i["id"] == name)
    state = copy.deepcopy(base["state"])
    state.update(selected_ingredients=selected, doses_already_chosen=prepared,
                 dosing_goal="Select a practical dose for this ingredient as part of the whole dip. Omit redundant ingredients. Consider all doses already chosen, strong seasoning, and the ingredients still to come. For squeeze bottles, estimate the dispensed volume against the 25 mL ladle; squeeze counts are not the unit. Shaker shakes have unknown volumes. Use seasoning judiciously; there is no hard cap on ingredient count or total ladle volume.")
    criteria = {}
    for key, dose in options.items():
        if key == "omit":
            description = "Omit this ingredient: unnecessary, redundant, or unsuitable for the current dip."
        elif dose["unit"] == "shake":
            description = f"Add {dose['amount']} gentle shaker shake(s). A small uncalibrated seasoning dose, not a 25 mL ladle."
        elif dose["unit"] == "squeeze":
            description = f"Squeeze until the dispensed volume is approximately {dose['amount']:g} of a {config['ladle_ml']:g} mL ladle ({dose['volume_ml']:g} mL approximately). Estimate by volume, not number of squeezes."
        else:
            action = "Use tongs to add herbs with loose volume equivalent to" if dose["unit"] == "tongs" else "Scoop"
            description = f"{action} {dose['amount']:g} of a {config['ladle_ml']:g} mL ladle ({dose['volume_ml']:g} mL approximately)."
        criteria[key] = description + f" Choose this amount only when it balances {item['name']} with the entire dip."
    return {"model": base["model"], "state": state, "questions": {name: {
        "type": "choice", "instructions": f"How much {item['name']} should be added now? Flavor and texture: {item['flavor']}", "criteria": criteria,
    }}}, options


def parse_choice(response, name, options):
    answers = response.get("answers") if isinstance(response, dict) else None
    if not isinstance(answers, dict) or set(answers) != {name}:
        raise ValueError("Expected exactly one dose answer")
    answer = answers[name]
    if not isinstance(answer, dict) or answer.get("type") != "choice" or not isinstance(answer.get("choice"), str) or answer["choice"] not in options:
        raise ValueError("Dose must be one of the allowed choices")
    probabilities = answer.get("probabilities")
    if not isinstance(probabilities, dict) or set(probabilities) != set(options) or any(type(p) not in (int, float) or not math.isfinite(p) or not 0 <= p <= 1 for p in probabilities.values()):
        raise ValueError("Invalid dose probabilities")
    if not math.isclose(sum(probabilities.values()), 1, abs_tol=.02):
        raise ValueError("Dose probabilities must sum to one")
    return options[answer["choice"]]


def generate_recipe(base, profile, catalog, config, ask, parse_noul):
    """ask retains every request/response; selection and doses are never averaged."""
    response = ask(base)
    noul = parse_noul(response)
    selected = shortlist(noul, profile, config)
    prepared = {}
    for name in selected:
        payload, options = amount_payload(base, name, selected, prepared, catalog, config)
        if len(options) == 1:
            dose = options["omit"]
        else:
            dose = parse_choice(ask(payload), name, options)
        prepared[name] = dose
    servings = {i["id"]: prepared.get(i["id"], {"amount": 0, "unit": config["dispensers"].get(i["id"], "ladle"), "volume_ml": 0}) for i in catalog}
    return noul, selected, servings
