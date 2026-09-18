# FROST Gelato — Submission Build

This build preserves the premium FROST storefront direction: Gelato shop video, editorial hero slideshow, premium typography, discovery experiences, separate Cart and Account views, catalog-grounded shopping assistant, and non-disruptive product details.

## Before running
1. Create/activate a virtual environment.
2. Install `requirements.txt`.
3. Copy `.env.example` to `.env`.
4. Put your Gemini API key in `.env` as `GEMINI_API_KEY=...`.
5. Never commit `.env`.

## Run
`streamlit run app.py`

## Validation performed
- Catalog: 80 products (30 ice creams, 10 ice-cream cakes, 15 chocolates, 25 toppings)
- Automated tests: 13 passed
- Python compilation: passed
- API key is read from environment only
- Microphone/voice UI is not included

## Competition note
The package has been code-tested, but a final live browser walkthrough on the competition laptop should still be performed before submission.
