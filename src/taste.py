from __future__ import annotations

import hashlib
import random
import re

DEFAULT_TASTE = {
    "chocolate": 0,
    "fruity": 0,
    "nutty": 0,
    "creamy": 0,
    "sweet": 0,
    "crunchy": 0,
    "adventurous": 0,
}

KEYWORDS = {
    "chocolate": "chocolate cocoa cacao brownie mocha espresso",
    "fruity": "fruit berry berries mango strawberry peach fig orange lemon lime guava lychee pomegranate cherry blueberry blackberry apricot",
    "nutty": "nut nuts pistachio almond cashew hazelnut pecan sesame coconut",
    "creamy": "cream creamy milk velvet silk custard",
    "sweet": "sweet sweetness caramel jaggery honey toffee sugar sugary",
    "crunchy": "crunch crunchy crumble brittle crisp shards biscuit cookie nibs",
    "adventurous": "adventurous surprise unusual bold spicy cardamom saffron basil chili pepper rose",
}

# These are recommendation signals, not hard-coded product lists. They make an
# occasion materially affect ranking while still allowing the catalog to decide
# the actual products shown.
OCCASION_PROFILES = {
    "Birthday": {"category": {"Ice Cream Cake": 12, "Frost Chocolates": 4}, "terms": "celebration cake berry chocolate saffron rose"},
    "Anniversary": {"category": {"Frost Chocolates": 8, "Ice Cream": 3}, "terms": "chocolate rose fig cherry cocoa indulgent"},
    "Celebration": {"category": {"Ice Cream Cake": 10, "Frost Chocolates": 5}, "terms": "cake celebration berry saffron chocolate"},
    "Thank you": {"category": {"Frost Chocolates": 9, "Ice Cream Cake": 4}, "terms": "rose vanilla berry elegant saffron"},
    "Family time": {"category": {"Ice Cream": 8, "Ice Cream Cake": 4}, "terms": "vanilla chocolate caramel creamy fruit"},
    "Just because": {"category": {"Ice Cream": 7, "Toppings": 2}, "terms": "fruit refreshing chocolate comforting"},
}


def taste_from_text(text: str) -> dict[str, int]:
    low = re.sub(r"[^a-z0-9 ]+", " ", (text or "").lower())
    out = dict(DEFAULT_TASTE)
    for trait, words in KEYWORDS.items():
        out[trait] = min(5, sum(1 for w in words.split() if re.search(rf"\b{re.escape(w)}\b", low)))
    for trait, words in KEYWORDS.items():
        if re.search(rf"\b(no|not|dont|don't|avoid|hate|without)\b[^.?!]{{0,40}}\b(?:{words.replace(' ', '|')})\b", low):
            out[trait] = 0
    return out



def negative_taste_from_text(text: str) -> set[str]:
    low = re.sub(r"[^a-z0-9 ]+", " ", (text or "").lower())
    patterns = {
        "chocolate": r"\b(?:no|not|without|avoid|dont want|don't want|hate)\s+(?:any\s+)?(?:chocolate|cocoa|cacao|chocolaty|chocolatey)\b|\b(?:no|without|avoid|dont want|don't want)\s+(?:chocolate|cocoa|cacao)\s+(?:flavou?r|taste)\b",
        "fruity": r"\b(?:no|not|without|avoid|dont want|don't want)\s+(?:any\s+)?fruity?\b",
        "nutty": r"\b(?:no|not|without|avoid|dont want|don't want)\s+(?:any\s+)?nutty\b",
        "creamy": r"\b(?:no|not|without|avoid|dont want|don't want)\s+(?:any\s+)?(?:creamy|cream)\b",
    }
    return {trait for trait, pattern in patterns.items() if re.search(pattern, low)}

def merge_taste(profile: dict, delta: dict) -> dict:
    result = dict(DEFAULT_TASTE)
    result.update({k: int(v) for k, v in profile.items() if k in result})
    for key, value in delta.items():
        if value:
            result[key] = min(5, result[key] + int(value))
    return result


def product_traits(product: dict) -> dict[str, int]:
    text = " ".join(str(product.get(k, "")) for k in ("Product", "Ingredients", "Category")).lower()
    return {
        trait: min(5, sum(1 for w in words.split() if re.search(rf"\b{re.escape(w)}\b", text)))
        for trait, words in KEYWORDS.items()
    }



def query_match_score(query: str, product: dict) -> int:
    """Score explicit natural-language constraints against one catalog product.

    Explicit constraints are deliberately stronger than generic taste-profile
    similarity.  This keeps a product that merely shares one keyword from
    beating a product that satisfies the whole request.
    """
    low = re.sub(r"[^a-z0-9 ]+", " ", (query or "").lower())
    text = " ".join(str(product.get(k, "")) for k in ("Product", "Ingredients", "Category")).lower()
    score = 0

    def has_any(words: str) -> bool:
        return any(re.search(rf"\b{re.escape(w)}\b", text) for w in words.split())

    # Detect positive/negative constraints in natural language.
    positive = {
        "chocolate": "chocolate cocoa cacao brownie mocha espresso",
        "fruity": "fruit berry berries mango strawberry peach fig orange lemon lime guava lychee pomegranate cherry blueberry blackberry apricot",
        "creamy": "cream creamy milk velvet silk custard coconut",
        "nutty": "nut nuts pistachio almond cashew hazelnut pecan sesame coconut",
        "crunchy": "crunch crunchy crumble brittle crisp shards biscuit cookie nibs",
        "sweet": "sweet sweetness caramel jaggery honey toffee sugar sugary",
    }
    phrases = {
        "creamy": r"\b(creamy|cream(?:y)?|silky|velvety)\b",
        "mild_sweet": r"\b(mild(?:ly)? sweet(?:ness)?|less sweet|not too sweet|low sweetness|subtle(?:ly)? sweet|lightly sweet)\b",
        "dark": r"\b(dark chocolate|dark cocoa|dark cacao)\b",
    }

    for trait, words in positive.items():
        if re.search(rf"\b{re.escape(trait)}\b", low):
            score += 12 if has_any(words) else -12

    if re.search(phrases["creamy"], low):
        # Catalog-grounded proxies: dairy/cream or explicit creamy descriptors.
        score += 12 if has_any("cream creamy milk silk velvet custard coconut") else -12

    if re.search(phrases["dark"], low):
        score += 16 if has_any("dark cocoa cacao") else -12

    if re.search(phrases["mild_sweet"], low):
        try:
            sugar = float(product.get("Sugar", 0))
            # Lower sugar is a stronger match for "mild/less sweet".
            score += max(-14, min(14, int(round((20.0 - sugar) * 1.4))))
        except (TypeError, ValueError):
            pass

    # Explicit avoid constraints are hard penalties here; the application also
    # removes catalog-flagged allergens from the candidate pool.
    avoid_patterns = {
        "Nuts": r"\b(no nuts?|without nuts?|nut[- ]?free|avoid nuts?|allergic to nuts?)\b",
        "Milk": r"\b(no milk|without milk|dairy[- ]?free|milk[- ]?free|allergic to milk|no dairy)\b",
        "Soy": r"\b(no soy|without soy|soy[- ]?free|allergic to soy)\b",
        "Gluten": r"\b(no gluten|without gluten|gluten[- ]?free|allergic to gluten)\b",
        "Oats": r"\b(no oats?|without oats?|oat[- ]?free|allergic to oats?)\b",
    }
    allergen_set = set(product.get("Allergens", []))
    for label, pattern in avoid_patterns.items():
        if re.search(pattern, low) and label in allergen_set:
            score -= 100

    # Name/ingredient overlap is a tie-breaker, never the main decision rule.
    q_tokens = {t for t in re.findall(r"[a-z0-9]+", low) if len(t) >= 4}
    p_tokens = set(re.findall(r"[a-z0-9]+", text))
    score += min(8, 2 * len(q_tokens & p_tokens))
    return score

def match_score(profile: dict, product: dict) -> int:
    traits = product_traits(product)
    weights = {k: max(1, int(v)) for k, v in profile.items() if int(v) > 0}
    if not weights:
        return 68
    total = sum(weights.values())
    raw = sum(min(5, traits.get(k, 0)) * w for k, w in weights.items()) / (5 * total)
    return max(55, min(99, int(round(55 + raw * 44))))


def _occasion_score(product: dict, occasion: str | None) -> int:
    profile = OCCASION_PROFILES.get(occasion or "")
    if not profile:
        return 0
    text = " ".join(str(product.get(k, "")) for k in ("Product", "Ingredients", "Category")).lower()
    terms = profile["terms"].split()
    return sum(1 for term in terms if re.search(rf"\b{re.escape(term)}\b", text)) + profile["category"].get(product.get("Category"), 0)


def recommend_products(
    profile: dict,
    products: list[dict],
    limit: int = 3,
    occasion: str | None = None,
    budget: int | None = None,
    offset: int = 0,
) -> list[tuple[dict, int]]:
    pool = [p for p in products if budget is None or int(p.get("Price", 0)) <= int(budget)]
    if not pool:
        return []

    # The seed changes when the user asks for different options, but all scoring
    # remains tied to the profile/occasion/budget. This gives controlled variety,
    # not arbitrary random products.
    seed_text = repr((sorted(profile.items()), occasion, budget, offset, [p.get("Code") for p in pool]))
    rng = random.Random(int(hashlib.sha256(seed_text.encode()).hexdigest()[:12], 16))
    ranked = []
    for p in pool:
        base = match_score(profile, p)
        occ = _occasion_score(p, occasion)
        budget_fit = 0
        if budget:
            price = int(p.get("Price", 0))
            budget_fit = max(0, 6 - int((budget - price) / max(1, budget) * 6))
        jitter = rng.uniform(-2.2, 2.2)
        score = base + occ * 1.35 + budget_fit + jitter
        display = max(55, min(99, int(round(base + min(14, occ) * 1.2 + budget_fit))))
        ranked.append((score, p, display))

    ranked.sort(key=lambda x: (-x[0], x[1]["Product"]))
    # Use a wider candidate window and rotate it for deliberate refresh variation.
    candidate_count = min(len(ranked), max(limit * 5, 12))
    candidates = ranked[:candidate_count]
    if candidates:
        shift = offset % len(candidates)
        candidates = candidates[shift:] + candidates[:shift]

    selected = []
    used_categories = set()
    for item in candidates:
        if len(selected) >= limit:
            break
        _, product, display = item
        # Prefer variety between cards when the score is close.
        if len(selected) < limit - 1 and product.get("Category") in used_categories:
            continue
        selected.append((product, display))
        used_categories.add(product.get("Category"))
    if len(selected) < limit:
        for _, product, display in candidates:
            if all(product["Code"] != p["Code"] for p, _ in selected):
                selected.append((product, display))
            if len(selected) >= limit:
                break
    return selected


def rank_products(profile: dict, products: list[dict], limit: int = 3) -> list[tuple[dict, int]]:
    return recommend_products(profile, products, limit=limit)


def profile_summary(profile: dict) -> list[tuple[str, int]]:
    labels = {
        "chocolate": "Chocolate",
        "fruity": "Fruity",
        "nutty": "Nutty",
        "creamy": "Creamy",
        "sweet": "Sweet",
        "crunchy": "Crunch",
        "adventurous": "Adventure",
    }
    return [(labels[k], int(profile.get(k, 0))) for k in labels]
