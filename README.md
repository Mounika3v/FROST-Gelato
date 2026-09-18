# FROST · Gelato — Premium Competition Build

FROST is a premium Streamlit storefront with Gelato as the conversational shopping assistant.

## What this build preserves

- The original editorial FROST visual direction.
- Automatic four-scene hero slideshow.
- Gelato atelier side rail with the original shop video.
- Quick-idea shortcuts.
- The "More than a menu" discovery experience.
- Premium serif/display typography, warm cream palette and spacious product presentation.
- Separate Cart and Account interfaces with direct navigation.

## What was corrected

- Removed only the broken Taste DNA feature; the rest of the discovery experience remains.
- Renamed discovery features with cleaner customer-facing titles.
- Product ingredients/allergens open in a dialog so the product grid does not jump or get pushed down.
- Cart and Account open as dedicated views.
- Order Now goes directly to checkout.
- Persistent accounts, profiles, favorites and orders are supported through SQLite locally and `FROST_DATABASE_URL` for a deployed database.
- Gelato has natural conversation, recent-chat context, catalog/PDF grounding, local intent handling, quantity parsing, budget/allergen filtering and validated catalog facts.
- Cart mutations are handled by application logic rather than trusting free-form LLM output.
- Microphone/voice functionality is not included.
- Customer-facing demo/prototype wording is removed.

## Catalog

Exactly 80 original FROST products:

- 30 ice creams
- 10 ice-cream cakes
- 15 chocolates
- 25 toppings

## Windows setup

```bat
cd /d "YOUR\\PATH\\FROST_PREMIUM_FINAL"
py -m venv .venv
call .venv\\Scripts\\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if not exist .env copy .env.example .env
python validate_catalog.py
pytest -q
python -m streamlit run app.py
```

Put the Gemini key only in `.env`:

```env
GEMINI_API_KEY=YOUR_KEY_HERE
GEMINI_MODEL=gemini-3.8-flash
```

Never commit `.env` to GitHub. `.gitignore` already excludes it.

## Deployment

For Streamlit deployment, put the Gemini key in Streamlit Secrets rather than the repository. For persistent production accounts/orders, configure `FROST_DATABASE_URL` to a managed PostgreSQL database.
