from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

from src.catalog import CATEGORIES, all_products
from src.taste import product_traits, query_match_score, taste_from_text


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
    """Normalize user text for tolerant keyword matching."""
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _category_noun(category: str) -> str:
    return {
        "Ice Cream": "ice-cream flavours",
        "Ice Cream Cake": "ice-cream cakes",
        "Frost Chocolates": "chocolates",
        "Toppings": "toppings",
    }.get(category, category.lower())


def detect_category(text: str) -> str | None:
    """Resolve the customer's intended catalog category.

    More specific product/category phrases win over broad words like "flavours".
    A negative phrase such as "I don't want chocolate flavour" is treated as a
    taste exclusion, not as a request for the chocolate collection.
    """
    raw = text or ""
    n = _norm(raw)

    # Specific category phrases first.
    if re.search(r"\bice[- ]?cream\s+cakes?\b|\bcakes?\b", n):
        return "Ice Cream Cake"

    # Explicit ice-cream/gelato mention must beat generic "flavour(s)".
    if re.search(r"\bice[- ]?creams?\b|\bgelatos?\b", n):
        return "Ice Cream"

    if re.search(r"\btoppings?\b|\badd[- ]?ons?\b|\bsprinkles?\b", n):
        return "Toppings"

    chocolate_negative = bool(
        re.search(
            r"\b(?:no|not|without|avoid|hate)\s+(?:any\s+)?"
            r"(?:chocolate|cocoa|cacao|chocolaty|chocolatey)\b",
            n,
        )
        or re.search(
            r"\b(?:dont|don\s+t)\s+want\s+(?:any\s+)?"
            r"(?:chocolate|cocoa|cacao|chocolaty|chocolatey)\b",
            n,
        )
        or re.search(
            r"\b(?:no|without|avoid)\s+(?:chocolate|cocoa|cacao)\s+(?:flavou?r|taste)\b",
            n,
        )
        or re.search(
            r"\b(?:dont|don\s+t)\s+want\s+(?:chocolate|cocoa|cacao)\s+(?:flavou?r|taste)\b",
            n,
        )
    )
    chocolate_positive = bool(
        re.search(
            r"\b(frost\s+chocolates?|chocolates?|chocolate\s+bars?|"
            r"cocoa\s+bars?|dark\s+chocolate)\b",
            n,
        )
    )
    if chocolate_positive and not chocolate_negative:
        return "Frost Chocolates"

    # A standalone "flavours" question conventionally refers to ice cream in FROST.
    if re.search(r"\bflavou?rs?\b|\bflavou?r\b", n) and not chocolate_negative:
        return "Ice Cream"

    return None


def budget_from_text(text: str) -> int | None:
    n = (text or "").lower()
    m = re.search(
        r"(?:under|below|within|upto|up to|less than|budget(?: of)?|rs\.?|inr|₹)\s*₹?\s*(\d{1,3}(?:,\d{3})+|\d{2,5})",
        n,
    )
    return int(m.group(1).replace(",", "")) if m else None


def comparison_direction(text: str) -> str | None:
    n = _norm(text)
    if re.search(r"\b(costliest|priciest|most expensive|highest priced|highest price|maximum price|most costly)\b", n):
        return "max"
    if re.search(r"\b(cheapest|least expensive|lowest priced|lowest price|minimum price|least costly)\b", n):
        return "min"
    return None


def _explicit_avoids(text: str) -> set[str]:
    """Extract catalog allergen exclusions from natural language."""
    # Use lightly normalized lowercase text but preserve apostrophes as optional.
    n = (text or "").lower().replace("’", "'")
    patterns = {
        "Nuts": r"\b(?:no|without|avoid|allergic to|hate)\s+(?:any\s+)?(?:nuts?|pistachio|almond|cashew|hazelnut|pecan)\b|\bnut[- ]?free\b|\b(?:dont|don\s*'t)\s+want\s+(?:any\s+)?(?:nuts?|pistachio|almond|cashew|hazelnut|pecan)\b",
        "Milk": r"\b(?:no|without|avoid|allergic to|hate)\s+(?:any\s+)?(?:milk|dairy)\b|\b(?:dairy|milk)[- ]?free\b|\b(?:dont|don\s*'t)\s+want\s+(?:any\s+)?(?:milk|dairy)\b",
        "Soy": r"\b(?:no|without|avoid|allergic to|hate)\s+(?:any\s+)?soy\b|\bsoy[- ]?free\b|\b(?:dont|don\s*'t)\s+want\s+(?:any\s+)?soy\b",
        "Gluten": r"\b(?:no|without|avoid|allergic to|hate)\s+(?:any\s+)?(?:gluten|wheat)\b|\bgluten[- ]?free\b|\b(?:dont|don\s*'t)\s+want\s+(?:any\s+)?(?:gluten|wheat)\b",
        "Oats": r"\b(?:no|without|avoid|allergic to|hate)\s+(?:any\s+)?oats?\b|\boat[- ]?free\b|\b(?:dont|don\s*'t)\s+want\s+(?:any\s+)?oats?\b",
    }
    return {label for label, pattern in patterns.items() if re.search(pattern, n)}


def _negative_traits(text: str) -> set[str]:
    """Extract explicit flavour exclusions without misreading "not too sweet"."""
    n = (text or "").lower().replace("’", "'")
    out: set[str] = set()
    patterns = {
        "chocolate": r"\b(?:no|not|without|avoid|hate)\s+(?:any\s+)?(?:chocolate|cocoa|cacao|chocolaty|chocolatey)\b|\b(?:dont|don\s*'t)\s+want\s+(?:any\s+)?(?:chocolate|cocoa|cacao|chocolaty|chocolatey)\b|\b(?:no|without|avoid|dont|don\s*'t)\s+(?:chocolate|cocoa|cacao)\s+(?:flavou?r|taste)\b",
        "fruity": r"\b(?:no|not|without|avoid|hate)\s+(?:any\s+)?fruity?\b|\b(?:dont|don\s*'t)\s+want\s+(?:any\s+)?fruity?\b",
        "nutty": r"\b(?:no|not|without|avoid|hate)\s+(?:any\s+)?nutty\b|\b(?:dont|don\s*'t)\s+want\s+(?:any\s+)?nutty\b",
        "creamy": r"\b(?:no|not|without|avoid|hate)\s+(?:any\s+)?(?:creamy|cream)\b|\b(?:dont|don\s*'t)\s+want\s+(?:any\s+)?(?:creamy|cream)\b",
    }
    for trait, pattern in patterns.items():
        if re.search(pattern, n):
            out.add(trait)
    return out


def _product_has_trait(product: dict, trait: str) -> bool:
    """Safely test a product against the canonical trait vocabulary."""
    try:
        return int(product_traits(product).get(trait, 0)) > 0
    except (TypeError, ValueError, KeyError):
        return False


def _candidate_pool(
    products: list[dict], text: str, profile: dict | None = None
) -> tuple[list[dict], str | None, set[str]]:
    category = detect_category(text)
    pool = [p for p in products if category is None or p.get("Category") == category]

    budget = budget_from_text(text)
    if budget is not None:
        pool = [p for p in pool if int(p.get("Price", 0)) <= budget]

    avoid = _explicit_avoids(text)
    if avoid:
        pool = [p for p in pool if not (set(p.get("Allergens", [])) & avoid)]

    negatives = _negative_traits(text)
    if negatives:
        pool = [
            p for p in pool
            if not any(_product_has_trait(p, trait) for trait in negatives)
        ]

    return pool, category, negatives


def _rank(products: Iterable[dict], text: str, profile: dict | None = None) -> list[dict]:
    profile = profile or {}
    scored = []
    for p in products:
        explicit = query_match_score(text, p)
        profile_score = 0
        for key, value in profile.items():
            try:
                weight = int(value)
            except (TypeError, ValueError):
                continue
            if weight > 0 and _product_has_trait(p, key):
                profile_score += weight
        scored.append((explicit * 10 + profile_score, p))
    scored.sort(key=lambda x: (-x[0], x[1].get("Product", "")))
    return [p for _, p in scored]


def _referenced_product(text: str, previous_products: list[dict]) -> dict | None:
    if not previous_products:
        return None
    n = _norm(text)
    ordinals = {
        "first": 0,
        "1st": 0,
        "second": 1,
        "2nd": 1,
        "third": 2,
        "3rd": 2,
        "fourth": 3,
        "4th": 3,
    }
    m = re.search(
        r"\b(?:the\s+)?(first|1st|second|2nd|third|3rd|fourth|4th)\s+(?:one|option|choice|item)\b",
        n,
    )
    if m and ordinals[m.group(1)] < len(previous_products):
        return previous_products[ordinals[m.group(1)]]
    if re.search(r"\b(that one|this one|the above|from above|those options|that product|this product)\b", n):
        return previous_products[0] if len(previous_products) == 1 else None
    return None


def _direct_product_reference(text: str, products: list[dict]) -> dict | None:
    """Match a complete catalog product name in the customer's message."""
    n = _norm(text)
    candidates = sorted(
        products,
        key=lambda p: len(_norm(p.get("Product", ""))),
        reverse=True,
    )
    for product in candidates:
        name = _norm(product.get("Product", ""))
        if name and re.search(rf"\b{re.escape(name)}\b", n):
            return product
    return None


def _fact_plan(text: str, products: list[dict], previous_products: list[dict]) -> Plan | None:
    """Answer exact product facts from the catalog, without asking the LLM."""
    n = _norm(text)
    referenced = _referenced_product(text, previous_products) or _direct_product_reference(text, products)
    if not referenced:
        return None

    category = referenced.get("Category")
    if re.search(r"\b(price|cost|how much|rupee|rupees)\b|₹", n):
        return Plan(
            "fact",
            f"**{referenced['Product']}** is ₹{int(referenced['Price']):,} for {int(referenced['Serving'])} g.",
            [referenced],
            category,
        )

    if re.search(r"\b(ingredient|ingredients|contains|made of|what is in|what s in|what\s+is\s+inside)\b", n):
        allergens = ", ".join(referenced.get("Allergens", [])) or "None flagged"
        return Plan(
            "fact",
            f"**{referenced['Product']}** contains {referenced['Ingredients']}. Catalog-flagged allergens: {allergens}.",
            [referenced],
            category,
        )

    if re.search(r"\b(allergens?|allergies?|allergic)\b", n):
        allergens = ", ".join(referenced.get("Allergens", [])) or "None flagged"
        return Plan(
            "fact",
            f"For **{referenced['Product']}**, the catalog flags: {allergens}.",
            [referenced],
            category,
        )

    if re.search(r"\b(calories|kcal|nutrition|fat|protein|sugar)\b", n):
        return Plan(
            "fact",
            f"**{referenced['Product']}**: {referenced['kcal']} kcal, {referenced['Fat']} g fat, {referenced['Protein']} g protein, and {referenced['Sugar']} g sugar per {referenced['Serving']} g.",
            [referenced],
            category,
        )

    # A product-specific conversational question should still carry the exact
    # product into the LLM context so the app can answer it without hallucinating.
    return Plan("followup", "", [referenced], category)


def _inventory_requested(text: str) -> bool:
    n = _norm(text)
    # Recommendation verbs should stay on the recommendation path.
    if re.search(r"\b(recommend|recommendation|suggest|suggestion)\b", n):
        return False
    question_word = re.search(r"\b(what|which|show|list|tell me|can you tell me|how many)\b", n)
    inventory_word = re.search(
        r"\b(do you have|have|available|offer|serve|serving|flavou?r|options|choices|items|varieties|selection|menu|carry|sell|ice[- ]?creams?|gelatos?|cakes?|chocolates?|toppings?)\b",
        n,
    )
    return bool(question_word and inventory_word)


def _inventory_plan(text: str, products: list[dict]) -> Plan | None:
    if not _inventory_requested(text):
        return None
    category = detect_category(text)
    budget = budget_from_text(text)

    if category:
        pool = [p for p in products if p.get("Category") == category]
        if budget is not None:
            pool = [p for p in pool if int(p.get("Price", 0)) <= budget]
        names = ", ".join(p["Product"] for p in pool)
        noun = _category_noun(category)
        # Keep the existing project test contract for the Toppings label while
        # using natural wording for the other collections.
        if category == "Toppings":
            noun = "toppings items"
        if re.search(r"\bhow many\b", _norm(text)):
            count_text = f"FROST has {len(pool)} {noun}."
            if budget is not None:
                count_text = f"FROST has {len(pool)} {noun} within ₹{budget:,}."
            return Plan("inventory", count_text, [], category, budget=budget)
        if budget is not None:
            return Plan(
                "inventory",
                f"I have {len(pool)} {noun} within ₹{budget:,}: {names or 'none.'}",
                [],
                category,
                budget=budget,
            )
        return Plan(
            "inventory",
            f"I have {len(pool)} {noun}: {names or 'none.'}",
            [],
            category,
        )

    counts = {c: sum(p.get("Category") == c for p in products) for c in CATEGORIES}
    text_out = (
        "FROST has "
        + ", ".join(f"{counts[c]} {_category_noun(c)}" for c in CATEGORIES)
        + ". Tell me which collection you'd like to explore."
    )
    return Plan("inventory", text_out, [], None, budget=budget)


def plan(
    text: str,
    products: list[dict] | None = None,
    profile: dict | None = None,
    previous_products: list[dict] | None = None,
    previous_request: str = "",
) -> Plan:
    products = products or all_products()
    previous_products = previous_products or []
    raw = (text or "").strip()
    n = _norm(raw)

    # Continuity: preserve the previous request while applying a new modifier.
    reference = bool(
        re.search(r"\b(same thing|same one|same as above|repeat that|repeat the above|repeat it|again)\b", n)
    )
    effective = raw
    if reference and previous_request:
        stripped = re.sub(
            r"\b(same thing|same one|same as above|repeat that|repeat the above|repeat it|again)\b",
            "",
            raw,
            flags=re.I,
        ).strip(" ,.-")
        effective = f"{previous_request} {stripped}".strip()

    # Exact product/follow-up facts first.
    fact = _fact_plan(raw, products, previous_products)
    if fact:
        return fact

    direction = comparison_direction(effective)
    if direction:
        pool, category, _ = _candidate_pool(products, effective, profile)
        referential = bool(
            re.search(r"\b(these|those|the options|options above|above|from above|same)\b", n)
        )
        if previous_products and not detect_category(effective) and (
            referential or re.search(r"\b(my preferences?|my taste|those options|all the options)\b", n)
        ):
            pool = list(previous_products)
        if not pool:
            return Plan(
                "comparison",
                "I couldn't find any catalog items that match those preferences.",
                category=category,
            )
        chosen = (max if direction == "max" else min)(pool, key=lambda p: int(p["Price"]))
        article = "most expensive" if direction == "max" else "least expensive"
        noun = _category_noun(category) if category else "match"
        noun = noun.rstrip("s") if noun.endswith("flavours") else noun
        text_out = (
            f"The {article} {noun} is **{chosen['Product']}** at **₹{int(chosen['Price']):,}**."
            if category
            else f"The {article} match is **{chosen['Product']}** at **₹{int(chosen['Price']):,}**."
        )
        return Plan(
            "comparison",
            text_out,
            [chosen],
            category,
            chosen,
            budget_from_text(effective),
        )

    inventory = _inventory_plan(effective, products)
    if inventory:
        return inventory

    # A conversational product reference can be handed to the LLM with the exact product.
    referenced = _referenced_product(raw, previous_products)
    if referenced:
        return Plan("followup", "", [referenced], referenced.get("Category"))

    # Strong negative preference must never be overridden by a generic keyword match.
    pool, category, _ = _candidate_pool(products, effective, profile)
    has_recommendation_signal = bool(
        re.search(
            r"\b(recommend|recommendation|suggest|something|surprise|find me|looking for|mood|craving|under|budget|fruity|chocolate|creamy|refreshing|nutty|crunchy|sweet|best|favorite|favourite|pick|choose|want|need|dessert|treat|preferences|preference)\b",
            n,
        )
    ) or reference

    if has_recommendation_signal:
        if not pool:
            return Plan(
                "recommendation",
                "I couldn't find an option that satisfies all of those preferences in the FROST catalog.",
                [],
                category,
                budget=budget_from_text(effective),
                avoid=_explicit_avoids(effective),
            )

        if previous_products and re.search(
            r"\b(cheaper|less expensive|lower priced|more affordable)\b", n
        ):
            ceiling = min(int(p["Price"]) for p in previous_products)
            cheaper = [p for p in pool if int(p["Price"]) < ceiling]
            if cheaper:
                pool = cheaper

        ranked = _rank(pool, effective, profile)
        selected = ranked[:3]
        names = ", ".join(p["Product"] for p in selected)
        return Plan(
            "recommendation",
            f"A few options that fit are {names}.",
            selected,
            category,
            budget=budget_from_text(effective),
            avoid=_explicit_avoids(effective),
        )

    return Plan(
        "conversation",
        "",
        [],
        category,
        budget=budget_from_text(effective),
        avoid=_explicit_avoids(effective),
    )
