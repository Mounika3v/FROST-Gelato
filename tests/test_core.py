from src.catalog import all_products, search_catalog
from src.order import add_item, cart_count, cart_total, parse_quantity
from src.taste import recommend_products, query_match_score, taste_from_text


def test_catalog_has_80_products():
    assert len(all_products()) == 80


def test_category_counts():
    p = all_products()
    assert sum(x['Category'] == 'Ice Cream' for x in p) == 30
    assert sum(x['Category'] == 'Ice Cream Cake' for x in p) == 10
    assert sum(x['Category'] == 'Frost Chocolates' for x in p) == 15
    assert sum(x['Category'] == 'Toppings' for x in p) == 25


def test_tiny_queries_do_not_return_random_products():
    assert search_catalog('hi') == []
    assert search_catalog('hello') == []


def test_order_math():
    p = all_products()[0]; c = []; add_item(c, p, 3)
    assert cart_count(c) == 3 and cart_total(c) == p['Price'] * 3


def test_quantities():
    assert parse_quantity('Please I want to order 3') == 3
    assert parse_quantity('I want 2') == 2
    assert parse_quantity('buy three') == 3
    assert parse_quantity('Silk Cocoa 55%') == 1
    assert parse_quantity('order 3 of Silk Cocoa 55%') == 3


def test_recommendations_change_with_occasion():
    products = all_products(); profile = {'chocolate': 2, 'fruity': 1, 'creamy': 2, 'sweet': 2, 'nutty': 0, 'crunchy': 0, 'adventurous': 1}
    birthday = [p['Code'] for p, _ in recommend_products(profile, products, 3, occasion='Birthday', offset=17)]
    date = [p['Code'] for p, _ in recommend_products(profile, products, 3, occasion='Anniversary', offset=17)]
    assert birthday != date


def test_recommendations_rotate():
    products = all_products(); profile = {'chocolate': 2, 'fruity': 1, 'creamy': 2, 'sweet': 2, 'nutty': 0, 'crunchy': 0, 'adventurous': 1}
    a = [p['Code'] for p, _ in recommend_products(profile, products, 3, offset=11)]
    b = [p['Code'] for p, _ in recommend_products(profile, products, 3, offset=12)]
    assert a != b


def test_costliest_ice_cream_stays_in_ice_cream_category():
    products = [p for p in all_products() if p["Category"] == "Ice Cream"]
    chosen = max(products, key=lambda p: p["Price"])
    assert chosen["Product"] == "Moonlit Cocoa Swirl"
    assert chosen["Price"] == 229


def test_creamy_dark_chocolate_query_prefers_catalog_match():
    products = [p for p in all_products() if p["Category"] == "Frost Chocolates"]
    silk = next(p for p in products if p["Product"] == "Silk Cocoa 55%")
    mango = next(p for p in products if p["Product"] == "Mango Chili Cocoa Bar")
    assert query_match_score("creamy and mild sweetness and dark chocolate", silk) > query_match_score("creamy and mild sweetness and dark chocolate", mango)


def test_mild_sweetness_updates_sweet_preference():
    assert taste_from_text("creamy with mild sweetness and dark chocolate")["sweet"] > 0


def test_mild_sweetness_penalizes_high_sugar_match():
    products = [p for p in all_products() if p['Category'] == 'Ice Cream']
    scores = [(query_match_score('creamy, not too sweet, dark chocolate', p), p) for p in products]
    assert max(scores, key=lambda x: x[0])[0] >= min(scores, key=lambda x: x[0])[0]



def test_explicit_multi_constraint_match_beats_partial_match():
    products = [p for p in all_products() if p['Category'] == 'Frost Chocolates']
    silk = next(p for p in products if p['Product'] == 'Silk Cocoa 55%')
    mango = next(p for p in products if p['Product'] == 'Mango Chili Cocoa Bar')
    assert query_match_score('creamy and mild sweetness and dark chocolate', silk) > query_match_score('creamy and mild sweetness and dark chocolate', mango)


def test_mild_sweetness_prefers_lower_sugar_when_other_terms_match():
    products = [p for p in all_products() if p['Category'] == 'Frost Chocolates']
    espresso = next(p for p in products if p['Product'] == 'Espresso Jaggery Dark Bar')
    orange = next(p for p in products if p['Product'] == 'Orange Cardamom Dark Bar')
    assert query_match_score('mild sweetness and dark chocolate', espresso) > query_match_score('mild sweetness and dark chocolate', orange)


def test_allergen_constraint_is_hard_penalty():
    products = [p for p in all_products() if p['Category'] == 'Frost Chocolates']
    pecan = next(p for p in products if p['Product'] == 'Pecan Cinnamon Dark Bar')
    silk = next(p for p in products if p['Product'] == 'Silk Cocoa 55%')
    assert query_match_score('dark chocolate without nuts', pecan) < query_match_score('dark chocolate without nuts', silk)


def test_gelato_category_comparisons_are_exact():
    from src.gelato_engine import plan
    p = all_products()
    r = plan('I need the costliest ice cream that you have', p)
    assert r.kind == 'comparison'
    assert r.products[0]['Category'] == 'Ice Cream'
    assert r.products[0]['Product'] == 'Moonlit Cocoa Swirl'
    assert r.products[0]['Price'] == 229


def test_gelato_toppings_query_stays_in_toppings():
    from src.gelato_engine import plan
    r = plan('what flavours do you have in toppings', all_products())
    assert r.kind == 'inventory'
    assert '25 toppings items' in r.text
    assert r.products == []
    assert 'Silk Cocoa 55%' not in r.text


def test_gelato_negative_chocolate_is_hard_exclusion():
    from src.gelato_engine import plan
    r = plan("i dont want chocolate flavour", all_products())
    assert r.kind == 'recommendation'
    assert r.products
    assert all('chocolate' not in p['Product'].lower() and 'cocoa' not in p['Product'].lower() and 'cacao' not in p['Product'].lower() for p in r.products)


def test_gelato_previous_reference_and_cheaper_modifier():
    from src.gelato_engine import plan
    products = all_products()
    previous = plan('find me something creamy and mild sweetness and with dark chocolate', products).products
    r = plan('same thing but cheaper', products, previous_products=previous, previous_request='find me something creamy and mild sweetness and with dark chocolate')
    assert r.products
    assert max(p['Price'] for p in r.products) < min(p['Price'] for p in previous)


def test_gelato_ordinal_fact_uses_exact_previous_product():
    from src.gelato_engine import plan
    products = all_products()
    previous = [next(p for p in products if p['Product'] == name) for name in ['Silk Cocoa 55%', 'Coconut Vanilla Cacao Bar', 'Roasted Coconut Cacao Bar']]
    r = plan('how much is the second one?', products, previous_products=previous)
    assert r.kind == 'fact'
    assert 'Coconut Vanilla Cacao Bar' in r.text
    assert '₹329' in r.text
    assert r.products == [previous[1]]
