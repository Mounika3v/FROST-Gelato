from __future__ import annotations
import re


def money(value: float | int) -> str:
    return f"₹{float(value):,.0f}"


def add_item(cart: list[dict], product: dict, qty: int = 1) -> list[dict]:
    qty = max(1, min(20, int(qty)))
    for item in cart:
        if item["Code"] == product["Code"]:
            item["qty"] = min(20, item["qty"] + qty)
            return cart
    cart.append({**product, "qty": qty})
    return cart


def remove_item(cart: list[dict], code: str) -> list[dict]:
    return [i for i in cart if i["Code"] != code]


def set_qty(cart: list[dict], code: str, qty: int) -> list[dict]:
    qty = max(1, min(20, int(qty)))
    for item in cart:
        if item["Code"] == code:
            item["qty"] = qty
            break
    return cart


def cart_total(cart: list[dict]) -> int:
    return int(sum(i["Price"] * i["qty"] for i in cart))


def cart_count(cart: list[dict]) -> int:
    return int(sum(i["qty"] for i in cart))

NUMBER_WORDS = {"one":1,"two":2,"three":3,"four":4,"five":5,"six":6,"seven":7,"eight":8,"nine":9,"ten":10,"eleven":11,"twelve":12,"thirteen":13,"fourteen":14,"fifteen":15,"sixteen":16,"seventeen":17,"eighteen":18,"nineteen":19,"twenty":20}


def parse_quantity(text: str, default: int = 1) -> int:
    low = str(text or "").lower().strip()
    # Never interpret percentages such as 55% as quantities.
    patterns = [r"\b(?:x|×|qty|quantity)\s*(\d{1,2})\b", r"\b(\d{1,2})\s*(?:x|units?|pieces?|pcs?|servings?|scoops?)\b", r"\b(\d{1,2})\s+of\b"]
    for pat in patterns:
        m = re.search(pat, low)
        if m and 1 <= int(m.group(1)) <= 20:
            return int(m.group(1))
    m = re.search(r"\b(?:order|buy|purchase|take|get|want|add|put|make it|give me)\s+(?:only\s+|just\s+)?(\d{1,2})\b", low)
    if m and 1 <= int(m.group(1)) <= 20:
        return int(m.group(1))
    for word, value in NUMBER_WORDS.items():
        if re.search(rf"\b(?:order|buy|purchase|take|get|want|add|put|make it|give me)\s+(?:only\s+|just\s+)?{word}\b", low):
            return value
    return default


def bill_text(cart: list[dict], customer_name: str = "Guest", order_number: str = "") -> str:
    lines = ["FROST — ORDER SUMMARY", f"Customer — {customer_name}", f"Order — {order_number}", ""]
    for i in cart:
        lines.append(f"{i['qty']} × {i['Product']} ({i['Code']}) — {money(i['Price'] * i['qty'])}")
    lines += ["", f"Total — {money(cart_total(cart))}", "", "Prepared by Gelato · FROST"]
    return "\n".join(lines)
