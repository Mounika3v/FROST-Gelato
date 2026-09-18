from __future__ import annotations

from pathlib import Path
import re
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "frost_catalog.csv"
PRODUCT_DIR = ROOT / "assets" / "products"

CATEGORIES = ["Ice Cream", "Ice Cream Cake", "Frost Chocolates", "Toppings"]
CATEGORY_LABELS = {
    "Ice Cream": "ICE CREAM",
    "Ice Cream Cake": "ICE-CREAM CAKES",
    "Frost Chocolates": "FROST CHOCOLATES",
    "Toppings": "TOPPINGS",
}
ALIASES = {
    "ice cream cake": "Ice Cream Cake", "icecream cake": "Ice Cream Cake", "cakes": "Ice Cream Cake", "cake": "Ice Cream Cake",
    "ice cream": "Ice Cream", "icecream": "Ice Cream", "flavors": "Ice Cream", "flavours": "Ice Cream", "flavour": "Ice Cream", "flavor": "Ice Cream",
    "frost chocolates": "Frost Chocolates", "chocolates": "Frost Chocolates", "chocolate": "Frost Chocolates", "bars": "Frost Chocolates", "bar": "Frost Chocolates",
    "toppings": "Toppings", "topping": "Toppings", "add ons": "Toppings", "add-ons": "Toppings", "add on": "Toppings", "addon": "Toppings",
}
STOP_WORDS = set("the a an i me my want need please show give tell about what which with and or for to of is are can you do serve have your menu item items price prices cost total order now add get some one two three four five six seven eight nine ten scoops scoop".split())

# Small query-expansion layer for natural language. It improves retrieval without
# making another model/API call.
QUERY_ALIASES = {
    "chocolatey": "chocolate", "chocolaty": "chocolate", "cocoa": "chocolate",
    "creamy": "cream", "dessert": "sweet", "refreshing": "fruit",
    "fruity": "fruit", "berry": "berries", "berries": "berry",
    "nutty": "nuts", "allergy": "allergen", "allergic": "allergen",
    "vegan": "plant", "crunchy": "crunch", "celebration": "cake",
}



def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower().replace("&", " and ")).strip()


def load_catalog() -> pd.DataFrame:
    df = pd.read_csv(DATA_PATH).fillna("-")
    for col in ["Price", "Serving", "kcal", "Fat", "Protein", "Sugar", "Added"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    return df


CATALOG = load_catalog()


def detect_allergens(row: dict) -> list[str]:
    return [label for col, label in [("Milk", "Milk"), ("Nuts", "Nuts"), ("Soy", "Soy"), ("Gluten", "Gluten"), ("Oats", "Oats")] if str(row.get(col, "-")).strip().upper() == "X"]


def product_image(code: str) -> Path | None:
    hits = sorted(PRODUCT_DIR.glob(f"{code}_*"))
    return hits[0] if hits else None


def row_to_dict(row) -> dict:
    d = row.to_dict() if hasattr(row, "to_dict") else dict(row)
    for col in ["Price", "Serving", "kcal", "Fat", "Protein", "Sugar", "Added"]:
        if col in d:
            d[col] = int(d[col])
    d["Allergens"] = detect_allergens(d)
    img = product_image(d["Code"])
    d["Image"] = str(img) if img else ""
    return d


def all_products() -> list[dict]:
    return [row_to_dict(r) for _, r in CATALOG.iterrows()]


def category_from_text(text: str) -> str | None:
    n = normalize(text)
    for alias, category in sorted(ALIASES.items(), key=lambda x: len(normalize(x[0])), reverse=True):
        if re.search(rf"\b{re.escape(normalize(alias))}\b", n):
            return category
    return None


def category_products(category: str) -> list[dict]:
    if category not in CATEGORIES:
        return []
    return [row_to_dict(r) for _, r in CATALOG[CATALOG["Category"] == category].iterrows()]


def _score(query: str, row: dict) -> int:
    q = normalize(query)
    if not q:
        return 0
    name = normalize(row["Product"])
    code = normalize(row["Code"])
    searchable = " ".join(
        normalize(row.get(field, ""))
        for field in ("Product", "Code", "Category", "Ingredients")
    )
    if name == q:
        return 10000
    if code == q:
        return 9500
    expanded = []
    for token in q.split():
        if token in STOP_WORDS or len(token) < 3:
            continue
        expanded.append(token)
        alias = QUERY_ALIASES.get(token)
        if alias:
            expanded.extend(alias.split())
    tokens = list(dict.fromkeys(expanded))
    if len(q) >= 3 and name in q:
        return 9000
    if len(q) >= 3 and q in name:
        return 8000 - len(name) + len(q)
    name_words = set(name.split())
    search_words = set(searchable.split())
    name_overlap = len(name_words & set(tokens))
    broad_overlap = len(search_words & set(tokens))
    if broad_overlap:
        return 100 * name_overlap + 35 * broad_overlap + 12 * sum(t in searchable for t in tokens)
    return 0


def search_catalog(query: str, category: str | None = None, limit: int = 12) -> list[dict]:
    category = category or category_from_text(query)
    rows = CATALOG if not category else CATALOG[CATALOG["Category"] == category]
    products = [row_to_dict(r) for _, r in rows.iterrows()]
    scored = sorted(((p, _score(query, p)) for p in products), key=lambda x: (x[1], x[0]["Product"]), reverse=True)
    hits = [p for p, score in scored if score > 0]
    if hits:
        return hits[:limit]
    return products[:limit] if category else []


def products_mentioned(text: str, limit: int = 12) -> list[dict]:
    n = normalize(text)
    products = all_products()
    exact = [p for p in sorted(products, key=lambda x: len(normalize(x["Product"])), reverse=True)
             if re.search(rf"\b{re.escape(normalize(p['Product']))}\b", n)]
    return exact[:limit]


def catalog_context(products: list[dict]) -> str:
    return "\n".join(
        f"{p['Code']} | {p['Product']} | {p['Category']} | ₹{p['Price']} | {p['Serving']} g | Ingredients: {p['Ingredients']} | Flagged allergens: {', '.join(p['Allergens']) if p['Allergens'] else 'None flagged'} | Nutrition: {p.get('kcal',0)} kcal, fat {p.get('Fat',0)} g, protein {p.get('Protein',0)} g"
        for p in products
    )
