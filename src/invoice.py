from __future__ import annotations

from datetime import datetime
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from src.order import cart_total, money


def invoice_pdf(cart: list[dict], order_number: str) -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    left, right = 22 * mm, width - 22 * mm
    espresso = (0.13, 0.08, 0.05)
    gold = (0.67, 0.45, 0.14)
    cream = (0.98, 0.96, 0.91)
    muted = (0.40, 0.35, 0.30)

    c.setFillColorRGB(*cream); c.rect(0, 0, width, height, fill=1, stroke=0)
    c.setFillColorRGB(*espresso); c.rect(0, height - 48 * mm, width, 48 * mm, fill=1, stroke=0)
    c.setFillColorRGB(0.90, 0.70, 0.34); c.setFont("Helvetica-Bold", 25); c.drawString(left, height - 19 * mm, "FROST")
    c.setFillColorRGB(1, 0.97, 0.91); c.setFont("Helvetica", 8.5); c.drawString(left, height - 27 * mm, "GELATO · COLD MOMENTS · BRIGHTER DAYS")
    c.setFont("Helvetica-Bold", 13); c.drawRightString(right, height - 18 * mm, "ORDER RECEIPT")
    c.setFont("Helvetica", 8.5); c.drawRightString(right, height - 26 * mm, order_number)
    c.drawRightString(right, height - 32 * mm, datetime.now().strftime("%d %b %Y · %I:%M %p"))

    y = height - 64 * mm
    c.setFillColorRGB(*gold); c.setFont("Helvetica-Bold", 8); c.drawString(left, y, "YOUR FROST ORDER")
    y -= 8 * mm
    c.setFillColorRGB(*espresso); c.setFont("Helvetica-Bold", 10)
    c.drawString(left, y, "ITEM"); c.drawRightString(right - 38 * mm, y, "QTY"); c.drawRightString(right, y, "AMOUNT")
    y -= 5 * mm; c.setStrokeColorRGB(0.82, 0.75, 0.65); c.line(left, y, right, y); y -= 8 * mm

    for item in cart:
        if y < 45 * mm:
            c.showPage(); y = height - 25 * mm
        c.setFillColorRGB(*espresso); c.setFont("Helvetica-Bold", 10); c.drawString(left, y, item["Product"][:48])
        c.setFillColorRGB(*muted); c.setFont("Helvetica", 8); c.drawString(left, y - 5 * mm, f"{item['Category']} · {money(item['Price'])} each")
        c.setFillColorRGB(*espresso); c.setFont("Helvetica-Bold", 10); c.drawRightString(right - 38 * mm, y, str(item["qty"])); c.drawRightString(right, y, money(item["Price"] * item["qty"]))
        y -= 16 * mm

    c.setStrokeColorRGB(0.82, 0.75, 0.65); c.line(left, y + 4 * mm, right, y + 4 * mm); y -= 3 * mm
    c.setFillColorRGB(*espresso); c.setFont("Helvetica-Bold", 15); c.drawString(left, y, "TOTAL")
    c.setFillColorRGB(*gold); c.drawRightString(right, y, money(cart_total(cart)))
    y -= 20 * mm
    c.setFillColorRGB(*espresso); c.setFont("Helvetica-Bold", 10); c.drawString(left, y, "Thank you for choosing FROST.")
    c.setFillColorRGB(*muted); c.setFont("Helvetica", 8.5); c.drawString(left, y - 6 * mm, "Prepared by Gelato · FROST shop host")
    c.setFillColorRGB(*gold); c.rect(left, 18 * mm, right - left, 1.2 * mm, fill=1, stroke=0)
    c.setFillColorRGB(*muted); c.setFont("Helvetica", 7.5); c.drawCentredString(width / 2, 12 * mm, "FROST · PREMIUM GELATO · ORDER RECEIPT")
    c.save(); return buf.getvalue()
