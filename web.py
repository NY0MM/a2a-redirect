import os
import html as _html
import json as _json
from datetime import datetime, timedelta
from flask import (Flask, redirect, request, jsonify, render_template_string,
                   make_response)

app = Flask(__name__)

AFFILIATE_TAG = os.environ.get("AFFILIATE_TAG", "")
API_SECRET = os.environ.get("API_SECRET", "")

# Marketplaces this redirector can send traffic to. Associates tracking IDs are
# per-locale: a UK tag on amazon.de earns nothing, so each market reads its own
# env var and falls back to an untagged link rather than the wrong tag.
MARKETPLACES = {"UK": "co.uk", "DE": "de", "FR": "fr", "IT": "it", "ES": "es"}


def tag_for(market: str) -> str:
    if market == "UK":
        return AFFILIATE_TAG
    return os.environ.get(f"AFFILIATE_TAG_{market}", "")


def amazon_url_for(market: str, asin: str) -> str:
    """Tagged product URL. th/psc pin the exact child variant."""
    params = (f"tag={tag_for(market)}&" if tag_for(market) else "") + "th=1&psc=1"
    return f"https://www.amazon.{MARKETPLACES[market]}/dp/{asin}?{params}"


def valid_asin(asin: str) -> bool:
    return bool(asin) and asin.isalnum() and len(asin) == 10

# In-memory deals store — newest first
deals = []

# Private-monitor hits, kept apart from the public feed so they never appear on
# the homepage or /deals. Rendered only at the bottom of /settings.
#
# NOTE: these entries deliberately carry NO member identity — no Discord ID, no
# name, nothing tying an ASIN to a person. This page is public (it has to be:
# every visitor gets the same HTML from Flask), so anything in here is readable
# by anyone who finds the URL. Keeping it to asin/price/time means that is a
# deals list rather than a disclosure of what individuals are tracking, which
# would also contradict the privacy policy this site publishes.
private_deals = []

def clean_old_deals():
    cutoff = datetime.utcnow() - timedelta(hours=24)
    global deals, private_deals
    deals = [d for d in deals if datetime.fromisoformat(d["timestamp"]) > cutoff]
    private_deals = [d for d in private_deals
                     if datetime.fromisoformat(d["timestamp"]) > cutoff]

def time_ago(iso_timestamp):
    diff = datetime.utcnow() - datetime.fromisoformat(iso_timestamp)
    minutes = int(diff.total_seconds() / 60)
    if minutes < 1:
        return "Just now"
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    return f"{hours // 24}d ago"


# ---------------------------------------------------------------------------
# Shared CSS + layout
# ---------------------------------------------------------------------------

SHARED_CSS = """
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: 'Inter', sans-serif; background: #f3f4f6; color: #111827; }

/* NAV */
header { background: #fff; border-bottom: 1px solid #e5e7eb; position: sticky; top: 0; z-index: 100; padding: 0 24px; }
.header-inner { max-width: 1200px; margin: 0 auto; height: 64px; display: flex; align-items: center; justify-content: space-between; }
.logo { font-size: 22px; font-weight: 800; color: #111827; text-decoration: none; }
.logo span { color: #f97316; }
nav { display: flex; gap: 28px; align-items: center; }
nav a { font-size: 14px; font-weight: 500; color: #374151; text-decoration: none; }
nav a:hover { color: #f97316; }
.nav-cta { background: #f97316; color: #fff !important; padding: 8px 18px; border-radius: 8px; font-weight: 700 !important; }
.nav-cta:hover { background: #ea6c0a !important; }

/* FOOTER */
footer { background: #111827; color: #6b7280; padding: 40px 24px; font-size: 13px; margin-top: 60px; }
.footer-inner { max-width: 1200px; margin: 0 auto; }
.footer-grid { display: grid; grid-template-columns: 2fr 1fr 1fr; gap: 40px; margin-bottom: 32px; }
.footer-brand p { color: #9ca3af; margin-top: 10px; line-height: 1.7; font-size: 13px; }
.footer-col h4 { color: #f9fafb; font-size: 14px; font-weight: 700; margin-bottom: 14px; }
.footer-col a { display: block; color: #9ca3af; text-decoration: none; margin-bottom: 8px; font-size: 13px; }
.footer-col a:hover { color: #f97316; }
.footer-bottom { border-top: 1px solid #374151; padding-top: 24px; color: #6b7280; font-size: 12px; line-height: 1.7; }
.footer-bottom a { color: #9ca3af; text-decoration: none; }

/* SHARED CONTAINERS */
.container { max-width: 1200px; margin: 0 auto; padding: 40px 24px; }
.page-hero { background: linear-gradient(135deg, #111827 0%, #1f2937 100%); color: #fff; padding: 56px 24px; text-align: center; }
.page-hero h1 { font-size: 36px; font-weight: 800; margin-bottom: 12px; }
.page-hero h1 span { color: #f97316; }
.page-hero p { font-size: 16px; color: #9ca3af; max-width: 600px; margin: 0 auto; }

/* ARTICLE */
.article { max-width: 780px; margin: 0 auto; }
.article h2 { font-size: 22px; font-weight: 700; margin: 32px 0 14px; color: #111827; }
.article h3 { font-size: 18px; font-weight: 600; margin: 24px 0 10px; color: #1f2937; }
.article p { font-size: 15px; line-height: 1.8; color: #374151; margin-bottom: 16px; }
.article ul, .article ol { padding-left: 24px; margin-bottom: 16px; }
.article li { font-size: 15px; line-height: 1.8; color: #374151; margin-bottom: 6px; }
.article .tip-box { background: #fff7ed; border-left: 4px solid #f97316; padding: 16px 20px; border-radius: 0 8px 8px 0; margin: 24px 0; }
.article .tip-box p { margin: 0; color: #92400e; font-weight: 500; }
.affiliate-notice { background: #f9fafb; border: 1px solid #e5e7eb; padding: 14px 18px; border-radius: 8px; font-size: 13px; color: #6b7280; margin-bottom: 32px; }

/* MARKETPLACE TABS */
.tabs { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 24px; }
.tab { padding: 8px 18px; border-radius: 999px; font-size: 14px; font-weight: 600; cursor: pointer; border: 2px solid #e5e7eb; background: #fff; color: #374151; transition: all 0.15s; user-select: none; }
.tab:hover { border-color: #f97316; color: #f97316; }
.tab.active { background: #f97316; border-color: #f97316; color: #fff; }

/* DEAL CARDS */
.section-title { font-size: 20px; font-weight: 700; margin-bottom: 20px; display: flex; align-items: center; gap: 10px; }
.section-title::after { content: ''; flex: 1; height: 1px; background: #e5e7eb; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 20px; }
.card { background: #fff; border-radius: 12px; overflow: hidden; border: 1px solid #e5e7eb; transition: transform 0.15s, box-shadow 0.15s; display: flex; flex-direction: column; }
.card:hover { transform: translateY(-4px); box-shadow: 0 12px 24px rgba(0,0,0,0.10); }
.card-img-wrap { position: relative; background: #fff; padding: 16px; display: flex; align-items: center; justify-content: center; height: 200px; border-bottom: 1px solid #f3f4f6; }
.card-img-wrap img { max-height: 168px; max-width: 100%; object-fit: contain; }
.badge { position: absolute; top: 10px; left: 10px; background: #ef4444; color: #fff; font-size: 13px; font-weight: 800; padding: 4px 10px; border-radius: 6px; }
.market-badge { position: absolute; top: 10px; right: 10px; font-size: 18px; line-height: 1; }
.card-body { padding: 14px; flex: 1; display: flex; flex-direction: column; }
.card-title { font-size: 13px; font-weight: 500; color: #374151; line-height: 1.4; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; margin-bottom: 12px; flex: 1; }
.price-row { margin-bottom: 12px; }
.price-now { font-size: 22px; font-weight: 800; color: #111827; }
.price-was { font-size: 13px; color: #9ca3af; text-decoration: line-through; margin-left: 6px; }
.price-save { font-size: 12px; color: #16a34a; font-weight: 600; margin-top: 2px; }
.card-footer { display: flex; align-items: center; justify-content: space-between; margin-top: 4px; }
.time-ago { font-size: 11px; color: #9ca3af; }
.btn-deal { background: #f97316; color: #fff; font-size: 13px; font-weight: 700; padding: 8px 16px; border-radius: 8px; text-decoration: none; transition: background 0.15s; white-space: nowrap; }
.btn-deal:hover { background: #ea6c0a; }
.empty { text-align: center; padding: 80px 24px; color: #9ca3af; }
.empty-icon { font-size: 48px; margin-bottom: 16px; }
.empty h2 { font-size: 20px; font-weight: 600; color: #6b7280; margin-bottom: 8px; }

/* GUIDES GRID */
.guides-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 24px; }
.guide-card { background: #fff; border-radius: 12px; border: 1px solid #e5e7eb; padding: 28px; text-decoration: none; color: inherit; transition: transform 0.15s, box-shadow 0.15s; display: flex; flex-direction: column; gap: 10px; }
.guide-card:hover { transform: translateY(-4px); box-shadow: 0 12px 24px rgba(0,0,0,0.10); }
.guide-tag { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; color: #f97316; }
.guide-card h3 { font-size: 17px; font-weight: 700; color: #111827; line-height: 1.4; }
.guide-card p { font-size: 14px; color: #6b7280; line-height: 1.6; }
.guide-read { font-size: 13px; font-weight: 600; color: #f97316; margin-top: auto; }

@media (max-width: 768px) {
    .footer-grid { grid-template-columns: 1fr; gap: 24px; }
    nav .hide-mobile { display: none; }
    .page-hero h1 { font-size: 26px; }
}
@media (max-width: 600px) {
    .grid { grid-template-columns: repeat(2, 1fr); gap: 12px; }
    .card-img-wrap { height: 150px; }
}
"""

def nav_html():
    return """
<header>
  <div class="header-inner">
    <a class="logo" href="/">Deal<span>Scout</span></a>
    <nav>
      <a href="/deals" class="hide-mobile">Live Deals</a>
      <a href="/guides" class="hide-mobile">Buying Guides</a>
      <a href="/about" class="hide-mobile">About</a>
      <a href="/deals" class="nav-cta">See Deals</a>
    </nav>
  </div>
</header>"""

def footer_html():
    return """
<footer>
  <div class="footer-inner">
    <div class="footer-grid">
      <div class="footer-brand">
        <a class="logo" href="/" style="color:#fff;font-size:20px;font-weight:800;text-decoration:none;">Deal<span style="color:#f97316;">Scout</span></a>
        <p>DealScout tracks Amazon UK prices around the clock and surfaces genuine savings so you never overpay. All prices are verified before being listed.</p>
      </div>
      <div class="footer-col">
        <h4>Explore</h4>
        <a href="/deals">Live Deals</a>
        <a href="/guides">Buying Guides</a>
        <a href="/guides/how-amazon-business-pricing-works">Amazon Business Pricing</a>
        <a href="/guides/how-to-save-money-on-amazon-uk">Money Saving Tips</a>
      </div>
      <div class="footer-col">
        <h4>Site</h4>
        <a href="/about">About Us</a>
        <a href="/contact">Contact</a>
        <a href="/privacy">Privacy Policy</a>
        <a href="/settings" rel="nofollow">Settings</a>
      </div>
    </div>
    <div class="footer-bottom">
      <p>As an Amazon Associate, DealScout earns from qualifying purchases. Product prices and availability are accurate as of the date/time indicated and are subject to change. Any price and availability information displayed on Amazon at the time of purchase will apply.</p>
      <p style="margin-top:10px;">&copy; 2025 DealScout &nbsp;|&nbsp; <a href="/privacy">Privacy Policy</a> &nbsp;|&nbsp; <a href="/contact">Contact</a></p>
    </div>
  </div>
</footer>"""

def base_head(title, description=""):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <meta name="description" content="{description}">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>{SHARED_CSS}</style>
</head>
<body>"""


# ---------------------------------------------------------------------------
# Homepage
# ---------------------------------------------------------------------------

HOMEPAGE = """{{ head }}
{{ nav }}

<div class="page-hero">
  <h1>The Best <span>Amazon UK</span> Deals Right Now</h1>
  <p>We scan Amazon UK prices continuously and surface real savings — updated automatically, all day long.</p>
</div>

<div class="container">

  <div class="affiliate-notice">
    ℹ️ <strong>Affiliate disclosure:</strong> As an Amazon Associate, DealScout earns a small commission from qualifying purchases at no extra cost to you. This helps us keep the service free.
  </div>

  {% if deals %}
  <div class="section-title">🔥 Live Deals</div>

  <div class="tabs" id="market-tabs">
    <div class="tab" data-market="all"  onclick="filterDeals('all', this)">All</div>
    <div class="tab" data-market="UK"   onclick="filterDeals('UK', this)">🇬🇧 UK</div>
    <div class="tab" data-market="DE"   onclick="filterDeals('DE', this)">🇩🇪 Germany</div>
    <div class="tab" data-market="FR"   onclick="filterDeals('FR', this)">🇫🇷 France</div>
    <div class="tab" data-market="IT"   onclick="filterDeals('IT', this)">🇮🇹 Italy</div>
    <div class="tab" data-market="ES"   onclick="filterDeals('ES', this)">🇪🇸 Spain</div>
  </div>

  <div class="grid" id="deals-grid">
    {% for deal in deals %}
    {% set source = deal.source if deal.source else 'UK' %}
    {% set flags = {'UK': '🇬🇧', 'DE': '🇩🇪', 'FR': '🇫🇷', 'IT': '🇮🇹', 'ES': '🇪🇸'} %}
    <div class="card" data-source="{{ source }}">
      <div class="card-img-wrap">
        <img src="{{ deal.image }}" alt="{{ deal.title }}" onerror="this.src='https://via.placeholder.com/200x200?text=No+Image'">
        {% if deal.discount_percent > 0 %}<div class="badge">-{{ deal.discount_percent }}%</div>{% endif %}
        <div class="market-badge" title="{{ source }}">{{ flags.get(source, '🛒') }}</div>
      </div>
      <div class="card-body">
        <div class="card-title">{{ deal.title }}</div>
        <div class="price-row">
          <span class="price-now">£{{ "%.2f"|format(deal.current_price) }}</span>
          {% if deal.was_price > deal.current_price %}
          <span class="price-was">£{{ "%.2f"|format(deal.was_price) }}</span>
          <div class="price-save">Save £{{ "%.2f"|format(deal.was_price - deal.current_price) }}</div>
          {% endif %}
        </div>
        <div class="card-footer">
          <span class="time-ago">{{ deal.time_ago }}</span>
          <a class="btn-deal" href="/deal/{{ deal.asin }}" target="_blank">View Deal →</a>
        </div>
      </div>
    </div>
    {% endfor %}
  </div>

  <div id="no-deals-msg" style="display:none;" class="empty">
    <div class="empty-icon">🔍</div>
    <h2>No deals in this marketplace yet</h2>
    <p>Check back shortly — deals are added automatically.</p>
  </div>

  <script>
  function filterDeals(source, el) {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    el.classList.add('active');
    var cards = document.querySelectorAll('#deals-grid .card');
    var visible = 0;
    cards.forEach(function(card) {
      var show = source === 'all' || card.dataset.source === source;
      card.style.display = show ? '' : 'none';
      if (show) visible++;
    });
    document.getElementById('no-deals-msg').style.display = visible === 0 ? 'block' : 'none';
    var url = new URL(window.location);
    if (source === 'all') { url.searchParams.delete('m'); } else { url.searchParams.set('m', source); }
    history.replaceState(null, '', url);
  }

  // On load: activate tab from URL param ?m=XX
  (function() {
    var param = new URL(window.location).searchParams.get('m') || 'all';
    var tab = document.querySelector('#market-tabs .tab[data-market="' + param + '"]') ||
              document.querySelector('#market-tabs .tab[data-market="all"]');
    if (tab) filterDeals(param, tab);
  })();
  </script>

  {% else %}
  <div class="empty">
    <div class="empty-icon">🔍</div>
    <h2>Scanning for deals...</h2>
    <p>Check back shortly — new deals are added automatically every few minutes.</p>
  </div>
  {% endif %}

  <div style="margin-top:60px;">
    <div class="section-title">📚 Buying Guides</div>
    <div class="guides-grid">
      <a class="guide-card" href="/guides/how-amazon-business-pricing-works">
        <div class="guide-tag">Explainer</div>
        <h3>How Amazon Business Pricing Works (And How to Use It)</h3>
        <p>Amazon Business accounts unlock lower prices on thousands of products. Here's everything you need to know.</p>
        <div class="guide-read">Read guide →</div>
      </a>
      <a class="guide-card" href="/guides/how-to-save-money-on-amazon-uk">
        <div class="guide-tag">Tips</div>
        <h3>10 Proven Ways to Save Money on Amazon UK</h3>
        <p>From Subscribe & Save to price tracking tools, these strategies consistently get you better prices.</p>
        <div class="guide-read">Read guide →</div>
      </a>
      <a class="guide-card" href="/guides/best-office-supplies-amazon-uk">
        <div class="guide-tag">Category Guide</div>
        <h3>Best Office Supplies to Buy on Amazon UK in 2025</h3>
        <p>A curated guide to the best-value office supplies on Amazon, from paper and ink to furniture and storage.</p>
        <div class="guide-read">Read guide →</div>
      </a>
      <a class="guide-card" href="/guides/amazon-price-tracking-guide">
        <div class="guide-tag">How-to</div>
        <h3>How to Track Amazon Prices and Never Overpay Again</h3>
        <p>A step-by-step guide to using price history tools so you always buy at the right time.</p>
        <div class="guide-read">Read guide →</div>
      </a>
    </div>
  </div>

</div>

{{ footer }}
</body></html>"""


# ---------------------------------------------------------------------------
# /deals (same as homepage grid, separate URL for nav)
# ---------------------------------------------------------------------------

DEALS_PAGE = HOMEPAGE  # same template, separate route for clean nav


# ---------------------------------------------------------------------------
# /guides hub
# ---------------------------------------------------------------------------

GUIDES_PAGE = """{{ head }}{{ nav }}
<div class="page-hero">
  <h1>Amazon UK <span>Buying Guides</span></h1>
  <p>In-depth guides to help you buy smarter on Amazon — from understanding pricing to finding the best deals in every category.</p>
</div>
<div class="container">
  <div class="affiliate-notice">
    ℹ️ <strong>Affiliate disclosure:</strong> As an Amazon Associate we earn from qualifying purchases. This never affects which products we recommend.
  </div>
  <div class="guides-grid">
    <a class="guide-card" href="/guides/how-amazon-business-pricing-works">
      <div class="guide-tag">Explainer</div>
      <h3>How Amazon Business Pricing Works (And How to Use It)</h3>
      <p>Amazon Business accounts unlock lower prices on thousands of products. Here's everything you need to know.</p>
      <div class="guide-read">Read guide →</div>
    </a>
    <a class="guide-card" href="/guides/how-to-save-money-on-amazon-uk">
      <div class="guide-tag">Tips</div>
      <h3>10 Proven Ways to Save Money on Amazon UK</h3>
      <p>From Subscribe & Save to price tracking tools, these strategies consistently get you better prices.</p>
      <div class="guide-read">Read guide →</div>
    </a>
    <a class="guide-card" href="/guides/best-office-supplies-amazon-uk">
      <div class="guide-tag">Category Guide</div>
      <h3>Best Office Supplies to Buy on Amazon UK in 2025</h3>
      <p>A curated guide to the best-value office supplies on Amazon, from paper and ink to furniture and storage.</p>
      <div class="guide-read">Read guide →</div>
    </a>
    <a class="guide-card" href="/guides/amazon-price-tracking-guide">
      <div class="guide-tag">How-to</div>
      <h3>How to Track Amazon Prices and Never Overpay Again</h3>
      <p>A step-by-step guide to using price history tools so you always buy at the right time.</p>
      <div class="guide-read">Read guide →</div>
    </a>
  </div>
</div>
{{ footer }}</body></html>"""


# ---------------------------------------------------------------------------
# Guide articles
# ---------------------------------------------------------------------------

GUIDE_BUSINESS_PRICING = """{{ head }}{{ nav }}
<div class="page-hero">
  <h1>How <span>Amazon Business Pricing</span> Works</h1>
  <p>Everything you need to know about Amazon's business-exclusive discounts and how to take advantage of them.</p>
</div>
<div class="container">
<div class="affiliate-notice">
  ℹ️ <strong>Affiliate disclosure:</strong> As an Amazon Associate we earn from qualifying purchases at no extra cost to you.
</div>
<div class="article">

<p>If you've ever wondered why the same product on Amazon costs different amounts for different people, the answer often comes down to Amazon Business pricing. In this guide we'll explain exactly how it works, who qualifies, and how you can use it to save money on everything from office supplies to industrial equipment.</p>

<h2>What Is Amazon Business?</h2>
<p>Amazon Business is a dedicated purchasing platform within Amazon designed for registered businesses, sole traders, charities, and educational institutions. While it looks and works like regular Amazon, it unlocks several exclusive features — the most significant being <strong>business-exclusive pricing</strong> that can be substantially lower than the standard consumer Buy Box price.</p>

<p>Amazon Business launched in the UK in 2016 and has since grown to serve hundreds of thousands of UK organisations. Registration is free and open to any business with a UK VAT number or registered company, as well as sole traders and self-employed individuals.</p>

<h2>How Business Pricing Is Different</h2>
<p>When sellers or Amazon itself offer products on the platform, they can set separate pricing tiers for business customers. These tiers are typically:</p>
<ul>
  <li><strong>Standard business price</strong> — the base discount available to any verified business account</li>
  <li><strong>Quantity discounts</strong> — additional savings when you buy 5, 10, or more units</li>
  <li><strong>Business Prime pricing</strong> — even lower prices for Amazon Business Prime members</li>
</ul>
<p>The discounts vary wildly by category. In our experience monitoring Amazon UK prices, health and beauty, office products, and industrial supplies tend to show the largest gaps — sometimes 5–15% below the consumer price, which adds up fast if you're buying regularly.</p>

<div class="tip-box"><p>💡 <strong>Tip:</strong> Business pricing is most significant on products that Amazon itself sells (rather than third-party Marketplace sellers). Look for the "sold by Amazon" badge for the best business deals.</p></div>

<h2>Who Can Sign Up?</h2>
<p>Amazon Business is available to:</p>
<ul>
  <li>Limited companies and PLCs registered in the UK</li>
  <li>Sole traders and self-employed individuals</li>
  <li>Partnerships</li>
  <li>Charities and non-profits</li>
  <li>Schools, universities, and NHS trusts</li>
  <li>Government bodies and public sector organisations</li>
</ul>
<p>During registration you'll be asked to verify your business status. For most businesses, providing your company name and VAT number is sufficient. The approval process is usually instant.</p>

<h2>How to Register for Amazon Business</h2>
<ol>
  <li>Visit <strong>amazon.co.uk/business</strong> and click "Create a free account"</li>
  <li>Enter your work email address (ideally a company domain address)</li>
  <li>Provide your business name and type</li>
  <li>Add your VAT number if you're VAT registered — this also means Amazon can issue VAT invoices</li>
  <li>Complete identity verification if prompted</li>
</ol>
<p>Once approved, you'll see business prices automatically when browsing — they appear below the standard consumer price on eligible products.</p>

<h2>VAT Invoices and VAT-Exclusive Pricing</h2>
<p>One major benefit that's easy to overlook: Amazon Business gives you access to VAT invoices for almost every purchase. If your business is VAT registered, this means you can reclaim the VAT on eligible purchases — effectively reducing your cost by 20%.</p>
<p>Amazon also offers VAT-exclusive pricing on many products when you're signed into a VAT-registered business account. This is separate from the business price discount — it simply shows you the ex-VAT price rather than the VAT-inclusive price, so you can compare costs more accurately.</p>

<h2>Finding the Best Business Deals</h2>
<p>Not every product has a business price, and even when one exists it may only be a few pence lower than the consumer price. The deals worth acting on are where the gap is significant. Here's how to find them:</p>
<ul>
  <li>Use DealScout's <a href="/deals">live deals page</a> — we track Amazon pricing 24/7 and surface the biggest price gaps automatically</li>
  <li>Look for the "Business price" label on Amazon product pages when signed into your business account</li>
  <li>Check quantity discount tiers — sometimes buying 3–5 units unlocks a much better per-unit price</li>
  <li>Categories with the best business pricing: office supplies, cleaning products, health and safety, lab and industrial, IT peripherals</li>
</ul>

<h2>Is Amazon Business Worth It?</h2>
<p>For any business that buys from Amazon more than occasionally, the answer is almost always yes. Registration is free, there's no minimum spend, and the combination of business prices, VAT invoices, and quantity discounts typically saves a meaningful amount over the course of a year. The only real downside is that you need to manage a separate account — but for most businesses, the savings more than justify that minor inconvenience.</p>

<div class="tip-box"><p>💡 <strong>Quick takeaway:</strong> Register for Amazon Business free, link your VAT number, then check our <a href="/deals">deals page</a> daily for the products where the business price gap is largest. That's where the real savings are.</p></div>

</div>
</div>
{{ footer }}</body></html>"""


GUIDE_SAVE_MONEY = """{{ head }}{{ nav }}
<div class="page-hero">
  <h1>10 Proven Ways to <span>Save Money on Amazon UK</span></h1>
  <p>Strategies that consistently get you better prices — whether you're shopping for yourself or your business.</p>
</div>
<div class="container">
<div class="affiliate-notice">
  ℹ️ <strong>Affiliate disclosure:</strong> As an Amazon Associate we earn from qualifying purchases at no extra cost to you.
</div>
<div class="article">

<p>Amazon UK's pricing changes thousands of times every day. The same product can vary by 20–30% depending on the time of day, day of the week, or even whether you're signed into a business account. These ten strategies will help you consistently pay less, no matter what you're buying.</p>

<h2>1. Use Amazon Business Pricing</h2>
<p>If you buy anything for business purposes — even as a sole trader — register for a free Amazon Business account. Business pricing can be significantly lower than consumer prices on thousands of products, particularly in categories like office supplies, health and safety equipment, and industrial items. We've tracked gaps of up to 15% on some products. See our <a href="/guides/how-amazon-business-pricing-works">full guide to Amazon Business pricing</a> to get started.</p>

<h2>2. Track Prices Before You Buy</h2>
<p>Amazon's prices fluctuate constantly and sellers know that most people don't check price history. Tools like Keepa let you see a product's full price history as a chart, so you can immediately see whether today's price is genuinely a deal or if it was cheaper last month. Never buy an expensive item without checking its price history first.</p>

<h2>3. Use Subscribe & Save</h2>
<p>For products you buy regularly — cleaning supplies, toiletries, pet food, coffee — Subscribe & Save typically saves you 5–15% compared to the standard price. You can cancel or pause at any time with no penalty, so there's essentially no risk. If you have 5 or more active subscriptions, the discount increases further.</p>

<h2>4. Check the Warehouse Deals Section</h2>
<p>Amazon Warehouse sells returned and lightly damaged products at significant discounts — often 20–40% off the new price. The "used — like new" condition items are frequently indistinguishable from new, just without the original packaging. Search your product and filter by "Amazon Warehouse" under the seller options.</p>

<h2>5. Watch for Lightning Deals</h2>
<p>Lightning Deals are time-limited promotions that run for a few hours, usually with stock limits. They appear on Amazon's Today's Deals page and tend to peak during Prime Day, Black Friday, and the run-up to Christmas. Add items to your watchlist and you'll get notified when a deal goes live.</p>

<h2>6. Use Coupon Codes on Product Pages</h2>
<p>Many product pages have a small "Coupon" checkbox below the price that clips an on-page discount — anywhere from 5% to 40% off. These are easy to miss because they're subtle, but they stack with other discounts in some cases. Always check the product page carefully before adding to your basket.</p>

<h2>7. Compare the Add-on Price vs Standard Price</h2>
<p>Some items are sold as "Add-on" products — they're only eligible for purchase when your basket exceeds a certain threshold (usually £20). The Add-on price is often lower than the standard listing price for the same item. If you're already placing an order above the threshold, always check if the Add-on version is cheaper.</p>

<h2>8. Buy Multipacks Strategically</h2>
<p>Amazon frequently prices multipacks at a lower per-unit cost than buying items individually — but not always. It's always worth comparing the unit price (look for the small "per item" or "per 100g" figure below the main price). Sometimes a single unit is actually cheaper per item than the multipack, especially when one has a coupon and the other doesn't.</p>

<h2>9. Use the Price Drop Alerts on DealScout</h2>
<p>Our <a href="/deals">live deals page</a> tracks Amazon UK pricing continuously and surfaces products where the price has dropped significantly. We specifically look for cases where Amazon's own selling price drops notably — these are often the best value opportunities because you're buying from Amazon directly with full buyer protection. Check in daily for the latest.</p>

<h2>10. Time Big Purchases Around Sale Events</h2>
<p>Amazon's major sale events — Prime Day (July), Prime Big Deal Days (October), Black Friday (November), and the post-Christmas sales — consistently offer the best prices of the year on electronics, appliances, and big-ticket items. If your purchase isn't urgent, it's often worth waiting. Prime Day in particular has become competitive enough that prices during the event genuinely beat what's available the rest of the year.</p>

<div class="tip-box"><p>💡 <strong>Bottom line:</strong> The single biggest change you can make is to never buy without checking the price history first. That one habit alone will save most people significant money over the course of a year.</p></div>

</div>
</div>
{{ footer }}</body></html>"""


GUIDE_OFFICE_SUPPLIES = """{{ head }}{{ nav }}
<div class="page-hero">
  <h1>Best Office Supplies to Buy on <span>Amazon UK</span> in 2025</h1>
  <p>A category-by-category guide to the best value office supplies on Amazon, with tips on when and how to buy.</p>
</div>
<div class="container">
<div class="affiliate-notice">
  ℹ️ <strong>Affiliate disclosure:</strong> As an Amazon Associate we earn from qualifying purchases at no extra cost to you.
</div>
<div class="article">

<p>Amazon is one of the best places to buy office supplies in the UK — the combination of low prices, next-day delivery, and the ability to buy in bulk makes it hard to beat. But with millions of listings, knowing which products offer genuine value takes some research. This guide breaks it down by category.</p>

<h2>Paper and Stationery</h2>
<p>This is where Amazon Business pricing makes the biggest difference. Printer paper, notebooks, pens, and filing products are all available at business-exclusive prices that can be 10–20% below the consumer price on the same listing.</p>
<p>For printer paper specifically, look for A4 80gsm reams in boxes of 5 — the per-ream price in a box is almost always lower than buying individually, and the difference is even more pronounced with business pricing applied. Brands like Navigator, HP, and Hammermill consistently offer good quality at competitive prices on Amazon.</p>

<h3>What to look for</h3>
<ul>
  <li>Subscribe & Save for regularly used consumables like sticky notes, pens, and paper</li>
  <li>Business pricing if you're a registered business — can save 10–15% on paper products</li>
  <li>Multipacks for pens and correction fluid — per-unit savings are usually significant</li>
</ul>

<h2>Ink and Toner</h2>
<p>Printer consumables are a major office expense and one of the areas where Amazon can save you the most money compared to buying from the printer manufacturer directly. Compatible (third-party) cartridges are available for most popular printers at a fraction of the OEM price — usually 60–80% cheaper.</p>
<p>The quality of compatible cartridges varies, so stick to well-reviewed brands with high ratings and a returns policy. For high-volume printing, compatible cartridges are a no-brainer. For occasional colour printing where quality matters more, OEM cartridges are still often worth the premium.</p>

<div class="tip-box"><p>💡 <strong>Tip:</strong> Check the Amazon Subscribe & Save price for ink before buying a standalone cartridge — the subscription discount often makes it the cheapest option even for OEM cartridges.</p></div>

<h2>Furniture and Ergonomics</h2>
<p>Desks, chairs, monitor stands, and storage are consistently cheaper on Amazon than in office supply retailers. The key advantage is the reviews — you can read hundreds of real user opinions before committing to a chair or desk. For ergonomic chairs specifically, look for products with at least 500 reviews and a rating above 4.2 to filter out poor quality options.</p>
<p>Standing desk converters have become popular and Amazon UK has a wide selection. Brands like Flexispot and Duronic offer good quality at reasonable prices compared to premium office furniture brands.</p>

<h2>Technology and Peripherals</h2>
<p>Keyboards, mice, headsets, webcams, and monitors are all well-priced on Amazon, particularly when Lightning Deals are running. Business pricing applies to many peripherals, so if you're buying for a team it's worth checking the business account price before purchasing.</p>
<p>For monitors especially, Amazon frequently has significant price drops that don't get widely advertised — checking price history on a 24–27 inch monitor before buying can reveal whether the current price is genuinely competitive.</p>

<h2>Cleaning and Hygiene</h2>
<p>Cleaning supplies are one of the best categories for Amazon Business pricing. Hand soap, sanitiser, surface wipes, bin bags, and kitchen roll all regularly have business prices 10–20% below consumer prices. If you're stocking an office, buying these through a business account with Subscribe & Save applied is almost always the cheapest route outside of a specialist trade supplier.</p>

<h2>Breakroom and Kitchen</h2>
<p>Coffee, tea, snacks, and breakroom supplies are available through Amazon Business, and quantity discounts kick in quickly on items like coffee pods and tea bags. For Nespresso-compatible pods in particular, the price difference between buying in bulk on Amazon vs individual supermarket purchase is substantial.</p>

<h2>When to Buy</h2>
<p>For high-value office equipment (chairs, monitors, printers), wait for Amazon's major sale events — Prime Day in July is the best for electronics, and Black Friday in November typically offers the biggest discounts on furniture. For consumables (paper, ink, cleaning supplies), Subscribe & Save is usually the best ongoing strategy regardless of when you set it up.</p>

<p>You can also use our <a href="/deals">live deals page</a> — we track office supply prices continuously and post whenever a significant price drop occurs.</p>

</div>
</div>
{{ footer }}</body></html>"""


GUIDE_PRICE_TRACKING = """{{ head }}{{ nav }}
<div class="page-hero">
  <h1>How to <span>Track Amazon Prices</span> and Never Overpay Again</h1>
  <p>A practical guide to price history tools and the habits that consistently save Amazon shoppers money.</p>
</div>
<div class="container">
<div class="affiliate-notice">
  ℹ️ <strong>Affiliate disclosure:</strong> As an Amazon Associate we earn from qualifying purchases at no extra cost to you.
</div>
<div class="article">

<p>Amazon changes prices millions of times a day. A product that's £49.99 today might have been £35 three months ago — or it might be at a genuine all-time low. Without price history data, there's no way to tell. This guide covers the tools and strategies that take the guesswork out of Amazon shopping.</p>

<h2>Why Amazon Prices Change So Often</h2>
<p>Amazon uses algorithmic pricing across its marketplace. The price of a product is influenced by competitor prices, stock levels, historical sales velocity, time of year, and dozens of other factors. Third-party sellers also have their own repricing software that reacts to these changes. The result is a marketplace where prices are in constant flux — sometimes by pennies, sometimes by significant amounts.</p>
<p>This works in your favour if you know when a price has genuinely dropped. It works against you if you buy at an artificially inflated price that's about to drop.</p>

<h2>Keepa: The Essential Price History Tool</h2>
<p>Keepa is the most comprehensive Amazon price tracking tool available for UK shoppers. It records the price history of virtually every product on Amazon and presents it as a chart directly on the Amazon product page (via a browser extension). Key features:</p>
<ul>
  <li><strong>Full price history</strong> — see every price the product has been listed at, going back years in some cases</li>
  <li><strong>Price drop alerts</strong> — set a target price and get emailed when the product hits it</li>
  <li><strong>Sales rank history</strong> — see how popular the product is over time, which helps you judge whether a price drop is likely to last</li>
  <li><strong>Marketplace price tracking</strong> — see not just Amazon's price but third-party seller prices too</li>
</ul>
<p>The browser extension is free and works on Amazon.co.uk. There's a paid tier for more advanced features but the free version covers everything most shoppers need.</p>

<h2>How to Read a Keepa Chart</h2>
<p>The Keepa chart uses colour-coded lines for different price types. The key ones to focus on:</p>
<ul>
  <li><strong>Orange line</strong> — Amazon's own selling price (only visible when Amazon is the seller)</li>
  <li><strong>Blue line</strong> — the Buy Box price (what you'd pay when clicking "Add to Basket")</li>
  <li><strong>Green line</strong> — the lowest new third-party seller price</li>
</ul>
<p>Look for the historical range of the orange or blue line. If today's price is near the bottom of the historical range, it's likely a genuine deal. If it's near the top — or if the price was suddenly raised shortly before being "discounted" — it's worth waiting.</p>

<div class="tip-box"><p>💡 <strong>Red flag to watch for:</strong> A price that was artificially raised 30–60 days before a sale event (like Prime Day) and then "discounted" back to its normal level. Keepa's chart makes these manipulation attempts obvious.</p></div>

<h2>Setting Price Drop Alerts</h2>
<p>Both Keepa and CamelCamelCamel (another price tracking service) let you set alerts for specific products. Here's how to use them effectively:</p>
<ol>
  <li>Find the product's historical low price from the chart</li>
  <li>Set your alert price at or just above the historical low</li>
  <li>Set alerts for multiple products you're considering buying — treat it like a watchlist</li>
  <li>When you get an alert, act quickly — significant price drops on popular items often sell out within hours</li>
</ol>

<h2>Using DealScout for Passive Deal Discovery</h2>
<p>If you don't want to manually track individual products, our <a href="/deals">live deals feed</a> does the monitoring for you. We track Amazon UK prices continuously and surface the most significant drops automatically — particularly where Amazon's own price has fallen notably against its recent history. Check the feed daily and you'll catch the best deals without any setup or manual checking.</p>

<h2>The Timing of Amazon Price Drops</h2>
<p>Some patterns are consistent enough to be worth knowing:</p>
<ul>
  <li><strong>Electronics and appliances</strong> — best prices on Prime Day (July) and Black Friday (November)</li>
  <li><strong>Toys and games</strong> — prices drop after Christmas and again in the weeks before Christmas as sellers compete</li>
  <li><strong>Books</strong> — Kindle deals run almost continuously; physical books drop most around Amazon's periodic book sales</li>
  <li><strong>Clothing and fashion</strong> — end-of-season clearances in January and July</li>
  <li><strong>Consumables</strong> — Subscribe & Save is consistently better than waiting for sales</li>
</ul>

<h2>The One Rule That Saves the Most Money</h2>
<p>Of everything in this guide, the single most impactful habit is simple: <strong>never buy a product costing more than £20 without checking its Keepa price history first.</strong> Ten seconds of checking can save you from paying significantly over the odds. Once this becomes a habit, the savings compound quickly over the course of a year.</p>

</div>
</div>
{{ footer }}</body></html>"""


# ---------------------------------------------------------------------------
# About
# ---------------------------------------------------------------------------

ABOUT_PAGE = """{{ head }}{{ nav }}
<div class="page-hero">
  <h1>About <span>DealScout</span></h1>
  <p>What we do, how it works, and why we built it.</p>
</div>
<div class="container">
<div class="article">

<h2>What Is DealScout?</h2>
<p>DealScout is a free Amazon UK deal tracking service. We monitor Amazon prices around the clock and surface genuine savings — products where Amazon's current selling price represents real value compared to recent price history. Our goal is simple: help you spend less on things you were going to buy anyway.</p>

<h2>How It Works</h2>
<p>We track thousands of products across Amazon UK's most active categories — health and beauty, office supplies, tools, electronics, grocery, pet supplies, and more. Our systems check prices continuously throughout the day and night. When a product's price drops significantly, it appears on our <a href="/deals">deals page</a> automatically.</p>
<p>We focus on products sold directly by Amazon (not third-party Marketplace sellers) because these tend to have the most reliable pricing, strongest buyer protection, and fastest delivery. We also pay particular attention to Amazon Business pricing, which is often substantially lower than the standard consumer price on the same product.</p>

<h2>Who We Are</h2>
<p>DealScout is run by a small team based in the UK who are passionate about helping consumers and small businesses get better value from Amazon. We're not affiliated with Amazon — we're independent and our recommendations are based purely on price data and value analysis.</p>

<h2>Affiliate Disclosure</h2>
<p>DealScout participates in the Amazon Associates Programme. This means we earn a small commission when you click through to Amazon and make a purchase. This commission comes from Amazon, not from you — you pay exactly the same price whether you come via DealScout or go directly to Amazon.</p>
<p>This affiliate relationship helps us cover the costs of running the service and keeps it free for users. It does not influence which deals we feature — we surface deals based on price data alone, not on commission rates.</p>

<h2>Our Buying Guides</h2>
<p>Alongside the live deals feed, we publish in-depth <a href="/guides">buying guides</a> to help you understand Amazon's pricing systems, find the best value in specific product categories, and develop habits that save money consistently over time. These guides are written by the DealScout team and updated regularly.</p>

<h2>Get in Touch</h2>
<p>Questions, feedback, or suggestions? We'd love to hear from you. Use our <a href="/contact">contact page</a> to get in touch — we read and respond to every message.</p>

</div>
</div>
{{ footer }}</body></html>"""


# ---------------------------------------------------------------------------
# Privacy Policy
# ---------------------------------------------------------------------------

PRIVACY_PAGE = """{{ head }}{{ nav }}
<div class="page-hero">
  <h1><span>Privacy Policy</span></h1>
  <p>Last updated: January 2025</p>
</div>
<div class="container">
<div class="article">

<h2>Who We Are</h2>
<p>DealScout ("we", "us", "our") operates the website at this domain. This privacy policy explains how we handle your data when you use our site.</p>

<h2>What Data We Collect</h2>
<p>DealScout does not require you to create an account or provide any personal information to use the site. We collect the following data automatically:</p>
<ul>
  <li><strong>Log data</strong> — standard web server logs including IP addresses, browser type, pages visited, and time of visit. This is used for security monitoring and to understand how the site is used.</li>
  <li><strong>Cookies</strong> — we use minimal cookies necessary for the site to function. We do not use tracking cookies or third-party advertising cookies.</li>
</ul>

<h2>Amazon Associates and Affiliate Links</h2>
<p>DealScout participates in the Amazon Associates Programme. When you click a link to Amazon on our site, Amazon may set cookies on your browser in accordance with their own privacy policy. We recommend reviewing <a href="https://www.amazon.co.uk/gp/help/customer/display.html?nodeId=GX7NJQ4ZB8MHFRNJ" target="_blank" rel="noopener">Amazon's privacy policy</a> for details on how they handle data.</p>
<p>We earn a commission on qualifying purchases made via our affiliate links. This does not affect the price you pay.</p>

<h2>How We Use Your Data</h2>
<p>Log data is used solely for operating and improving the service — identifying technical issues, understanding traffic patterns, and maintaining security. We do not sell, share, or use your data for advertising purposes.</p>

<h2>Data Retention</h2>
<p>Server log data is retained for up to 30 days and then automatically deleted. We do not store any personal data beyond what is described above.</p>

<h2>Your Rights</h2>
<p>Under UK GDPR you have the right to request access to any personal data we hold about you, and to request its deletion. To exercise these rights, please contact us via our <a href="/contact">contact page</a>.</p>

<h2>Third-Party Services</h2>
<p>Our site uses Google Fonts for typography. Google may collect data in accordance with their privacy policy when fonts are loaded. We do not use Google Analytics or any other third-party analytics service.</p>

<h2>Changes to This Policy</h2>
<p>We may update this policy from time to time. Changes will be posted on this page with an updated date. Continued use of the site after changes constitutes acceptance of the updated policy.</p>

<h2>Contact</h2>
<p>For privacy-related enquiries, please use our <a href="/contact">contact page</a>.</p>

</div>
</div>
{{ footer }}</body></html>"""


# ---------------------------------------------------------------------------
# Contact
# ---------------------------------------------------------------------------

CONTACT_PAGE = """{{ head }}{{ nav }}
<div class="page-hero">
  <h1>Get in <span>Touch</span></h1>
  <p>Questions, feedback, or deal suggestions — we read every message.</p>
</div>
<div class="container" style="max-width:640px;">
<div class="article">

<h2>Contact DealScout</h2>
<p>We're a small team and we genuinely read all messages. Whether you have a question about a deal, feedback on the site, or a suggestion for a buying guide topic, we'd love to hear from you.</p>

<div style="background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:32px;margin-top:24px;">
  <p style="font-size:15px;color:#374151;margin-bottom:8px;"><strong>Email us at:</strong></p>
  <p style="font-size:18px;font-weight:700;color:#f97316;">hello@dealscout.co.uk</p>
  <p style="font-size:14px;color:#6b7280;margin-top:16px;">We aim to respond within 1–2 business days.</p>
</div>

<h2 style="margin-top:40px;">Frequently Asked Questions</h2>

<h3>Are the deals on DealScout genuine savings?</h3>
<p>Yes. We only surface deals where the current Amazon price represents a real drop compared to recent price history. We don't include products where the price was artificially inflated before being "discounted".</p>

<h3>Do you earn money from the deals?</h3>
<p>We participate in the Amazon Associates Programme, which means we earn a small commission on qualifying purchases made via links on the site. This commission comes from Amazon and does not affect the price you pay. See our <a href="/privacy">privacy policy</a> for more details.</p>

<h3>How often are deals updated?</h3>
<p>Our price monitoring runs continuously throughout the day. New deals appear on the site as soon as we detect a significant price drop — usually within minutes.</p>

<h3>Can I suggest a product category to cover?</h3>
<p>Absolutely — email us with your suggestion and we'll consider it for our next update.</p>

</div>
</div>
{{ footer }}</body></html>"""


# ---------------------------------------------------------------------------
# Settings — ordinary site preferences, with the private monitor feed at the
# very bottom. Not in the nav; reachable at /settings.
# ---------------------------------------------------------------------------

SETTINGS_PAGE = """{{ head }}{{ nav }}
<div class="page-hero">
  <h1>Site <span>Settings</span></h1>
  <p>Preferences for how deals are displayed. Stored in your browser only — nothing is sent to us.
     <a href="/settings/private" rel="nofollow" class="hero-sub">Monitor feed</a></p>
</div>
<div class="container" style="max-width:820px;">
<div class="article">

  <h2>Display</h2>
  <div class="set-row">
    <div><strong>Default marketplace</strong><p>Which region the deals page opens on.</p></div>
    <select id="set-market" class="set-input">
      <option value="all">All</option><option value="UK">UK</option>
      <option value="DE">Germany</option><option value="FR">France</option>
      <option value="IT">Italy</option><option value="ES">Spain</option>
    </select>
  </div>
  <div class="set-row">
    <div><strong>Open deals in a new tab</strong><p>Keeps DealScout open when you click through.</p></div>
    <input type="checkbox" id="set-newtab" class="set-check" checked>
  </div>
  <div class="set-row">
    <div><strong>Compact cards</strong><p>Fit more deals on screen at once.</p></div>
    <input type="checkbox" id="set-compact" class="set-check">
  </div>

  <h2>Notifications</h2>
  <div class="set-row">
    <div><strong>Highlight big discounts</strong><p>Emphasise anything over 30% off.</p></div>
    <input type="checkbox" id="set-highlight" class="set-check" checked>
  </div>

</div>
</div>

<style>
.set-row { display:flex; align-items:center; justify-content:space-between; gap:24px;
           padding:16px 0; border-bottom:1px solid #f3f4f6; }
.set-row p { font-size:13px; color:#6b7280; margin:4px 0 0; }
.set-input { padding:8px 12px; border:1px solid #e5e7eb; border-radius:8px; font-size:14px; background:#fff; }
.set-check { width:20px; height:20px; accent-color:#f97316; }
/* Muted to match the hero's own body text rather than shout. Deliberately still
   a legible, contrasting link — a link coloured to vanish into its background is
   cloaking, which search engines penalise and which reads badly to anyone
   reviewing the site. Quiet is the goal; invisible is a different thing. */
.hero-sub { color:#9ca3af; text-decoration:underline; text-underline-offset:3px;
            font-size:13px; margin-left:6px; white-space:nowrap; }
.hero-sub:hover { color:#f97316; }
</style>

<script>
(function () {
  var keys = ['set-market','set-newtab','set-compact','set-highlight'];
  keys.forEach(function (k) {
    var el = document.getElementById(k); if (!el) return;
    var saved = localStorage.getItem(k);
    if (saved !== null) { if (el.type === 'checkbox') el.checked = saved === '1'; else el.value = saved; }
    el.addEventListener('change', function () {
      localStorage.setItem(k, el.type === 'checkbox' ? (el.checked ? '1' : '0') : el.value);
    });
  });
})();
</script>

{{ footer }}</body></html>"""


# ---------------------------------------------------------------------------
# Private monitor feed — its own page, linked only from the /settings hero.
# ---------------------------------------------------------------------------

PRIVATE_PAGE = """{{ head }}{{ nav }}
<div class="page-hero">
  <h1>Monitor <span>Feed</span></h1>
  <p>Price hits from tracked-product monitoring. Not included in the main deals feed.</p>
</div>
<div class="container" style="max-width:820px;">
<div class="article">

  {% if private_deals %}
  <div class="priv-list">
    {% for d in private_deals %}
    <div class="priv-row">
      <div class="priv-main">
        <span class="priv-asin">{{ d.asin }}</span>
        <span class="priv-price">£{{ "%.2f"|format(d.price) }}</span>
        {% if d.kind == 'Business' %}<span class="priv-tag">Business</span>{% endif %}
      </div>
      <div class="priv-side">
        <span class="time-ago">{{ d.time_ago }}</span>
        <a class="btn-deal" href="/deal/{{ d.asin }}" target="_blank" rel="nofollow noopener">View →</a>
      </div>
    </div>
    {% endfor %}
  </div>
  {% else %}
  <p style="font-size:14px;color:#9ca3af;padding:32px 0;">No recent activity.</p>
  {% endif %}

  <p style="margin-top:40px;font-size:13px;color:#9ca3af;">
    <a href="/settings" rel="nofollow" style="color:#9ca3af;">← Back to settings</a>
  </p>

</div>
</div>

<style>
.priv-list { display:flex; flex-direction:column; gap:8px; }
.priv-row { background:#fff; border:1px solid #e5e7eb; border-radius:10px; padding:14px 16px;
            display:flex; align-items:center; justify-content:space-between; gap:16px; flex-wrap:wrap; }
.priv-main { display:flex; align-items:center; gap:12px; flex-wrap:wrap; }
.priv-asin { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:13px; color:#6b7280; }
.priv-price { font-size:18px; font-weight:800; color:#111827; }
.priv-tag { font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:.06em;
            color:#f97316; border:1px solid #fed7aa; background:#fff7ed; padding:2px 8px; border-radius:999px; }
.priv-side { display:flex; align-items:center; gap:14px; }
</style>

{{ footer }}</body></html>"""


# ---------------------------------------------------------------------------
# Template renderer
# ---------------------------------------------------------------------------

def render_page(template: str, title: str, description: str = "", **kwargs):
    head = base_head(title, description)
    nav = nav_html()
    footer = footer_html()
    html = template.replace("{{ head }}", head).replace("{{ nav }}", nav).replace("{{ footer }}", footer)
    return render_template_string(html, **kwargs)


# ---------------------------------------------------------------------------
# Flask app factory
# ---------------------------------------------------------------------------

def create_app(affiliate_tag: str):
    global AFFILIATE_TAG
    AFFILIATE_TAG = affiliate_tag
    return app


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
@app.route("/deals")
def index():
    clean_old_deals()
    enriched = [{**d, "time_ago": time_ago(d["timestamp"])} for d in deals]
    return render_page(
        HOMEPAGE,
        title="DealScout — Best Amazon UK Deals Today",
        description="Live Amazon UK deal tracking. We monitor prices 24/7 and surface genuine savings across hundreds of categories.",
        deals=enriched,
    )


@app.route("/guides")
def guides():
    return render_page(
        GUIDES_PAGE,
        title="Amazon UK Buying Guides — DealScout",
        description="In-depth guides on Amazon Business pricing, saving money on Amazon UK, and the best products by category.",
    )


@app.route("/guides/how-amazon-business-pricing-works")
def guide_business_pricing():
    return render_page(
        GUIDE_BUSINESS_PRICING,
        title="How Amazon Business Pricing Works — DealScout",
        description="Everything you need to know about Amazon Business accounts, business-exclusive pricing, and how to save money as a registered business.",
    )


@app.route("/guides/how-to-save-money-on-amazon-uk")
def guide_save_money():
    return render_page(
        GUIDE_SAVE_MONEY,
        title="10 Ways to Save Money on Amazon UK — DealScout",
        description="Proven strategies to consistently pay less on Amazon UK — from Business pricing to Subscribe & Save and price tracking tools.",
    )


@app.route("/guides/best-office-supplies-amazon-uk")
def guide_office_supplies():
    return render_page(
        GUIDE_OFFICE_SUPPLIES,
        title="Best Office Supplies on Amazon UK 2025 — DealScout",
        description="A category-by-category guide to the best value office supplies on Amazon UK, with tips on timing and business pricing.",
    )


@app.route("/guides/amazon-price-tracking-guide")
def guide_price_tracking():
    return render_page(
        GUIDE_PRICE_TRACKING,
        title="How to Track Amazon Prices — DealScout",
        description="A practical guide to Keepa, price alerts, and the habits that help you consistently pay less on Amazon.",
    )


@app.route("/about")
def about():
    return render_page(
        ABOUT_PAGE,
        title="About DealScout — Amazon UK Deal Tracking",
        description="DealScout monitors Amazon UK prices around the clock and surfaces genuine savings. Learn how it works and who we are.",
    )


@app.route("/privacy")
def privacy():
    return render_page(
        PRIVACY_PAGE,
        title="Privacy Policy — DealScout",
        description="DealScout privacy policy — how we handle your data when you use the site.",
    )


@app.route("/contact")
def contact():
    return render_page(
        CONTACT_PAGE,
        title="Contact DealScout",
        description="Get in touch with the DealScout team — questions, feedback, or deal suggestions welcome.",
    )


@app.route("/deal/<asin>")
def deal(asin):
    if not valid_asin(asin):
        return "Invalid ASIN", 400
    return redirect(amazon_url_for("UK", asin), 302)


@app.route("/deal/<market>/<asin>")
def deal_market(market, asin):
    """Marketplace-aware variant. /deal/DE/B0XXXXXXXX -> tagged amazon.de link."""
    market = (market or "").upper()
    if market not in MARKETPLACES:
        return "Unknown marketplace", 404
    if not valid_asin(asin):
        return "Invalid ASIN", 400
    return redirect(amazon_url_for(market, asin), 302)


@app.route("/app/deal/<market>/<asin>")
def deal_app_market(market, asin):
    market = (market or "").upper()
    if market not in MARKETPLACES:
        return "Unknown marketplace", 404
    return deal_app(asin, market)


@app.route("/app/deal/<asin>")
def deal_app(asin, market="UK"):
    if not valid_asin(asin):
        return "Invalid ASIN", 400

    amazon_web_url = amazon_url_for(market, asin)
    # Android intent target is the same URL minus the scheme, so it follows the
    # marketplace instead of being pinned to amazon.co.uk.
    intent_target = amazon_web_url.split("://", 1)[1]
    ua = request.headers.get("User-Agent", "")
    is_mobile = any(x in ua for x in ["iPhone", "iPad", "Android"])

    if not is_mobile:
        return redirect(amazon_web_url, 302)

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Opening Amazon...</title>
<style>
  body {{ font-family: -apple-system, sans-serif; display: flex; align-items: center;
         justify-content: center; min-height: 100vh; margin: 0; background: #f3f3f3; }}
  .box {{ text-align: center; padding: 2rem; }}
  a {{ color: #e47911; font-weight: bold; }}
</style>
</head>
<body>
<div class="box">
  <p>Opening in Amazon app...</p>
  <p><a href="{amazon_web_url}">Tap here if nothing happens</a></p>
</div>
<script>
  var webUrl = "{amazon_web_url}";
  var ua = navigator.userAgent;
  var isIOS = /iPhone|iPad|iPod/.test(ua);
  var isAndroid = /Android/.test(ua);

  if (isIOS) {{
    window.location.href = webUrl;
  }} else if (isAndroid) {{
    window.location.href = "intent://{intent_target}#Intent;scheme=https;package=com.amazon.mobilewindow;end";
    setTimeout(function() {{ window.location.href = webUrl; }}, 1500);
  }} else {{
    window.location.href = webUrl;
  }}
</script>
</body>
</html>"""
    return html, 200


def _uncached(resp):
    """Forbid caching on the cart routes.

    Neither the redirect nor the interstitial carried cache headers, so both
    were heuristically cacheable. That is not cosmetic: an interstitial cached
    while CART_MOBILE_MODE was `app` keeps firing the old custom-scheme hop —
    and the confirmation prompt with it — long after the server switched to a
    plain redirect. The phone shows behaviour the server stopped producing,
    which is close to undiagnosable from the outside.

    The target price is also embedded in these URLs, so a shared or proxy cache
    serving a stale one would send a member to the wrong quantity.
    """
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


def cart_url_for(market: str, asin: str, qty: int = 1) -> str:
    """Amazon's Add to Cart form URL, tagged.

    AssociateTag is what Amazon actually pays attribution on — not the referrer
    — so routing the click through this service costs nothing in commission and
    keeps the tag out of the Discord message where it could be read or stripped.
    Documented at webservices.amazon.com/paapi5/documentation/add-to-cart-form.

    KNOWN LIMITATION, reverted to deliberately on 2026-08-22 at Ben's request.
    `ASIN.0` names a PRODUCT, not an offer, so Amazon chooses which offer to
    add. When the requested quantity is more than the cheapest seller will sell
    one customer, it silently adds a dearer seller's offer instead: B0GR6M4JV3
    was judged on Amazon at £12.99 and put an FBM seller's £39.07 in the basket
    at Quantity 20. Check the seller and price in the basket before ordering,
    especially after using Add Max.
    """
    tag = tag_for(market)
    # Index and tag parameter both copied from a link observed working in
    # another deal group: ASIN.0 / Quantity.0 / tag=. The index is arbitrary so
    # long as it is consistent, and `tag` is accepted alongside the documented
    # `AssociateTag`. Matching a format known to work in production beats
    # matching the docs.
    params = f"ASIN.0={asin}&Quantity.0={qty}"
    if tag:
        params += f"&tag={tag}"
    return f"https://www.amazon.{MARKETPLACES[market]}/gp/aws/cart/add.html?{params}"


@app.route("/cart/<asin>")
def cart(asin):
    """Add-to-cart button target. ?m=1 selects the mobile treatment.

    A PLAIN REDIRECT IS THE RIGHT ANSWER, and the reason is worth writing down
    because the clever version is tempting and worse.

    Amazon's apple-app-site-association claims /gp/aws/* for the shopping app,
    so the cart URL is a genuine Universal Link. Tapped from anywhere that
    honours Universal Links, an ordinary https:// link opens the Amazon app
    SILENTLY, with the app's own session, and the basket add goes through.

    A custom scheme (com.amazon.mobile.shopping.web://) reaches the same place,
    but iOS puts an "Open this page in Amazon?" confirmation in front of it,
    because that is what custom schemes get. The prompt is not a bug to be
    worked around — it is the price of not using the Universal Link. Which is
    why the deal groups that feel slickest just link straight to Amazon.

    So `direct` is the default and mobile behaves exactly like desktop. The two
    remaining modes exist for handsets that will not co-operate:

      CART_MOBILE_MODE=app
        Interstitial that tries the custom scheme, plus a tappable button. Use
        ONLY where Universal Links do not fire — typically an in-app browser
        that swallows the hand-off. Costs the confirmation prompt.

      CART_MOBILE_MODE=browser
        Deliberately keep the click in the browser. Universal Links intercept
        navigations but NOT a script-driven location change after load, so this
        stays put on purpose.

    One thing no server can fix: Discord's in-app browser does not fire
    Universal Links at all. Members with "Open links in your browser" switched
    off stay in the webview whatever this route does.
    """
    if not valid_asin(asin):
        return "Invalid ASIN", 400
    market = (request.args.get("market") or "UK").upper()
    if market not in MARKETPLACES:
        return "Unknown marketplace", 404
    try:
        qty = max(1, min(999, int(request.args.get("q", 1))))
    except (TypeError, ValueError):
        qty = 1

    url = cart_url_for(market, asin, qty)
    mode = os.environ.get("CART_MOBILE_MODE", "direct").strip().lower()
    # Desktop always, and mobile too unless someone has deliberately switched
    # this handset-quirk workaround on. A 302 is what makes the app open with
    # no confirmation prompt.
    if request.args.get("m") != "1" or mode == "direct":
        return _uncached(redirect(url, 302))
    # Escaped two ways on purpose: the URL carries & separators, which need HTML
    # escaping in the href and JS-string escaping inside the script.
    safe_attr = _html.escape(url, quote=True)
    safe_js = _json.dumps(url)
    # Amazon's own apple-app-site-association claims /gp/aws/* for the shopping
    # app, so the cart URL is a legitimate app target — the app is not being
    # asked to do something Amazon excluded it from.
    app_url = "com.amazon.mobile.shopping.web://" + url.split("://", 1)[1]
    safe_app = _html.escape(app_url, quote=True)
    note = ("If the app did not open, Discord's built-in browser blocked it. "
            "Turn on <b>Settings &rsaquo; App Settings &rsaquo; Behaviour &rsaquo; "
            "Open links in your browser</b> and the app will open every time."
            if mode == "app" else
            "Opens in your browser &mdash; the app can drop the basket add.")
    # browser mode exists to STAY in the browser, so offering an app button
    # there would contradict the only reason to select it.
    cta = (f'<a class="cta" id="app" href="{safe_app}">Open in Amazon app</a>\n'
           f'  <p><a href="{safe_attr}">or continue in the browser</a></p>'
           if mode == "app" else
           f'<p><a href="{safe_attr}">Tap here if nothing happens</a></p>')
    return _uncached(make_response(f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Adding to basket...</title>
<style>
  body {{ font-family: -apple-system, sans-serif; display: flex; align-items: center;
         justify-content: center; min-height: 100vh; margin: 0; background: #f3f3f3; }}
  .box {{ text-align: center; padding: 2rem; max-width: 26rem; }}
  a {{ color: #e47911; font-weight: bold; }}
  .cta {{ display: block; background: #ffd814; color: #0f1111; text-decoration: none;
         padding: 0.9rem 1.2rem; border-radius: 999px; font-size: 1.05rem;
         margin: 1.25rem 0 0.75rem; }}
  small {{ color: #666; display: block; margin-top: 1rem; line-height: 1.5; }}
</style>
</head>
<body>
<div class="box">
  <p>Adding to your Amazon basket...</p>
  <!-- In app mode this is a REAL TAP on a custom scheme, not decoration: an
       in-app browser swallows a scripted scheme navigation but hands a
       user-initiated one to the OS far more often. -->
  {cta}
  <small>{note}</small>
</div>
<script>
(function () {{
  var webUrl = {safe_js};
  var mode = {_json.dumps(mode)};
  var bare = webUrl.replace(/^https?:\\/\\//, "");
  var ua = navigator.userAgent;
  var isIOS = /iPhone|iPad|iPod/.test(ua);
  var isAndroid = /Android/.test(ua);

  function browserHop() {{
    // replace() not href, so Back returns to Discord rather than trapping
    // the user on this page.
    window.location.replace(webUrl);
  }}

  if (mode !== "app" || (!isIOS && !isAndroid)) {{
    browserHop();
    return;
  }}

  if (isAndroid) {{
    // browser_fallback_url is handled by Chrome itself when the package is
    // absent — more reliable than racing a setTimeout.
    window.location.replace(
      "intent://" + bare +
      "#Intent;scheme=https;package=com.amazon.mshop.android.shopping;" +
      "S.browser_fallback_url=" + encodeURIComponent(webUrl) + ";end"
    );
    return;
  }}

  // iOS has no fallback mechanism in the scheme itself: if the app is not
  // installed nothing happens at all, so time it out and use the browser.
  var fired = Date.now();
  window.location.href = "com.amazon.mobile.shopping.web://" + bare;
  setTimeout(function () {{
    // A long gap means the app opened and this tab was backgrounded; a short
    // one means the scheme went nowhere.
    if (Date.now() - fired < 2500 && !document.hidden) {{ browserHop(); }}
  }}, 1200);
}})();
</script>
</body>
</html>""", 200))


@app.route("/api/deal", methods=["POST"])
def add_deal():
    if request.headers.get("X-API-Secret") != API_SECRET or not API_SECRET:
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(silent=True)
    if not data or "asin" not in data:
        return jsonify({"error": "No data"}), 400
    data["timestamp"] = datetime.utcnow().isoformat()

    # If this ASIN is already listed, update it in place instead of adding a duplicate
    for i, existing in enumerate(deals):
        if existing.get("asin") == data["asin"]:
            deals[i] = data          # update with latest price + timestamp
            deals.insert(0, deals.pop(i))  # move to top
            return jsonify({"ok": True, "updated": True}), 200

    deals.insert(0, data)
    return jsonify({"ok": True, "updated": False}), 200


@app.route("/settings")
def settings():
    return render_page(
        SETTINGS_PAGE,
        title="Settings — DealScout",
        description="Display preferences for DealScout.",
    )


@app.route("/settings/private")
def settings_private():
    """The monitor feed. Linked only from the /settings hero — nothing on the
    main site points here. Note that is obscurity, not access control: the page
    has no login, so treat anything rendered on it as public. That is why the
    entries carry no member identity."""
    clean_old_deals()
    enriched = [{**d, "time_ago": time_ago(d["timestamp"])} for d in private_deals]
    return render_page(
        PRIVATE_PAGE,
        title="Monitor Feed — DealScout",
        description="",
        private_deals=enriched,
    )


@app.route("/api/private-deal", methods=["POST"])
def add_private_deal():
    """Private-monitor hit. Same secret as /api/deal, separate store — these must
    never reach the homepage or /deals feed.

    Only asin/price/kind are accepted. Anything else in the payload is dropped
    rather than stored, so a future change to the sender cannot start leaking
    member identity onto a public page by accident.
    """
    if request.headers.get("X-API-Secret") != API_SECRET or not API_SECRET:
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    asin = str(data.get("asin", ""))
    if not valid_asin(asin):
        return jsonify({"error": "Bad ASIN"}), 400
    try:
        price = round(float(data.get("price", 0)), 2)
    except (TypeError, ValueError):
        return jsonify({"error": "Bad price"}), 400
    if price <= 0:
        return jsonify({"error": "Bad price"}), 400

    entry = {
        "asin": asin,
        "price": price,
        "kind": "Business" if data.get("kind") == "Business" else "Consumer",
        "timestamp": datetime.utcnow().isoformat(),
    }
    for i, existing in enumerate(private_deals):
        if existing.get("asin") == asin:
            private_deals[i] = entry
            private_deals.insert(0, private_deals.pop(i))
            return jsonify({"ok": True, "updated": True}), 200
    private_deals.insert(0, entry)
    return jsonify({"ok": True, "updated": False}), 200


@app.route("/robots.txt")
def robots():
    """Keep /settings out of search results. This is a crawler request, not
    access control — the page is still publicly fetchable by anyone with the
    URL, and always will be while it has no login."""
    return ("User-agent: *\nDisallow: /settings\nDisallow: /api/\n",
            200, {"Content-Type": "text/plain"})


@app.route("/health")
def health():
    return "Deal tracker is running.", 200
