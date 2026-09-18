from __future__ import annotations
from pathlib import Path
import base64
import html
import streamlit as st


def _data_uri(path: Path) -> str:
    if not path.exists():
        return ""
    suffix = path.suffix.lower()
    mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}.get(suffix, "image/jpeg")
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def inject_css() -> None:
    st.markdown('''
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Playfair+Display:ital,wght@0,500;0,600;1,500&display=swap');
:root{--ink:#24180f;--muted:#766657;--cream:#fbf6ec;--paper:#fffdf9;--line:#e4d8c8;--gold:#a96f1f;--gold-dark:#805014}
html,body,[class*="css"]{font-family:'DM Sans',sans-serif;color:var(--ink)}
.stApp{background:linear-gradient(180deg,#fcf8ef 0%,#fffdf9 44%,#fbf6ec 100%)}
.block-container{max-width:1460px;padding:18px 28px 54px}
header[data-testid="stHeader"]{background:transparent}
.logo{font:4.4rem/.78 'Playfair Display',Georgia,serif;letter-spacing:-.055em;color:#684319}.tagline{font-size:.58rem;letter-spacing:.25em;text-transform:uppercase;color:#8c7865;margin-top:9px}
.nav-wrap{border-bottom:1px solid rgba(132,101,67,.18);padding-bottom:14px;margin-bottom:18px}
.stButton>button{border-radius:10px!important;min-height:42px!important;border:1px solid #d8c7b2!important;font-weight:600!important;background:rgba(255,252,247,.92)!important;color:#3b2819!important;box-shadow:none!important;transition:all .15s ease}.stButton>button:hover{transform:translateY(-1px);border-color:#b8905d!important}.stButton>button[kind="primary"],button[kind="primary"]{background:linear-gradient(135deg,#b87c29,#925b16)!important;color:#fff!important;border-color:#925b16!important}
/* Home editorial rail */
.rail{border-right:1px solid rgba(132,101,67,.18);padding-right:22px;min-height:100%}.rail-title{font-size:.64rem;letter-spacing:.22em;text-transform:uppercase;color:#8c7865;font-weight:700;margin:4px 0 8px}.rail-copy{color:#766657;font-size:.82rem;line-height:1.55;margin-bottom:14px}.rail-rule{height:1px;background:#cdbda9;margin:18px 0}.rail-stat{font-size:.72rem;color:#6e5a46;margin:9px 0}.rail-stat span{display:inline-block;width:7px;height:7px;border-radius:50%;background:#7fb78c;margin-right:8px}
.video-shell{border-radius:14px;overflow:hidden;border:1px solid #d9c7b2;background:#efe5d7;box-shadow:0 14px 30px rgba(63,39,18,.08);margin:8px 0 16px}
.quick-label{font-size:.62rem;letter-spacing:.2em;text-transform:uppercase;color:#8c7865;font-weight:700;margin:2px 0 9px}.quick-button{margin-bottom:9px}
/* Editorial hero slideshow */
.slideshow{position:relative;height:410px;border-radius:28px;overflow:hidden;background:#24150d;box-shadow:0 22px 54px rgba(55,32,14,.13)}
.slide{position:absolute;inset:0;background-position:center;background-size:cover;opacity:0;animation:frostSlide 24s infinite}.slide:nth-child(1){animation-delay:0s}.slide:nth-child(2){animation-delay:6s}.slide:nth-child(3){animation-delay:12s}.slide:nth-child(4){animation-delay:18s}
.slide:after{content:"";position:absolute;inset:0;background:linear-gradient(90deg,rgba(19,9,4,.83),rgba(20,10,5,.30) 62%,rgba(20,10,5,.06))}
.slide-copy{position:absolute;z-index:2;left:48px;bottom:43px;max-width:700px;color:#fff8ee}.slide-eyebrow{font-size:.62rem;letter-spacing:.24em;text-transform:uppercase;color:#d3a05a;font-weight:700}.slide-title{font:clamp(3.1rem,5.5vw,5.7rem)/.9 'Playfair Display',Georgia,serif;margin:10px 0 14px;letter-spacing:-.035em}.slide-copy p{font-size:.94rem;line-height:1.55;color:#f7eadb;margin:0;max-width:620px}.slide-name{position:absolute;right:34px;bottom:30px;z-index:3;color:rgba(255,248,238,.78);font:italic 1rem 'Playfair Display',Georgia,serif}
@keyframes frostSlide{0%,22%{opacity:1}25%,100%{opacity:0}}
.stats{display:flex;flex-wrap:wrap;gap:8px;margin:11px 0 30px}.stat{padding:8px 13px;border:1px solid var(--line);background:#fff8ef;border-radius:999px;font-size:.7rem;color:#6e5a46}
.kicker{font-size:.61rem;letter-spacing:.23em;text-transform:uppercase;color:#9a6a2d;font-weight:700}.section-title{font:3.05rem/.98 'Playfair Display',Georgia,serif;margin:5px 0 7px;color:#2b1a10;letter-spacing:-.025em}.section-note{color:var(--muted);font-size:.88rem;margin-bottom:18px}
.discovery-card{min-height:145px;border:1px solid #e2d4c2;border-radius:18px;background:rgba(255,253,249,.74);padding:18px 16px 14px;box-shadow:0 8px 22px rgba(63,39,18,.035)}.discovery-title{font:1.28rem/1.08 'Playfair Display',Georgia,serif;margin-bottom:8px}.discovery-copy{color:var(--muted);font-size:.77rem;line-height:1.48;min-height:42px}.discovery-card .stButton{margin-top:8px}
.gelato-panel{margin-top:24px;border:1px solid #ddcdb8;border-radius:23px;background:linear-gradient(135deg,#fff9ed,#f8ecd6);padding:22px 24px;box-shadow:0 12px 34px rgba(63,39,18,.055)}.gelato-title{font:2.6rem/1 'Playfair Display',Georgia,serif}.gelato-copy{color:var(--muted);font-size:.88rem;margin-top:7px}
.chat-intro{font:2.7rem/1 'Playfair Display',Georgia,serif}.chat-sub{color:var(--muted);font-size:.9rem;margin:7px 0 16px}.chat-panel{background:#fffaf3;border:1px solid var(--line);border-radius:22px;padding:16px}div[data-testid="stChatMessage"]{border:1px solid #e3d5c3!important;border-radius:17px!important;background:#fffdf9!important;box-shadow:none!important}div[data-testid="stChatMessage"] p{line-height:1.55!important}
.product-card{border:1px solid #e2d6c6;border-radius:18px;background:rgba(255,253,249,.82);padding:12px;box-shadow:0 10px 28px rgba(63,39,18,.045)}.product-name{font:1.24rem/1.08 'Playfair Display',Georgia,serif;margin:8px 0 4px}.price{font-weight:800;font-size:1.02rem;color:var(--gold-dark);margin:7px 0}.match{display:inline-block;font-size:.64rem;padding:5px 8px;border:1px solid #ddc18f;background:#fbf1df;border-radius:999px;color:#7b551b;font-weight:700}.detail-caption{font-size:.72rem;color:#8a7766}
.profile{background:linear-gradient(135deg,#2b1a10,#402616);color:#fff8ef;border-radius:20px;padding:21px}.profile h3{font:1.9rem/1 'Playfair Display',Georgia,serif;margin:0}.profile p{color:#e5d0ae;font-size:.8rem}.profile-row{display:grid;grid-template-columns:90px 1fr 22px;gap:10px;align-items:center;margin:9px 0;font-size:.72rem}.track{height:7px;background:#65462b;border-radius:999px;overflow:hidden}.fill{height:100%;background:#d7a04c;border-radius:999px}
.checkout-total{font:2rem 'Playfair Display',Georgia,serif}.empty{text-align:center;padding:45px 20px;color:var(--muted)}.footer{text-align:center;color:#927e67;font-size:.6rem;letter-spacing:.22em;margin-top:42px}
@media(max-width:1050px){.block-container{padding:12px 16px 40px}.logo{font-size:3.7rem}.slideshow{height:350px}.slide-copy{left:30px;bottom:30px}.slide-title{font-size:3.4rem}.section-title{font-size:2.55rem}.rail{border-right:0;padding-right:0;margin-bottom:20px}}
@media(max-width:700px){.slideshow{height:310px;border-radius:20px}.slide-title{font-size:2.8rem}.slide-copy{left:22px;bottom:24px}.slide-copy p{font-size:.8rem}.slide-name{display:none}}
</style>''', unsafe_allow_html=True)


def render_slideshow(images: list[tuple[Path, str]]) -> None:
    slides = []
    for path, name in images:
        uri = _data_uri(path)
        if not uri:
            continue
        safe_name = html.escape(name)
        slides.append(f'''<div class="slide" style="background-image:url('{uri}')"><div class="slide-copy"><div class="slide-eyebrow">Premium gelato · FROST</div><div class="slide-title">Indulge in<br><em>Happiness</em></div><p>Crafted for cold moments, brighter days, and the little decisions that deserve something delicious.</p></div><div class="slide-name">{safe_name}</div></div>''')
    if slides:
        st.markdown('<section class="slideshow">' + ''.join(slides) + '</section>', unsafe_allow_html=True)
