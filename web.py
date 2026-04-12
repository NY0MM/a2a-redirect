import os
from datetime import datetime, timedelta
from flask import Flask, redirect, request, jsonify, render_template_string

app = Flask(__name__)

AFFILIATE_TAG = os.environ.get("AFFILIATE_TAG", "")
API_SECRET = os.environ.get("API_SECRET", "")

# In-memory deals store — newest first
deals = []

def clean_old_deals():
    cutoff = datetime.utcnow() - timedelta(hours=24)
    global deals
    deals = [d for d in deals if datetime.fromisoformat(d["timestamp"]) > cutoff]

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

HOMEPAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>UK Amazon Deals</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }

        body {
            font-family: 'Inter', sans-serif;
            background: #f3f4f6;
            color: #111827;
        }

        /* Header */
        header {
            background: #fff;
            border-bottom: 1px solid #e5e7eb;
            position: sticky;
            top: 0;
            z-index: 100;
            padding: 0 24px;
        }
        .header-inner {
            max-width: 1400px;
            margin: 0 auto;
            height: 64px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        .logo {
            font-size: 22px;
            font-weight: 800;
            color: #111827;
            text-decoration: none;
        }
        .logo span { color: #f97316; }
        .tagline {
            font-size: 13px;
            color: #6b7280;
        }
        .deal-count {
            background: #f97316;
            color: #fff;
            font-size: 12px;
            font-weight: 700;
            padding: 4px 12px;
            border-radius: 20px;
        }

        /* Hero */
        .hero {
            background: linear-gradient(135deg, #111827 0%, #1f2937 100%);
            color: #fff;
            text-align: center;
            padding: 48px 24px;
        }
        .hero h1 {
            font-size: 36px;
            font-weight: 800;
            margin-bottom: 12px;
        }
        .hero h1 span { color: #f97316; }
        .hero p {
            font-size: 16px;
            color: #9ca3af;
        }
        .hero-stats {
            display: flex;
            justify-content: center;
            gap: 40px;
            margin-top: 32px;
        }
        .stat { text-align: center; }
        .stat-number {
            font-size: 28px;
            font-weight: 800;
            color: #f97316;
        }
        .stat-label {
            font-size: 12px;
            color: #9ca3af;
            margin-top: 2px;
        }

        /* Grid */
        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 32px 24px;
        }
        .section-title {
            font-size: 20px;
            font-weight: 700;
            margin-bottom: 20px;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .section-title::after {
            content: '';
            flex: 1;
            height: 1px;
            background: #e5e7eb;
        }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
            gap: 20px;
        }

        /* Card */
        .card {
            background: #fff;
            border-radius: 12px;
            overflow: hidden;
            border: 1px solid #e5e7eb;
            transition: transform 0.15s, box-shadow 0.15s;
            display: flex;
            flex-direction: column;
        }
        .card:hover {
            transform: translateY(-4px);
            box-shadow: 0 12px 24px rgba(0,0,0,0.10);
        }
        .card-img-wrap {
            position: relative;
            background: #fff;
            padding: 16px;
            display: flex;
            align-items: center;
            justify-content: center;
            height: 200px;
            border-bottom: 1px solid #f3f4f6;
        }
        .card-img-wrap img {
            max-height: 168px;
            max-width: 100%;
            object-fit: contain;
        }
        .badge {
            position: absolute;
            top: 10px;
            left: 10px;
            background: #ef4444;
            color: #fff;
            font-size: 13px;
            font-weight: 800;
            padding: 4px 10px;
            border-radius: 6px;
        }
        .card-body {
            padding: 14px;
            flex: 1;
            display: flex;
            flex-direction: column;
        }
        .card-title {
            font-size: 13px;
            font-weight: 500;
            color: #374151;
            line-height: 1.4;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
            margin-bottom: 12px;
            flex: 1;
        }
        .price-row {
            margin-bottom: 12px;
        }
        .price-now {
            font-size: 22px;
            font-weight: 800;
            color: #111827;
        }
        .price-was {
            font-size: 13px;
            color: #9ca3af;
            text-decoration: line-through;
            margin-left: 6px;
        }
        .price-save {
            font-size: 12px;
            color: #16a34a;
            font-weight: 600;
            margin-top: 2px;
        }
        .card-footer {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-top: 4px;
        }
        .time-ago {
            font-size: 11px;
            color: #9ca3af;
        }
        .btn-deal {
            background: #f97316;
            color: #fff;
            font-size: 13px;
            font-weight: 700;
            padding: 8px 16px;
            border-radius: 8px;
            text-decoration: none;
            transition: background 0.15s;
            white-space: nowrap;
        }
        .btn-deal:hover { background: #ea6c0a; }

        /* Empty state */
        .empty {
            text-align: center;
            padding: 80px 24px;
            color: #9ca3af;
        }
        .empty-icon { font-size: 48px; margin-bottom: 16px; }
        .empty h2 { font-size: 20px; font-weight: 600; color: #6b7280; margin-bottom: 8px; }

        /* Footer */
        footer {
            background: #111827;
            color: #6b7280;
            text-align: center;
            padding: 24px;
            font-size: 12px;
            margin-top: 48px;
        }
        footer a { color: #9ca3af; text-decoration: none; }

        @media (max-width: 600px) {
            .hero h1 { font-size: 24px; }
            .hero-stats { gap: 20px; }
            .tagline { display: none; }
            .grid { grid-template-columns: repeat(2, 1fr); gap: 12px; }
            .card-img-wrap { height: 150px; }
        }
    </style>
</head>
<body>

<header>
    <div class="header-inner">
        <a class="logo" href="/">Deal<span>Scout</span></a>
        <span class="tagline">Fresh Amazon UK deals, updated every minute</span>
        <span class="deal-count">{{ deals|length }} live deals</span>
    </div>
</header>

<div class="hero">
    <h1>The Best <span>Amazon UK</span> Deals</h1>
    <p>Hand-picked discounts updated automatically — all day, every day</p>
    <div class="hero-stats">
        <div class="stat">
            <div class="stat-number">{{ deals|length }}</div>
            <div class="stat-label">Live Deals</div>
        </div>
        <div class="stat">
            <div class="stat-number">24h</div>
            <div class="stat-label">Rolling Window</div>
        </div>
        <div class="stat">
            <div class="stat-number">Auto</div>
            <div class="stat-label">Updated</div>
        </div>
    </div>
</div>

<div class="container">
    {% if deals %}
    <div class="section-title">Latest Deals</div>
    <div class="grid">
        {% for deal in deals %}
        <div class="card">
            <div class="card-img-wrap">
                <img
                    src="{{ deal.image }}"
                    alt="{{ deal.title }}"
                    onerror="this.src='https://via.placeholder.com/200x200?text=No+Image'"
                >
                {% if deal.discount_percent > 0 %}
                <div class="badge">-{{ deal.discount_percent }}%</div>
                {% endif %}
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
    {% else %}
    <div class="empty">
        <div class="empty-icon">🔍</div>
        <h2>Scanning for deals...</h2>
        <p>Check back shortly — new deals are added automatically every minute.</p>
    </div>
    {% endif %}
</div>

<footer>
    <p>As an Amazon Associate I earn from qualifying purchases. &nbsp;|&nbsp; Prices may change at any time.</p>
</footer>

</body>
</html>
"""

def create_app(affiliate_tag: str):
    global AFFILIATE_TAG
    AFFILIATE_TAG = affiliate_tag
    return app


@app.route("/")
def index():
    clean_old_deals()
    enriched = [{**d, "time_ago": time_ago(d["timestamp"])} for d in deals]
    return render_template_string(HOMEPAGE, deals=enriched)


@app.route("/deal/<asin>")
def deal(asin):
    if not asin.isalnum() or len(asin) != 10:
        return "Invalid ASIN", 400
    amazon_url = f"https://www.amazon.co.uk/dp/{asin}?tag={AFFILIATE_TAG}&th=1&psc=1"
    return redirect(amazon_url, 302)


@app.route("/api/deal", methods=["POST"])
def add_deal():
    if request.headers.get("X-API-Secret") != API_SECRET or not API_SECRET:
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "No data"}), 400
    data["timestamp"] = datetime.utcnow().isoformat()
    deals.insert(0, data)
    return jsonify({"ok": True}), 200


@app.route("/")
def health():
    return "Deal tracker is running.", 200
