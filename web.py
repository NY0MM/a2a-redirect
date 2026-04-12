import os
from flask import Flask, redirect

app = Flask(__name__)

AFFILIATE_TAG = os.environ.get("AFFILIATE_TAG", "")

@app.route("/deal/<asin>")
def deal(asin):
    tag = AFFILIATE_TAG
    if not asin.isalnum() or len(asin) != 10:
        return "Invalid ASIN", 400
    amazon_url = f"https://www.amazon.co.uk/dp/{asin}?tag={tag}&th=1&psc=1"
    return redirect(amazon_url, 302)

@app.route("/")
def index():
    return "Deal tracker is running.", 200
