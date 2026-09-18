from __future__ import annotations

import hashlib
import random
import re
import uuid
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv

from src.account import validate_email
from src.storage import authenticate, create_user, get_favorites, get_orders, init_db, save_order, save_profile, set_favorite, update_name, load_profile
from src.catalog import CATEGORIES, CATEGORY_LABELS, all_products, catalog_context, category_products, products_mentioned, search_catalog
from src.invoice import invoice_pdf
from src.llm import api_ready, ask_gemini
from src.order import add_item, cart_count, cart_total, money, parse_quantity, remove_item, set_qty
from src.pdf_rag import retrieve_pdf
from src.taste import DEFAULT_TASTE, merge_taste, negative_taste_from_text, profile_summary, recommend_products, taste_from_text, query_match_score
from src.gelato_engine import plan as build_gelato_plan
from src.ui import inject_css, render_slideshow

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env", override=True)
st.set_page_config(page_title="FROST · Gelato", page_icon="🍨", layout="wide", initial_sidebar_state="collapsed")
inject_css()
init_db()

PRODUCTS = all_products()
HEROES = [
    (ROOT / "assets" / "hero" / "ice_cream.png", "The FROST collection"),
    (ROOT / "assets" / "hero" / "cakes.png", "Celebrations, layered beautifully"),
    (ROOT / "assets" / "hero" / "chocolates.jpg", "Chocolate, after dark"),
    (ROOT / "assets" / "hero" / "toppings.png", "Finish it your way"),
]
GELATO_VIDEO = ROOT / "assets" / "media" / "gelato_shop.mp4"
GELATO_AVATAR = ROOT / "assets" / "gelato_avatar.png"
USER_AVATAR = ROOT / "assets" / "user_avatar.png"

VIEWS = {"home", "chat", "flavor", "gift", "surprise", "shop", "cart", "checkout", "account", "confirmation"}


def init_state():
    defaults = {
        "view": "home",
        "messages": [{"role": "assistant", "content": "Welcome to FROST. I'm Gelato. What are you in the mood for today?"}],
        "cart": [],
        "favorites": set(),
        "orders": [],
        "customer": {"signed_in": False, "user_id": None, "name": "", "email": ""},
        "taste": dict(DEFAULT_TASTE),
        "taste_avoid": set(),
        "occasion": "Birthday",
        "occasion_selector": "Birthday",
        "gift_budget": 1500,
        "recommend_offset": 0,
        "recommend_seed": random.SystemRandom().randint(0, 10_000_000),
        "checkout_snapshot": [],
        "order_number": None,
        "checkout_complete": False,
        "payment": "UPI",
        "llm_cache": {},
        "last_selected": None,
        "pending_order": None,
        "scroll_top": False,
        "last_user_request": "",
        "last_result_codes": [],
        "last_query_candidates": [],
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


init_state()


def customer_name() -> str:
    return st.session_state.customer.get("name") or "Guest"


def product_by_code(code: str):
    return next((p for p in PRODUCTS if p["Code"] == code), None)


def toggle_favorite(product: dict):
    code = product["Code"]
    if code in st.session_state.favorites:
        st.session_state.favorites.discard(code)
        if st.session_state.customer.get("user_id"):
            set_favorite(st.session_state.customer["user_id"], code, False)
    else:
        st.session_state.favorites.add(code)
        if st.session_state.customer.get("user_id"):
            set_favorite(st.session_state.customer["user_id"], code, True)


def is_greeting(text: str) -> bool:
    return bool(re.fullmatch(r"\s*(hi|hello|hey|hiya|good morning|good afternoon|good evening)[!.? ]*", text or "", re.I))


def explicit_order_intent(text: str) -> bool:
    low = re.sub(r"\s+", " ", (text or "").lower().strip())
    # "order/buy something" is still a discovery request, not a cart mutation.
    if re.search(r"\b(order|buy|purchase|get|take)\s+(?:me\s+)?(?:something|anything|some|a|an)\b", low):
        return False
    # Recommendation language must never be mistaken for a cart command.
    if re.search(r"\b(find|show|recommend|suggest|something|options|looking for|surprise me)\b", low):
        return bool(re.search(r"\b(add|put)\b.*\b(cart|order)\b|\b(order|buy|purchase)\b.*\b(?:this|that|it|one|product|item)\b", low))
    return bool(
        re.search(r"\b(order|buy|purchase|take|i.?ll take|add|put)\b", low)
        or re.search(r"\b(?:to|into) my (?:cart|order)\b", low)
    )


def cart_context() -> str:
    if not st.session_state.cart:
        return "Empty"
    return "; ".join(f"{i['qty']} × {i['Product']} @ {money(i['Price'])}" for i in st.session_state.cart)


def resolve_product(text: str):
    found = products_mentioned(text, limit=6)
    if found:
        return found[0]
    low = text.lower()
    if re.search(r"\b(that|this|it|same|one|those)\b", low) and st.session_state.get("last_selected"):
        return st.session_state.last_selected
    recent = []
    for message in reversed(st.session_state.messages):
        if message.get("role") == "assistant":
            recent = products_mentioned(message.get("content", ""), limit=6)
            if recent:
                break
    for word, idx in [("first", 0), ("1st", 0), ("second", 1), ("2nd", 1), ("third", 2), ("3rd", 2)]:
        if re.search(rf"\b{word}\b", low) and len(recent) > idx:
            return recent[idx]
    return None


def add_to_cart(product: dict, qty: int = 1):
    qty = max(1, min(20, int(qty)))
    add_item(st.session_state.cart, product, qty)
    st.session_state.last_selected = product


@st.dialog("FROST · Add to order")
def order_dialog(product: dict):
    if product.get("Image"):
        st.image(product["Image"], use_container_width=True)
    st.markdown(f"### {product['Product']}")
    st.caption(f"{product['Category']} · {product['Serving']} g")
    qty = st.number_input("Quantity", min_value=1, max_value=20, value=1, step=1, key=f"order_qty_{product['Code']}")
    st.markdown(f'<div class="checkout-total">Total · {money(product["Price"] * qty)}</div>', unsafe_allow_html=True)
    if st.button("Add to order", type="primary", use_container_width=True):
        add_to_cart(product, int(qty))
        st.session_state.view = "cart"
        st.session_state.scroll_top = True
        st.rerun()

def order_now(product: dict):
    order_dialog(product)


def handle_order(text: str):
    low = text.lower().strip()
    if re.search(r"\b(remove|delete)\b", low) and st.session_state.cart:
        target = resolve_product(text)
        if target:
            st.session_state.cart = remove_item(st.session_state.cart, target["Code"])
            return f"Removed **{target['Product']}** from your cart."
        return "Which item would you like me to remove?"
    if not explicit_order_intent(text):
        return None
    product = resolve_product(text)
    if not product:
        st.session_state.pending_order = {"qty": parse_quantity(text, 1)}
        return "Of course. Which FROST item would you like me to add?"
    qty = parse_quantity(text, 1)
    add_to_cart(product, qty)
    return f"Added **{product['Product']} × {qty}** to your cart — {money(product['Price'] * qty)}."


def local_answer(text: str):
    low = text.lower().strip()
    if is_greeting(text):
        name = f", {customer_name()}" if customer_name() != "Guest" else ""
        return f"Hi{name}. What are you in the mood for today?"
    if low in {"thanks", "thank you", "thx"}:
        return "Anytime. Take your time — I'm right here."
    if any(x in low for x in ("sad", "rough day", "bad day", "upset", "stressed", "tired", "exhausted", "not feeling good")):
        return "I'm sorry you're having a rough day. We can keep it simple — something rich and comforting, something bright and fruity, or I can choose a little treat for you."
    if re.search(r"\b(why|how come)\b", low) and re.search(r"\b(expensive|costly|pricey|prices|price)\b", low):
        prices = [int(p["Price"]) for p in PRODUCTS]
        return f"Our collection spans {money(min(prices))} to {money(max(prices))}, depending on the product type and serving. If you want, I can show you some of the more affordable options."
    if re.search(r"\b(?:my cart|what.?s in my cart|cart)\b", low):
        if not st.session_state.cart:
            return "Your cart is empty. I can help you find something whenever you're ready."
        return f"You have {cart_count(st.session_state.cart)} item(s) in your cart, totaling {money(cart_total(st.session_state.cart))}."
    if re.search(r"\b(?:menu|collection|catalog)\b", low):
        return "FROST has 30 ice creams, 10 ice-cream cakes, 15 chocolates and 25 toppings. Tell me what you're craving and I'll narrow it down."
    ps = products_mentioned(text, limit=3)
    if ps:
        p = ps[0]
        if re.search(r"\b(price|cost|how much|₹|rupee|rupees)\b", low):
            return f"{p['Product']} is {money(p['Price'])} for {p['Serving']} g."
        if re.search(r"\b(ingredient|ingredients|contains|made of)\b", low):
            allergens = ", ".join(p["Allergens"]) if p["Allergens"] else "None flagged"
            return f"{p['Product']} contains {p['Ingredients']}. Catalog-flagged allergens: {allergens}."
        if re.search(r"\b(allergen|allergy|allergic)\b", low):
            return f"For {p['Product']}, the catalog flags: {', '.join(p['Allergens']) if p['Allergens'] else 'None flagged'}."
    return None


def validate_reply(reply: str | None, allowed_products: list[dict] | None = None):
    if not reply:
        return None
    banned = ["api key", "api quota", "rate limit", "gemini error", "system prompt", "retrieval pipeline", "python code", "internal error"]
    if any(x in reply.lower() for x in banned):
        return None
    allowed_prices = {int(p["Price"]) for p in PRODUCTS}
    for value in re.findall(r"₹\s*([0-9,]+)", reply):
        if int(value.replace(",", "")) not in allowed_prices:
            return None
    if allowed_products is not None:
        allowed_codes = {p["Code"] for p in allowed_products}
        mentioned = products_mentioned(reply, limit=20)
        if any(p["Code"] not in allowed_codes for p in mentioned):
            return None
        # When the assistant pairs a product with a rupee amount, require the
        # amount to match the catalog for that product.
        for p in mentioned:
            m = re.search(rf"{re.escape(p['Product'])}[^₹]{{0,90}}₹\s*([0-9,]+)", reply, re.I)
            if m and int(m.group(1).replace(",", "")) != int(p["Price"]):
                return None
    return reply.strip()


def _budget_from_text(text: str) -> int | None:
    m = re.search(r'(?:under|below|within|upto|up to|less than|budget(?: of)?|₹)\s*₹?\s*(\d{2,5})', text.lower())
    return int(m.group(1)) if m else None


def _candidate_products(text: str) -> list[dict]:
    low = text.lower()
    budget = _budget_from_text(text)
    category = None
    if any(w in low for w in ("cake", "birthday", "celebration")):
        category = "Ice Cream Cake"
    elif any(w in low for w in ("chocolate", "cocoa", "cacao", "bar")):
        category = "Frost Chocolates" if "bar" in low or "chocolate" in low and "ice cream" not in low else None
    hits = search_catalog(text, category=category, limit=18)
    if not hits and category:
        hits = category_products(category)
    pool = hits or PRODUCTS
    if budget is not None:
        pool = [p for p in pool if int(p["Price"]) <= budget]
    if any(x in low for x in ("nut free", "without nuts", "no nuts", "nut allergy", "allergic to nuts")):
        pool = [p for p in pool if "Nuts" not in p["Allergens"]]
    if any(x in low for x in ("dairy free", "without milk", "no milk", "milk allergy")):
        pool = [p for p in pool if "Milk" not in p["Allergens"]]
    if not pool and budget is not None:
        pool = [p for p in PRODUCTS if int(p["Price"]) <= budget]
    return pool[:18]



def _preference_terms() -> list[str]:
    mapping = {
        "chocolate": "chocolate cocoa cacao",
        "fruity": "fruit berry mango strawberry peach fig orange lemon lime guava lychee pomegranate cherry blueberry blackberry apricot",
        "nutty": "nutty pistachio almond cashew hazelnut pecan sesame coconut",
        "creamy": "creamy cream milk silk velvet coconut cream",
        "sweet": "sweet caramel jaggery honey toffee",
        "crunchy": "crunch crunchy crumble brittle crisp",
        "adventurous": "bold unusual cardamom saffron basil chili rose",
    }
    terms = []
    for trait, words in mapping.items():
        if int(st.session_state.taste.get(trait, 0)) >= 2:
            terms.append(words)
    return terms



def _explicit_avoid_labels(text: str) -> set[str]:
    low = (text or "").lower()
    avoid = set()
    patterns = {
        "Nuts": r"\b(no|without|avoid|allergic to|allergy to|hate)\b[^.?!]{0,30}\b(nut|nuts|pistachio|almond|cashew|hazelnut|pecan)\b",
        "Milk": r"\b(no|without|avoid|allergic to|allergy to|dairy[- ]?free|milk[- ]?free)\b[^.?!]{0,30}\b(milk|dairy|cream)\b|\b(dairy[- ]?free|milk[- ]?free)\b",
        "Soy": r"\b(no|without|avoid|allergic to|allergy to)\b[^.?!]{0,30}\bsoy\b",
        "Gluten": r"\b(no|without|avoid|allergic to|allergy to|gluten[- ]?free)\b[^.?!]{0,30}\b(gluten|wheat)\b|\bgluten[- ]?free\b",
        "Oats": r"\b(no|without|avoid|allergic to|allergy to)\b[^.?!]{0,30}\boats?\b",
    }
    for label, pattern in patterns.items():
        if re.search(pattern, low):
            avoid.add(label)
    return avoid

def _effective_preference_pool(text: str) -> list[dict]:
    """Return a broad, catalog-grounded pool instead of lexical top hits."""
    low = text.lower()
    pool = list(PRODUCTS)
    explicit_category = None
    if re.search(r"\bice[- ]?cream cakes?\b|\bcakes?\b", low):
        explicit_category = "Ice Cream Cake"
    elif re.search(r"\bice[- ]?cream\b", low):
        explicit_category = "Ice Cream"
    elif re.search(r"\b(chocolates?|chocolate bars?|cocoa bars?|dark chocolate)\b", low):
        explicit_category = "Frost Chocolates"
    elif re.search(r"\btoppings?\b|add[- ]?ons?\b", low):
        explicit_category = "Toppings"
    if explicit_category:
        pool = [p for p in pool if p["Category"] == explicit_category]

    budget = _budget_from_text(text)
    if budget is not None:
        pool = [p for p in pool if int(p["Price"]) <= budget]

    avoid = set(st.session_state.taste_avoid) | _explicit_avoid_labels(text)
    if avoid:
        pool = [p for p in pool if not (set(p["Allergens"]) & avoid)]

    # Natural-language preference matching over the full relevant catalog.
    requested = taste_from_text(text)
    merged = merge_taste(st.session_state.taste, requested)
    # A broad profile should influence ranking, but explicit query words get a
    # stronger weight through the lexical candidate score below.
    from src.taste import query_match_score
    scored = []
    for p in pool:
        profile_score = query_match_score(text, p)
        preference_score = match_score_for_product(merged, p)
        scored.append((profile_score * 2.0 + preference_score, p))
    scored.sort(key=lambda x: (-x[0], x[1]["Product"]))
    return [p for _, p in scored]


def match_score_for_product(profile: dict, product: dict) -> int:
    from src.taste import match_score
    return match_score(profile, product)


def _contextual_query(text: str) -> str:
    """Resolve common conversational references without throwing away new constraints."""
    raw = re.sub(r"\s+", " ", (text or "").strip())
    low = raw.lower()
    previous = st.session_state.get("last_user_request", "").strip()
    if not previous:
        return raw

    # "same thing as above, but cheaper" should preserve both the old request
    # and the new modifier instead of replacing the whole message.
    reference = re.search(r"\b(same thing|same one|same as above|repeat that|repeat the above|repeat it|again)\b", low)
    if reference:
        suffix = (raw[:reference.start()] + " " + raw[reference.end():]).strip(" ,.-")
        return f"{previous} {suffix}".strip() if suffix else previous

    # Resolve ordinal/product references against the last displayed result set.
    ordinal = re.search(r"\b(the\s+)?(first|1st|second|2nd|third|3rd|fourth|4th)\s+(one|option|choice|item)\b", low)
    codes = st.session_state.get("last_result_codes") or []
    if ordinal and codes:
        index = {"first":0,"1st":0,"second":1,"2nd":1,"third":2,"3rd":2,"fourth":3,"4th":3}[ordinal.group(2)]
        if index < len(codes):
            product = product_by_code(codes[index])
            if product:
                suffix = (raw[:ordinal.start()] + " " + raw[ordinal.end():]).strip(" ,.-")
                return f"{product['Product']} {suffix}".strip() if suffix else product['Product']

    if re.search(r"\b(that|that one|those|those options|the above|from above)\b", low) and codes:
        names = [product_by_code(c)["Product"] for c in codes[:6] if product_by_code(c)]
        if names:
            return f"Products previously shown: {', '.join(names)}. Customer follow-up: {raw}"
    return raw


def _comparison_answer(text: str) -> str | None:
    low = text.lower()
    wants_max = bool(re.search(r"\b(costliest|priciest|most expensive|highest priced|highest price|maximum price|most costly)\b", low))
    wants_min = bool(re.search(r"\b(cheapest|least expensive|lowest priced|lowest price|minimum price|least costly)\b", low))
    if not (wants_max or wants_min):
        return None

    # If the user is referring to the immediately preceding options, compare
    # exactly those options. This fixes "which is the costliest of those?".
    explicit_category = bool(re.search(r"\b(ice[- ]?cream cakes?|cakes?|ice[- ]?cream|chocolates?|chocolate bars?|dark chocolate|toppings?)\b", low))
    referential = bool(re.search(r"\b(these|those|the options|options above|above|from above|same)\b", low))
    previous_codes = st.session_state.get("last_result_codes") or []
    pool = [product_by_code(c) for c in previous_codes] if referential and not explicit_category else []
    pool = [p for p in pool if p]
    if not pool:
        pool = _effective_preference_pool(text)
        # Keep a meaningful preference shortlist rather than comparing all 80
        # products when the user says "with my preferences".
        if "preference" in low or "my taste" in low or "my likes" in low:
            pool = pool[:18]

    if not pool:
        return "I couldn't find any catalog items that match those preferences."
    chosen = max(pool, key=lambda p: int(p["Price"])) if wants_max else min(pool, key=lambda p: int(p["Price"]))
    direction = "most expensive" if wants_max else "least expensive"
    return f"The {direction} match is **{chosen['Product']}** at **{money(chosen['Price'])}**."


def _fact_answer(text: str) -> str | None:
    """Answer objective catalog questions deterministically before the LLM."""
    low = text.lower().strip()
    comparison = _comparison_answer(text)
    if comparison:
        return comparison

    # Product-specific facts are always answered from the catalog.
    ps = products_mentioned(text, limit=1)
    if ps:
        p = ps[0]
        if re.search(r"\b(price|cost|how much|₹|rupee|rupees)\b", low):
            return f"**{p['Product']}** is {money(p['Price'])} for {p['Serving']} g."
        if re.search(r"\b(ingredient|ingredients|contains|made of)\b", low):
            allergens = ", ".join(p["Allergens"]) if p["Allergens"] else "None flagged"
            return f"**{p['Product']}** contains {p['Ingredients']}. Catalog-flagged allergens: {allergens}."
        if re.search(r"\b(allergen|allergy|allergic)\b", low):
            return f"For **{p['Product']}**, the catalog flags: {', '.join(p['Allergens']) if p['Allergens'] else 'None flagged'}."
        if re.search(r"\b(calories|kcal|nutrition|fat|protein)\b", low):
            return f"**{p['Product']}**: {p['kcal']} kcal, {p['Fat']} g fat, {p['Protein']} g protein per {p['Serving']} g."

    # Category counts are also deterministic and avoid unnecessary LLM calls.
    if re.search(r"\bhow many\b", low):
        counts = {c: sum(p["Category"] == c for p in PRODUCTS) for c in CATEGORIES}
        if "ice cream cake" in low or "cakes" in low:
            return f"FROST has **{counts['Ice Cream Cake']} ice-cream cakes**."
        if "ice cream" in low:
            return f"FROST has **{counts['Ice Cream']} ice creams**."
        if "chocolate" in low:
            return f"FROST has **{counts['Frost Chocolates']} chocolates**."
        if "topping" in low:
            return f"FROST has **{counts['Toppings']} toppings**."
    return None

def _set_answer_products(products: list[dict] | None):
    """Store the exact products rendered with the current assistant answer.

    This is deliberately separate from last_result_codes (conversation context).
    A previous answer must never leak its cards into a new assistant message.
    """
    codes = [p["Code"] for p in (products or []) if p and p.get("Code")]
    st.session_state.last_answer_codes = codes
    st.session_state.last_result_codes = codes
    return codes


def _plan_context(plan) -> str:
    if not plan.products:
        return f"ANSWER PLAN: {plan.text or 'No product recommendation is required.'}"
    rows = "\n".join(
        f"- {p['Code']} | {p['Product']} | {p['Category']} | ₹{p['Price']} | {p['Serving']} g"
        for p in plan.products
    )
    return (
        f"ANSWER PLAN: {plan.text}\n"
        f"EXACT DISPLAY PRODUCTS (the UI will display only these, in this order):\n{rows}\n"
        "Do not name or recommend any other product."
    )


def answer_prompt(text: str) -> str:
    previous_request = st.session_state.get("last_user_request", "").strip()
    previous_codes = st.session_state.get("last_result_codes") or []
    previous_products = [product_by_code(c) for c in previous_codes]
    previous_products = [p for p in previous_products if p]

    # Resolve conversational references while preserving the newest modifier.
    contextual = _contextual_query(text)

    # Complete a pending quantity only when the next message identifies a product.
    pending = st.session_state.get("pending_order")
    if pending and not explicit_order_intent(contextual):
        pending_product = resolve_product(contextual)
        if pending_product:
            qty = int(pending.get("qty", 1))
            add_to_cart(pending_product, qty)
            st.session_state.pending_order = None
            _set_answer_products([pending_product])
            return f"Added **{pending_product['Product']} × {qty}** to your cart — {money(pending_product['Price'] * qty)}."

    order = handle_order(contextual)
    if order:
        # handle_order sets last_selected; show that exact item only if one was resolved.
        selected = st.session_state.get("last_selected")
        _set_answer_products([selected] if selected else [])
        return order

    # Update persistent taste/avoid state from the user's actual message.
    delta = taste_from_text(text)
    explicit_avoid = _explicit_avoid_labels(text)
    if any(delta.values()):
        st.session_state.taste = merge_taste(st.session_state.taste, delta)
    if explicit_avoid:
        st.session_state.taste_avoid |= explicit_avoid
    # Explicit flavor exclusions override previously learned positive taste weights.
    for trait in negative_taste_from_text(text):
        if trait in st.session_state.taste:
            st.session_state.taste[trait] = 0
    if (any(delta.values()) or explicit_avoid) and st.session_state.customer.get("user_id"):
        save_profile(st.session_state.customer["user_id"], st.session_state.taste, st.session_state.taste_avoid)

    # Catalog planner is the source of truth for category, constraints, comparisons,
    # negative preferences, and exact products. The LLM is only the conversational layer.
    plan = build_gelato_plan(
        contextual,
        PRODUCTS,
        profile=st.session_state.taste,
        previous_products=previous_products,
        previous_request=previous_request,
    )

    if plan.kind in {"comparison", "inventory", "fact"}:
        _set_answer_products(plan.products)
        return plan.text

    local = local_answer(text)
    if local:
        _set_answer_products([])
        return local

    # For recommendations, use the deterministic plan as hard grounding. For normal
    # conversation, candidates are empty so Gelato cannot hallucinate a product card.
    candidates = plan.products[:3]
    pdf = retrieve_pdf(contextual, limit=3)
    if api_ready():
        try:
            taste = ", ".join(f"{k}:{v}/5" for k, v in st.session_state.taste.items() if v)
            reply = validate_reply(
                ask_gemini(
                    contextual,
                    catalog_context(candidates),
                    cart_context(),
                    st.session_state.messages[:-1][-10:],
                    pdf,
                    customer_name(),
                    taste,
                    _plan_context(plan),
                ),
                candidates,
            )
            if reply:
                _set_answer_products(candidates)
                return reply
        except Exception:
            pass

    if plan.kind == "recommendation":
        _set_answer_products(candidates)
        return plan.text

    _set_answer_products([])
    return "Tell me what you're in the mood for, and I'll help you choose."


def process_message(text: str):
    text = (text or "").strip()
    if not text:
        return
    st.session_state.messages.append({"role": "user", "content": text})
    answer = answer_prompt(text)
    # Only the products explicitly selected for THIS answer may be rendered.
    # Never fall back to stale last_result_codes or parse arbitrary product names
    # from the assistant prose.
    codes = list(st.session_state.get("last_answer_codes") or [])
    st.session_state.messages.append({"role": "assistant", "content": answer, "products": codes[:6]})
    st.session_state.last_user_request = text


def go(view: str):
    if view not in VIEWS:
        view = "home"
    st.session_state.view = view
    st.session_state.scroll_top = True
    st.rerun()


def scroll_to_top():
    if st.session_state.pop("scroll_top", False):
        components.html("<script>window.parent.scrollTo({top:0,left:0,behavior:'instant'});</script>", height=1)


def render_header():
    st.markdown('<div class="nav-wrap">', unsafe_allow_html=True)
    left, nav = st.columns([2.2, 3.8], vertical_alignment="center")
    with left:
        st.markdown('<div class="logo">FROST</div><div class="tagline">cold moments · brighter days</div>', unsafe_allow_html=True)
    with nav:
        a, b, c, d, e = st.columns(5, gap="small")
        buttons = [
            (a, "Home", "home"),
            (b, "Gelato", "chat"),
            (c, "Shop", "shop"),
            (d, f"Cart · {cart_count(st.session_state.cart)}", "cart"),
            (e, "Account", "account"),
        ]
        for col, label, target in buttons:
            with col:
                if st.button(label, key=f"nav_{target}", use_container_width=True, type="primary" if st.session_state.view == target else "secondary"):
                    go(target)
    st.markdown('</div>', unsafe_allow_html=True)


def render_profile(profile):
    rows = "".join(
        f'<div class="profile-row"><span>{label}</span><div class="track"><div class="fill" style="width:{v*20}%"></div></div><b>{v}</b></div>'
        for label, v in profile_summary(profile)
    )
    st.markdown(f'<div class="profile"><h3>Your flavor profile</h3><p>These preferences shape Gelato recommendations.</p>{rows}</div>', unsafe_allow_html=True)


@st.dialog("FROST · Product details")
def show_product_details(product: dict):
    if product.get("Image"):
        st.image(product["Image"], use_container_width=True)
    st.markdown(f"### {product['Product']}")
    st.markdown(f"**{money(product['Price'])}** · {product['Serving']} g")
    st.markdown("**Ingredients**")
    st.write(product["Ingredients"])
    st.markdown("**Allergens**")
    st.write(", ".join(product["Allergens"]) if product["Allergens"] else "No catalog-flagged allergens")
    st.caption(f"{product['kcal']} kcal · Fat {product['Fat']} g · Protein {product['Protein']} g")


def render_product_card(product: dict, score: int | None, key_prefix: str):
    with st.container(border=True):
        if product.get("Image"):
            st.image(product["Image"], use_container_width=True)
        st.markdown(f'<div class="product-name">{product["Product"]}</div>', unsafe_allow_html=True)
        st.caption(f'{product["Serving"]} g · {CATEGORY_LABELS[product["Category"]].title()}')
        st.markdown(f'<div class="price">{money(product["Price"])}</div>', unsafe_allow_html=True)
        if score is not None:
            st.markdown(f'<span class="match">{score}% match</span>', unsafe_allow_html=True)
        c1, c2 = st.columns(2, gap="small")
        with c1:
            if st.button("Add to cart", key=f"add_{key_prefix}_{product['Code']}", use_container_width=True, type="primary"):
                add_to_cart(product, 1); st.toast(f"Added {product['Product']}")
        with c2:
            if st.button("Order now", key=f"order_{key_prefix}_{product['Code']}", use_container_width=True):
                order_now(product)
        d1, d2 = st.columns(2, gap="small")
        with d1:
            if st.button("Details", key=f"details_{key_prefix}_{product['Code']}", use_container_width=True):
                show_product_details(product)
        with d2:
            fav_label = "Saved" if product["Code"] in st.session_state.favorites else "Save"
            if st.button(fav_label, key=f"fav_{key_prefix}_{product['Code']}", use_container_width=True):
                toggle_favorite(product); st.rerun()


def render_product_cards(items, key_prefix="rec"):
    if not items:
        st.info("I couldn't find a suitable match with those filters. Try widening the budget or removing an avoid preference.")
        return
    cols = st.columns(min(3, len(items)), gap="medium")
    for i, (product, score) in enumerate(items):
        with cols[i % len(cols)]:
            render_product_card(product, score, f"{key_prefix}_{i}")


def flavor_profile_view():
    st.markdown('<div class="kicker">Your taste</div><div class="section-title">Find your flavor.</div><div class="section-note">One simple place to set preferences and get personal matches.</div>', unsafe_allow_html=True)
    left, right = st.columns([1.1, 0.9], gap="large")
    with left:
        current_choices = [k.title() for k, v in st.session_state.taste.items() if v and k != "adventurous"]
        current_choices += ["Adventurous"] if st.session_state.taste.get("adventurous", 0) else []
        with st.form("flavor_profile_form"):
            choices = st.multiselect("What do you enjoy?", ["Chocolate", "Fruity", "Creamy", "Sweet", "Nutty", "Crunchy", "Adventurous"], default=current_choices)
            sweetness = st.slider("Sweetness", 0, 5, int(st.session_state.taste.get("sweet", 2)))
            creaminess = st.slider("Creaminess", 0, 5, int(st.session_state.taste.get("creamy", 2)))
            avoid = st.multiselect("Anything to avoid?", ["Nuts", "Milk", "Soy", "Gluten", "Oats"], default=sorted(st.session_state.taste_avoid))
            saved = st.form_submit_button("Save preferences", type="primary", use_container_width=True)
        if saved:
            new = dict(DEFAULT_TASTE)
            for item in choices:
                key = item.lower()
                if key in new:
                    new[key] = 3
            new["sweet"] = sweetness
            new["creamy"] = creaminess
            st.session_state.taste = new
            st.session_state.taste_avoid = set(avoid)
            if st.session_state.customer.get("user_id"):
                save_profile(st.session_state.customer["user_id"], st.session_state.taste, st.session_state.taste_avoid)
            st.session_state.recommend_offset += 1
            st.toast("Your flavor profile is saved")
    with right:
        render_profile(st.session_state.taste)
    pool = [p for p in PRODUCTS if not (set(p["Allergens"]) & set(st.session_state.taste_avoid))]
    recs = recommend_products(st.session_state.taste, pool, 3, offset=st.session_state.recommend_seed + st.session_state.recommend_offset)
    st.markdown("### Your current matches")
    render_product_cards(recs, "profile")


def _occasion_changed():
    selected = st.session_state.get("occasion_selector", "Birthday")
    if selected != st.session_state.get("occasion"):
        st.session_state.occasion = selected
        st.session_state.recommend_offset += 1


def gift_view():
    st.markdown('<div class="kicker">Occasion</div><div class="section-title">Find something for the moment.</div><div class="section-note">Your occasion and budget directly change the recommendation ranking.</div>', unsafe_allow_html=True)
    occasion_options = ["Birthday", "Anniversary", "Celebration", "Thank you", "Family time", "Just because"]
    a, b = st.columns(2)
    with a:
        st.radio(
            "What is it for?",
            occasion_options,
            key="occasion_selector",
            horizontal=True,
            on_change=_occasion_changed,
        )
        occasion = st.session_state.occasion_selector
    with b:
        budget = st.slider("Budget", 300, 3000, int(st.session_state.gift_budget), step=100, key="occasion_budget")
    if budget != st.session_state.gift_budget:
        st.session_state.gift_budget = budget
        st.session_state.recommend_offset += 1
    pool = [p for p in PRODUCTS if p["Price"] <= budget and not (set(p["Allergens"]) & set(st.session_state.taste_avoid))]
    recs = recommend_products(st.session_state.taste, pool, 3, occasion=occasion, budget=budget, offset=st.session_state.recommend_seed + st.session_state.recommend_offset)
    st.markdown(f"### Picks for {occasion}")
    render_product_cards(recs, "occasion")
    if st.button("Show different options", use_container_width=True):
        st.session_state.recommend_offset += 1
        st.rerun()


def surprise_view():
    st.markdown('<div class="kicker">Discovery</div><div class="section-title">Let Gelato choose.</div><div class="section-note">Fresh options from the FROST catalog, shaped by your preferences.</div>', unsafe_allow_html=True)
    pool = [p for p in PRODUCTS if not (set(p["Allergens"]) & set(st.session_state.taste_avoid))]
    recs = recommend_products(st.session_state.taste, pool, 3, offset=st.session_state.recommend_seed + st.session_state.recommend_offset)
    render_product_cards(recs, "surprise")
    if st.button("Show me something else", type="primary", use_container_width=True):
        st.session_state.recommend_offset += 1
        st.rerun()


def render_chat():
    st.markdown('<div class="kicker">Your personal shop host</div><div class="chat-intro">Talk to Gelato.</div><div class="chat-sub">Say what you want in your own words. Gelato will handle the shopping details.</div>', unsafe_allow_html=True)
    for idx, message in enumerate(st.session_state.messages[-20:]):
        avatar = str(GELATO_AVATAR if message["role"] == "assistant" else USER_AVATAR)
        with st.chat_message(message["role"], avatar=avatar):
            st.markdown(message["content"])
            codes = message.get("products", [])
            products = [product_by_code(code) for code in codes]
            products = [p for p in products if p]
            if products:
                cols = st.columns(min(3, len(products)), gap="small")
                for j, product in enumerate(products[:3]):
                    with cols[j]:
                        if product.get("Image"):
                            st.image(product["Image"], width=130)
                        st.markdown(f'**{product["Product"]}**')
                        st.caption(money(product["Price"]))
                        if st.button("Add", key=f"chat_add_{idx}_{j}_{product['Code']}", use_container_width=True, type="primary"):
                            add_to_cart(product, 1); st.toast(f"Added {product['Product']}")
                        if st.button("Order", key=f"chat_order_{idx}_{j}_{product['Code']}", use_container_width=True):
                            order_now(product)
    q1, q2, q3 = st.columns(3)
    quick = [(q1, "I'm in the mood for chocolate", "I want something rich and chocolatey"), (q2, "Something under ₹500", "Find me something under ₹500"), (q3, "Surprise me", "Surprise me")]
    for col, label, text in quick:
        with col:
            if st.button(label, key=f"quick_{label}", use_container_width=True):
                process_message(text); st.rerun()
    prompt = st.chat_input("Tell Gelato what you're craving…")
    if prompt:
        process_message(prompt); st.rerun()


def render_cart():
    st.markdown('<div class="kicker">Your order</div><div class="section-title">Your cart.</div><div class="section-note">Review quantities before checkout.</div>', unsafe_allow_html=True)
    if not st.session_state.cart:
        st.markdown('<div class="panel empty">Your cart is empty.</div>', unsafe_allow_html=True)
        if st.button("Browse the collection", type="primary"): go("shop")
        return
    for item in list(st.session_state.cart):
        with st.container(border=True):
            a, b, c, d = st.columns([1.1, 4.0, 1.2, 1.2], vertical_alignment="center")
            with a:
                if item.get("Image"):
                    st.image(item["Image"], width=105)
            with b:
                st.markdown(f'**{item["Product"]}**')
                st.caption(f'{item["Category"]} · {money(item["Price"])} each · Line total {money(item["Price"] * item["qty"])}')
            with c:
                qty = st.number_input("Qty", 1, 20, int(item["qty"]), key=f"cart_qty_{item['Code']}")
                if qty != item["qty"]:
                    set_qty(st.session_state.cart, item["Code"], qty); st.rerun()
            with d:
                if st.button("Remove", key=f"cart_remove_{item['Code']}", use_container_width=True):
                    st.session_state.cart = remove_item(st.session_state.cart, item["Code"]); st.rerun()
    st.divider()
    st.markdown(f'<div class="checkout-total">Total · {money(cart_total(st.session_state.cart))}</div>', unsafe_allow_html=True)
    if st.button("Continue to checkout", type="primary", use_container_width=True): go("checkout")


def render_checkout():
    st.markdown('<div class="kicker">Checkout</div><div class="section-title">Complete your order.</div><div class="section-note">A clear final review before your order is placed.</div>', unsafe_allow_html=True)
    if not st.session_state.cart:
        st.info("Your cart is empty.")
        if st.button("Back to shop", type="primary"): go("shop")
        return
    for item in st.session_state.cart:
        st.write(f'**{item["qty"]} × {item["Product"]}** · {money(item["Price"] * item["qty"])}')
    st.divider(); st.markdown(f'<div class="checkout-total">Total · {money(cart_total(st.session_state.cart))}</div>', unsafe_allow_html=True)
    name = st.text_input("Name", value=customer_name() if customer_name() != "Guest" else "", key="checkout_name")
    email = st.text_input("Email (optional)", value=st.session_state.customer.get("email", ""), key="checkout_email")
    payment = st.radio("Payment method", ["UPI", "Card", "Cash on Delivery"], horizontal=True, key="checkout_payment")
    if st.button("Place order", type="primary", use_container_width=True):
        if not name.strip():
            st.error("Please enter your name.")
            return
        if email.strip() and not validate_email(email.strip()):
            st.error("Please enter a valid email or leave it blank.")
            return
        snapshot = [dict(x) for x in st.session_state.cart]
        order_no = f"FROST-{uuid.uuid4().hex[:8].upper()}"
        st.session_state.customer.update({"name": name.strip(), "email": email.strip().lower()})
        order_record = {"order_number": order_no, "items": snapshot, "total": cart_total(snapshot), "payment": payment, "status": "Placed"}
        st.session_state.orders.insert(0, order_record)
        save_order(st.session_state.customer.get("user_id"), order_no, snapshot, cart_total(snapshot), payment)
        st.session_state.checkout_snapshot = snapshot
        st.session_state.order_number = order_no
        st.session_state.checkout_complete = True
        st.session_state.cart = []
        st.session_state.view = "confirmation"
        st.session_state.scroll_top = True
        st.rerun()


def render_account():
    st.markdown('<div class="kicker">My FROST</div><div class="section-title">Your account.</div><div class="section-note">Your profile, favorites and orders in one private space.</div>', unsafe_allow_html=True)
    if not st.session_state.customer.get("signed_in"):
        a, b = st.columns(2, gap="large")
        with a:
            with st.form("signin_form"):
                st.markdown("### Sign in")
                email = st.text_input("Email", autocomplete="email")
                password = st.text_input("Password", type="password", autocomplete="current-password")
                submit = st.form_submit_button("Sign in", type="primary", use_container_width=True)
            if submit:
                user = authenticate(email, password) if validate_email(email) and password else None
                if not user:
                    st.error("We couldn't sign you in with those details.")
                else:
                    taste, avoid = load_profile(user["id"])
                    st.session_state.customer = {"signed_in": True, "user_id": user["id"], "name": user["name"], "email": user["email"]}
                    st.session_state.taste.update(taste)
                    st.session_state.taste_avoid = avoid
                    st.session_state.favorites = get_favorites(user["id"])
                    st.session_state.orders = get_orders(user["id"])
                    st.rerun()
        with b:
            with st.form("create_form"):
                st.markdown("### Create account")
                name = st.text_input("Name", autocomplete="name")
                email2 = st.text_input("Email", autocomplete="email")
                password2 = st.text_input("Password", type="password", autocomplete="new-password")
                submit2 = st.form_submit_button("Create account", type="primary", use_container_width=True)
            if submit2:
                if not name.strip() or not validate_email(email2) or len(password2) < 8:
                    st.error("Use your name, a valid email, and a password of at least 8 characters.")
                elif create_user(name, email2, password2) is None:
                    st.error("An account with that email already exists.")
                else:
                    user = authenticate(email2, password2)
                    st.session_state.customer = {"signed_in": True, "user_id": user["id"], "name": user["name"], "email": user["email"]}
                    st.session_state.favorites = set()
                    st.session_state.orders = []
                    st.rerun()
        return
    st.success(f"Welcome back, {customer_name()}.")
    a, b = st.columns([1, 1], gap="large")
    with a:
        new_name = st.text_input("Name", value=customer_name(), key="profile_name")
        if st.button("Save name", use_container_width=True):
            if new_name.strip():
                update_name(st.session_state.customer["user_id"], new_name)
                st.session_state.customer["name"] = new_name.strip(); st.rerun()
        st.write(f'**Email:** {st.session_state.customer["email"]}')
    with b:
        render_profile(st.session_state.taste)
        if st.button("Edit flavor preferences", use_container_width=True):
            go("flavor")
    st.markdown("### Favorites")
    favorites = [product_by_code(code) for code in st.session_state.favorites]
    favorites = [p for p in favorites if p]
    if favorites:
        render_product_cards([(p, 100) for p in favorites], "fav")
    else:
        st.caption("No favorites yet. Save products while browsing.")
    st.markdown("### Orders")
    if not st.session_state.orders:
        st.caption("No orders yet.")
    for order in st.session_state.orders:
        with st.expander(f'{order["order_number"]} · {money(order["total"])} · {order["status"]}'):
            for item in order["items"]:
                st.write(f'{item["qty"]} × {item["Product"]} · {money(item["Price"] * item["qty"])}')
            st.caption(f'Payment: {order["payment"]} · {order.get("created_at", "")}')
    if st.button("Sign out", use_container_width=True):
        st.session_state.customer = {"signed_in": False, "user_id": None, "name": "", "email": ""}
        st.session_state.favorites = set(); st.session_state.orders = []; st.rerun()


def render_shop():
    st.markdown('<div class="kicker">The collection</div><div class="section-title">Choose your indulgence.</div><div class="section-note">80 original FROST creations.</div>', unsafe_allow_html=True)
    tabs = st.tabs([CATEGORY_LABELS[c].title() for c in CATEGORIES])
    for tab, category in zip(tabs, CATEGORIES):
        with tab:
            products = category_products(category)
            for start in range(0, len(products), 3):
                cols = st.columns(3, gap="medium")
                for col, product in zip(cols, products[start:start+3]):
                    with col:
                        render_product_card(product, None, f"shop_{category}_{start}")


def render_confirmation():
    snapshot = st.session_state.checkout_snapshot
    st.markdown(f'<div class="kicker">Order confirmed</div><div class="section-title">Thank you, {customer_name()}.</div><div class="section-note">Your FROST order has been recorded.</div>', unsafe_allow_html=True)
    st.success(f'Order {st.session_state.order_number} placed.')
    for item in snapshot:
        st.write(f'**{item["qty"]} × {item["Product"]}** · {money(item["Price"] * item["qty"])}')
    st.markdown(f'<div class="checkout-total">Total · {money(sum(i["Price"] * i["qty"] for i in snapshot))}</div>', unsafe_allow_html=True)
    st.download_button("Download receipt", invoice_pdf(snapshot, st.session_state.order_number), f'{st.session_state.order_number}.pdf', "application/pdf", use_container_width=True)
    if st.button("Continue shopping", type="primary", use_container_width=True): go("shop")


render_header()
scroll_to_top()

if st.session_state.view == "home":
    rail, main = st.columns([0.28, 0.72], gap="large")
    with rail:
        st.markdown('<div class="rail-title">Gelato atelier</div><div class="rail-copy">A quiet little corner for exploring the FROST collection before you choose your indulgence.</div>', unsafe_allow_html=True)
        if GELATO_VIDEO.exists():
            st.markdown('<div class="video-shell">', unsafe_allow_html=True)
            st.video(str(GELATO_VIDEO), format="video/mp4", start_time=0)
            st.markdown('</div>', unsafe_allow_html=True)
        st.markdown('<div class="rail-rule"></div><div class="rail-stat"><span></span>80 products · 4 collections</div>', unsafe_allow_html=True)
        st.markdown('<div class="quick-label">Quick ideas</div>', unsafe_allow_html=True)
        quick = [("Chocolate picks", "Find me something rich and chocolatey"), ("Something fruity", "I want something fruity and refreshing"), ("Nut-free", "Show me something without nuts"), ("Under ₹500", "Find me something under ₹500")]
        for i, (label, text) in enumerate(quick):
            if st.button(label, key=f"rail_quick_{i}", use_container_width=True):
                st.session_state.messages.append({"role":"user", "content":text})
                answer = answer_prompt(text)
                mentioned = products_mentioned(answer, limit=3)
                st.session_state.messages.append({"role":"assistant", "content":answer, "products":[p["Code"] for p in mentioned]})
                go("chat")
    with main:
        render_slideshow(HEROES)
        st.markdown('<div class="stats"><span class="stat">30 ice creams</span><span class="stat">10 ice-cream cakes</span><span class="stat">15 chocolates</span><span class="stat">25 toppings</span></div>', unsafe_allow_html=True)
        st.markdown('<div class="kicker">FROST intelligence</div><div class="section-title">More than a menu.</div><div class="section-note">Gelato learns what you like, then turns it into a better way to shop.</div>', unsafe_allow_html=True)
        choices = [
            ("Find your flavor", "Set a few preferences and get personal matches.", "flavor"),
            ("Build a gift", "Match an occasion and budget to the collection.", "gift"),
            ("Surprise me", "Let Gelato choose something worth discovering.", "surprise"),
            ("Find a match", "Describe a craving and get the closest catalog match.", "chat"),
            ("Discover something new", "Explore the full FROST collection.", "shop"),
        ]
        cols = st.columns(5, gap="small")
        for col, (title, copy, target) in zip(cols, choices):
            with col:
                st.markdown(f'<div class="discovery-card"><div class="discovery-title">{title}</div><div class="discovery-copy">{copy}</div></div>', unsafe_allow_html=True)
                if st.button("Explore", key=f"home_{target}", use_container_width=True):
                    go(target)
        st.markdown("<div class='gelato-panel'><div class='kicker'>Your FROST shop host</div><div class='gelato-title'>Talk to Gelato.</div><div class='gelato-copy'>Tell Gelato what you're in the mood for, what you're celebrating, or simply what sounds good.</div></div>", unsafe_allow_html=True)
        if st.button("Open Gelato", type="primary", use_container_width=True):
            go("chat")

elif st.session_state.view == "chat":
    render_chat()
elif st.session_state.view == "flavor":
    flavor_profile_view()
elif st.session_state.view == "gift":
    gift_view()
elif st.session_state.view == "surprise":
    surprise_view()
elif st.session_state.view == "shop":
    render_shop()
elif st.session_state.view == "cart":
    render_cart()
elif st.session_state.view == "checkout":
    render_checkout()
elif st.session_state.view == "account":
    render_account()
elif st.session_state.view == "confirmation":
    render_confirmation()

st.markdown('<div class="footer">FROST · COLD MOMENTS · BRIGHTER DAYS</div>', unsafe_allow_html=True)
