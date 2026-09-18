from src.catalog import CATEGORIES, all_products, category_products

products = all_products()
assert len(products) == 80, len(products)
assert sum(len(category_products(c)) for c in CATEGORIES) == 80
for c in CATEGORIES:
    assert category_products(c), c
print("FROST catalog valid: 80 products / 4 categories")
