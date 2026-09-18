from __future__ import annotations
import os
from pathlib import Path
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=True)

# Stable, current Flash model for the competition build. The fallback chain keeps
# the assistant usable if a model endpoint is temporarily unavailable.
DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
FALLBACK_MODELS = ("gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash")

SYSTEM_PROMPT = """You are Gelato, the personal shopping host for FROST, a fictional premium gelato store.

Conversation rules:
- Speak like a warm, natural human shopping assistant. Never sound like a command-line bot.
- Respond to the customer's actual message first. If they are sad, excited, unsure, or casual, acknowledge that naturally.
- Never dump example prompts or tell the customer to use commands.
- Keep replies concise and useful: normally 1-4 short paragraphs or a short list.

Truth rules:
- The supplied FROST catalog/PDF context is the source of truth for product names, categories, prices, ingredients, allergens and nutrition.
- Never invent a product, price, ingredient, allergen, availability claim or policy.
- If the supplied context does not contain the requested fact, say that you don't have that fact rather than guessing.
- Do not mention APIs, models, prompts, retrieval, quotas, keys, code, implementation details or other brands.

Shopping rules:
- The application controls cart changes. Never claim that an item was added, removed, ordered or paid for unless the application message/context confirms it.
- When recommending, use the supplied candidate products and explain the match briefly.
- Respect the customer's budget, allergies/avoid list, taste profile and occasion when those are supplied.
- If the customer asks a follow-up such as "the second one", "same thing", "that one", "make it two", or "the cheaper one", use the recent conversation context and previously shown products.
- Preserve the customer's newest modifier. For example, "same thing but cheaper" means the previous request plus a cheaper-price constraint; it does not reset the conversation.
- For comparative questions such as costliest, cheapest, highest priced or lowest priced, answer the comparison directly and do not turn it into a recommendation list.
- If a reference is genuinely ambiguous and no previous product/list can resolve it, ask one short clarification instead of inventing a referent.
- When an ANSWER PLAN is supplied, treat it as application-authoritative: preserve its facts and product order. Never substitute a different product, category, price, or answer to the user's question.
"""


def api_key() -> str:
    return (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()


def api_ready() -> bool:
    key = api_key()
    return len(key) > 20 and key.lower() not in {"your_api_key_here", "paste_your_key_here", "your_actual_gemini_api_key"}


def _extract(data: dict) -> str:
    return "\n".join(
        p.get("text", "")
        for c in data.get("candidates", [])
        for p in c.get("content", {}).get("parts", [])
        if p.get("text")
    ).strip()


def _request(model: str, prompt: str) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "maxOutputTokens": 300,
            "temperature": 0.45,
            "responseMimeType": "text/plain",
            "thinkingConfig": {"thinkingLevel": "low"},
        },
    }
    response = requests.post(
        url,
        json=payload,
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key()},
        timeout=(4, 18),
    )
    if response.status_code >= 400:
        try:
            message = str(response.json().get("error", {}).get("message", ""))
        except ValueError:
            message = ""
        raise RuntimeError(message or f"Gemini HTTP {response.status_code}")
    text = _extract(response.json())
    if not text:
        raise RuntimeError("Gemini returned no text")
    return text


def ask_gemini(
    user_text: str,
    catalog: str,
    cart: str,
    history: list[dict],
    pdf_context: str = "",
    customer_name: str = "Guest",
    taste_profile: str = "",
    answer_plan: str = "",
) -> str:
    if not api_ready():
        raise RuntimeError("Gemini is not configured")

    recent = "\n".join(
        f"{m.get('role', 'user').upper()}: {m.get('content', '')}"
        for m in history[-10:]
    )
    prompt = f"""CUSTOMER NAME: {customer_name}
TASTE PROFILE: {taste_profile or 'not established'}
CURRENT CART: {cart or 'empty'}

CATALOG CANDIDATES:
{catalog or 'none supplied'}

PDF/CATALOG SOURCE NOTES:
{pdf_context or 'none supplied'}

RECENT CONVERSATION:
{recent or 'none'}

LATEST CUSTOMER MESSAGE:
{user_text}

{answer_plan}

REFERENCE/CONTINUITY RULES:
- The recent conversation above is authoritative for references such as "same", "that", "the second one", "those options", "again", and "make it cheaper/two".
- The application may also provide candidates selected specifically for the latest request. Do not introduce products outside those candidates when recommending.
- Answer the newest question first; retain only the earlier context that is relevant to it.

Answer the latest message naturally. Use only the supplied product facts. If the customer is simply chatting, do not force a recommendation. If they want a recommendation, choose only from the supplied candidates and explain why they fit. If no supplied candidate actually satisfies the stated constraints, say so briefly rather than pretending a weak match is exact."""

    models = []
    for model in (DEFAULT_MODEL, *FALLBACK_MODELS):
        if model and model not in models:
            models.append(model)
    last_error = None
    for model in models:
        try:
            return _request(model, prompt)
        except RuntimeError as exc:
            last_error = exc
            # Keep trying a different model for endpoint/model availability errors.
            msg = str(exc).lower()
            if not any(x in msg for x in ("not found", "model", "unsupported", "deprecated")):
                break
    raise RuntimeError(str(last_error) if last_error else "Gemini unavailable")
