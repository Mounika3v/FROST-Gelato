from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

from src.catalog import CATEGORIES, all_products
from src.taste import query_match_score, taste_from_text


@dataclass
class Plan:
    kind: str
    text: str
    products: list[dict] = field(default_factory=list)
    category: str | None = None
    chosen: dict | None = None
    budget: int | None = None
    avoid: set[str] = field(default_factory=set)


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def detect_category(text: str) -> str | None:
    n = _norm(text)
    # Specific phrases must win over generic words such as "chocolate".
    if re.search(r"\b(ice[- ]?cream)\s+cakes?\b|\b(cakes?|cake)\b", n):
        return "Ice Cream Cake"
    if re.search(r"\b(ice[- ]?cream)\b", n):
        return "Ice Cream"
    if re.search(r"\b(toppings?|add[- ]?ons?|sprinkles?)\b", n):
        return "Toppings"
    # A negated chocolate phrase is a preference exclusion, not a request for
    # the chocolate collection (e.g. "I don't want chocolate flavour").
    chocolate_positive = re.search(r"\b(frost\s+chocolates?|chocolates?|chocolate\s+bars?|cocoa\s+bars?|dark\s+chocolate)\b", n)
    chocolate_negative = re.search(r"\b(?:no|not|without|avoid|dont want|don't want)\s+(?:any\s+)?(?:chocolate|cocoa|cacao|chocolaty|chocolatey)\b", n)
    if chocolate_positive and not chocolate_negative:
        return "Frost Chocolates"
    return None


def budget_from_text(text: str) -> int | None:
    m = re.search(r"(?:under|below|within|upto|up to|less than|budget(?: of)?|₹)\s*₹?\s*([0-9]{2,5})", (text or "").lower())
    return int(m.group(1)) if m else None


def comparison_direction(text: str) -> str | None:
    n = _norm(text)
    if re.search(r"\b(costliest|priciest|most expensive|highest priced|highest price|maximum price|most costly)\b", n):
        return "max"
    if re.search(r"\b(cheapest|least expensive|lowest priced|lowest price|minimum price|least costly)\b", n):
        return "min"
    return None


def _explicit_avoids(text: str) -> set[str]:
    n = _norm(text)
    out: set[str] = set()
    patterns = {
        "Nuts": r"\b(no nuts?|without nuts?|nut[- ]?free|avoid nuts?|allergic to nuts?|don't want nuts?|dont want nuts?)\b",
        "Milk": r"\b(no milk|without milk|dairy[- ]?free|milk[- ]?free|allergic to milk|no dairy)\b",
        "Soy": r"\b(no soy|without soy|soy[- ]?free|allergic to soy)\b",
        "Gluten": r"\b(no gluten|without gluten|gluten[- ]?free|allergic to gluten)\b",
        "Oats": r"\b(no oats?|without oats?|oat[- ]?free|allergic to oats?)\b",
    }
    for label, pat in patterns.items():
        if re.search(pat, n):
            out.add(label)
    return out


def _negative_traits(text: str) -> set[str]:
    n = _norm(text)
    # These are flavor exclusions, not sweetness modifiers. "not too sweet" is
    # deliberately NOT treated as "avoid sweet".
    out: set[str] = set()
    patterns = {
        "chocolate": r"\b(?:no|not|without|avoid|don't want|dont want|hate)\s+(?:any\s+)?(?:chocolate|cocoa|cacao|chocolaty|chocolatey)\b|\b(?:no|without|avoid|don't want|dont want)\s+(?:chocolate|cocoa|cacao)\s+(?:flavou?r|taste)\b",
        "fruity": r"\b(?:no|not|without|avoid|don't want|dont want)\s+(?:any\s+)?fruit(?:y)?\b",
        "nutty": r"\b(?:no|not|without|avoid|don't want|dont want)\s+(?:any\s+)?(?:nutty|nuts?)\b",
        "creamy": r"\b(?:no|not|without|avoid|don't want|dont want)\s+(?:any\s+)?(?:creamy|cream)\b",
    }
    for trait, pat in patterns.items():
        if re.search(pat, n):
            out.add(trait)
    return out


def _product_has_trait(product: dict, trait: str) -> bool:
    text = " ".join(str(product.get(k, "")) for k in ("Product", "Ingredients", "Category")).lower()
    vocab = {
        "chocolate": "chocolate cocoa cacao brownie mocha espresso nib",
        "fruity": "fruit berry berries mango strawberry peach fig orange lemon lime guava lychee pomegranate cherry blueberry blackberry apricot",
        "nutty": "nut nuts pistachio almond cashew hazelnut pecan sesame",
        "creamy": "cream creamy milk silk velvet custard coconut",
    }
    return any(re.search(rf"\b{re.escape(w)}\b", text) for w in vocab[trait].split())


def _candidate_pool(products: list[dict], text: str, profile: dict | None = None) -> tuple[list[dict], str | None, set[str]]:
    category = detect_category(text)
    pool = [p for p in products if category is None or p["Category"] == category]
    budget = budget_from_text(text)
    if budget is not None:
        pool = [p for p in pool if int(p["Price"]) <= budget]
    avoid = _explicit_avoids(text)
    if avoid:
        pool = [p for p in pool if not (set(p.get("Allergens", [])) & avoid)]
    negatives = _negative_traits(text)
    if negatives:
        pool = [p for p in pool if not any(_product_has_trait(p, trait) for trait in negatives)]
    return pool, category, negatives


def _rank(products: Iterable[dict], text: str, profile: dict | None = None) -> list[dict]:
    profile = profile or {}
    scored = []
    for p in products:
        explicit = query_match_score(text, p)
        # Current-message constraints are intentionally stronger than long-term taste.
        profile_score = 0
        if profile:
            profile_score = sum(int(v) * (1 if _product_has_trait(p, k) else 0) for k, v in profile.items() if int(v) > 0)
        scored.append((explicit * 10 + profile_score, p))
    scored.sort(key=lambda x: (-x[0], x[1]["Product"]))
    return [p for _, p in scored]


def _referenced_product(text: str, previous_products: list[dict]) -> dict | None:
    if not previous_products:
        return None
    n = _norm(text)
    ordinals = {"first": 0, "1st": 0, "second": 1, "2nd": 1, "third": 2, "3rd": 2, "fourth": 3, "4th": 3}
    m = re.search(r"\b(?:the\s+)?(first|1st|second|2nd|third|3rd|fourth|4th)\s+(?:one|option|choice|item)\b", n)
    if m and ordinals[m.group(1)] < len(previous_products):
        return previous_products[ordinals[m.group(1)]]
    if re.search(r"\b(that one|this one|the above|from above|those options|that product|this product)\b", n):
        return previous_products[0] if len(previous_products) == 1 else None
    return None


def plan(text: str, products: list[dict] | None = None, profile: dict | None = None,
         previous_products: list[dict] | None = None, previous_request: str = "") -> Plan:
    products = products or all_products()
    raw = (text or "").strip()
    n = _norm(raw)

    # Continuity: preserve the previous request while applying a new modifier.
    reference = bool(re.search(r"\b(same thing|same one|same as above|repeat that|repeat the above|repeat it|again)\b", n))
    effective = raw
    if reference and previous_request:
        stripped = re.sub(r"\b(same thing|same one|same as above|repeat that|repeat the above|repeat it|again)\b", "", raw, flags=re.I).strip(" ,.-")
        effective = f"{previous_request} {stripped}".strip()

    referenced = _referenced_product(raw, previous_products)
    if referenced and re.search(r"\b(price|cost|how much|ingredient|ingredients|allergen|allergy|nutrition|calories|kcal|fat|protein)\b", n):
        if re.search(r"\b(price|cost|how much)\b", n):
            return Plan("fact", f"**{referenced['Product']}** is ₹{referenced['Price']:,} for {referenced['Serving']} g.", [referenced], referenced.get("Category"))
        if re.search(r"\b(ingredient|ingredients)\b", n):
            return Plan("fact", f"**{referenced['Product']}** contains {referenced['Ingredients']}. Catalog-flagged allergens: {', '.join(referenced['Allergens']) if referenced['Allergens'] else 'None flagged'}.", [referenced], referenced.get("Category"))
        if re.search(r"\b(allergen|allergy)\b", n):
            return Plan("fact", f"For **{referenced['Product']}**, the catalog flags: {', '.join(referenced['Allergens']) if referenced['Allergens'] else 'None flagged'}.", [referenced], referenced.get("Category"))
        return Plan("fact", f"**{referenced['Product']}**: {referenced['kcal']} kcal, {referenced['Fat']} g fat, {referenced['Protein']} g protein per {referenced['Serving']} g.", [referenced], referenced.get("Category"))

    direction = comparison_direction(effective)
    if direction:
        pool, category, _ = _candidate_pool(products, effective, profile)
        # "these/those/options above" means exactly the previous displayed set.
        referential = bool(re.search(r"\b(these|those|the options|options above|above|from above|same)\b", n))
        if previous_products and not detect_category(effective) and (referential or re.search(r"\b(my preferences?|my taste|those options|all the options)\b", n)):
            pool = list(previous_products)
        if not pool:
            return Plan("comparison", "I couldn't find any catalog items that match those preferences.", category=category)
        chosen = (max if direction == "max" else min)(pool, key=lambda p: int(p["Price"]))
        article = "most expensive" if direction == "max" else "least expensive"
        noun = category.lower() if category else "match"
        if category:
            text_out = f"The {article} {noun} is **{chosen['Product']}** at **₹{chosen['Price']:,}**."
        else:
            text_out = f"The {article} match is **{chosen['Product']}** at **₹{chosen['Price']:,}**."
        return Plan("comparison", text_out, [chosen], category, chosen, budget_from_text(effective))

    # Exact inventory/category questions should list the actual category, not recommend unrelated items.
    if re.search(r"\b(what|which|show|list|tell me)\b", n) and re.search(r"\b(do you have|have|available|offer|flavou?r|options|choices|items)\b", n):
        category = detect_category(effective)
        if category:
            pool = [p for p in products if p["Category"] == category]
            names = ", ".join(p["Product"] for p in pool)
            return Plan("inventory", f"We have {len(pool)} {category.lower()} items: {names}.", [], category, budget=budget_from_text(effective))

    # A conversational reference can be handed to the LLM with the exact prior product,
    # so "tell me about that one" does not become a fresh recommendation search.
    if referenced:
        return Plan("followup", "", [referenced], referenced.get("Category"))

    # Strong negative preference must never be overridden by a generic chocolate/etc. match.
    pool, category, negatives = _candidate_pool(products, effective, profile)
    requested = taste_from_text(effective)
    has_recommendation_signal = bool(re.search(r"\b(recommend|recommendation|suggest|something|surprise|find me|looking for|mood|craving|under|budget|fruity|chocolate|creamy|refreshing|nutty|crunchy|sweet|best|favorite|favourite|pick|choose|want|need|dessert|treat|preferences|preference)\b", n)) or reference
    if has_recommendation_signal:
        if not pool:
            return Plan("recommendation", "I couldn't find an option that satisfies all of those preferences in the FROST catalog.", [], category, budget=budget_from_text(effective), avoid=_explicit_avoids(effective))
        if previous_products and re.search(r"\b(cheaper|less expensive|lower priced|more affordable)\b", n):
            ceiling = min(int(p["Price"]) for p in previous_products)
            cheaper = [p for p in pool if int(p["Price"]) < ceiling]
            if cheaper:
                pool = cheaper
        ranked = _rank(pool, effective, profile)
        # If the user named a specific category, stay in it. Otherwise prefer the best
        # three matches without inventing cross-category results.
        selected = ranked[:3]
        names = ", ".join(p["Product"] for p in selected)
        return Plan("recommendation", f"A few options that fit are {names}.", selected, category, budget=budget_from_text(effective), avoid=_explicit_avoids(effective))

    return Plan("conversation", "", [], category, budget=budget_from_text(effective), avoid=_explicit_avoids(effective))
