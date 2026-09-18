# FROST Gelato QA Report — LLM Rebuild

## What changed

Gelato's shopping logic was rebuilt around a catalog-first answer planner. The Gemini model is now the conversational/natural-language layer, while application logic owns facts, categories, constraints, comparisons, references, and the exact products rendered in the UI.

### Hard correctness rules
- Category filters are applied before ranking.
- Negative flavor constraints are hard exclusions.
- Allergen exclusions are hard exclusions.
- Cheapest/costliest questions are deterministic catalog comparisons.
- Inventory/category questions are answered from the exact category.
- Follow-ups can resolve ordinals and prior product references.
- Relative modifiers such as `same thing but cheaper` preserve the earlier request.
- The UI receives product codes from the current answer only; stale cards cannot leak into a new message.
- LLM responses are validated against the exact candidate set and catalog prices.
- If the LLM fails validation, the application returns the deterministic grounded answer instead of a fabricated response.

## Tested failure cases

1. `I need the costliest ice cream that you have`
   - Returns an Ice Cream product only.
   - Current catalog result: Moonlit Cocoa Swirl — ₹229.

2. `what flavours do you have in toppings`
   - Returns the Toppings collection only.
   - No chocolate/ice-cream cards are attached.

3. `i dont want chocolate flavour`
   - Chocolate/cocoa/cacao products are excluded from recommendations.

4. `find me something creamy and mild sweetness and with dark chocolate`
   - Multiple constraints are scored together.
   - Mild sweetness uses catalog sugar values rather than a generic keyword match.

5. `same thing but cheaper`
   - Preserves the earlier request and applies a lower-price constraint.

6. `how much is the second one?`
   - Resolves the second product from the previous displayed result set and answers from the catalog.

7. `why everything in store so expensive`
   - Treated as a natural conversational/pricing question rather than forced into a recommendation prompt.

## Automated verification

- Catalog: 80/80 products valid.
- Categories: 30 Ice Cream / 10 Ice Cream Cake / 15 Frost Chocolates / 25 Toppings.
- Tests: 26/26 passing.
- Python compilation: passing.

## Remaining verification

The final verification that cannot be proven by offline tests is the live Gemini/browser smoke test with the configured API key. The intended behavior is that Gemini cannot change the application-selected products; it can only phrase the grounded answer naturally.
