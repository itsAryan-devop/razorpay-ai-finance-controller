"""
Day-1 GO/NO-GO spike: does Razorpay TEST MODE actually give us usable
settlement data to reconcile against?

This is the single assumption the whole Track-4 plan rests on. We resolve it
in ~1 hour before building anything on top of it.

Usage (from the project root, after `pip install -r requirements.txt` and
creating a .env from .env.example):

    python spike/check_settlements.py setup   # creates test orders + payment links, prints URLs to pay
    #  -> open each printed URL, pay with test card 4111 1111 1111 1111,
    #     any future expiry, any CVV, and on the OTP page enter any digits (or use 'Success')
    python spike/check_settlements.py check   # fetches settlements + recon report, tells us the verdict

The script NEVER prints your secret key. Keys are read from .env only.
"""
import os
import sys
import json
import datetime as dt

import razorpay
import requests
from dotenv import load_dotenv

load_dotenv()

KEY_ID = os.getenv("RAZORPAY_KEY_ID", "")
KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")
BASE = "https://api.razorpay.com/v1"


def _guard_keys():
    if not KEY_ID or not KEY_SECRET or KEY_ID.startswith("rzp_test_xxxx"):
        sys.exit("ERROR: fill RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET in .env first "
                 "(copy .env.example). Use TEST keys (rzp_test_...).")
    if not KEY_ID.startswith("rzp_test_"):
        sys.exit("ERROR: key does not start with rzp_test_ . Refusing to run "
                 "against anything but test mode.")


def _client():
    return razorpay.Client(auth=(KEY_ID, KEY_SECRET))


def _auth():
    return (KEY_ID, KEY_SECRET)


def setup(n=4):
    """Create a few orders + payment links so we have something to settle."""
    _guard_keys()
    client = _client()
    print(f"[setup] auth ok as {KEY_ID[:12]}... (test mode)\n")

    links = []
    for i in range(n):
        amount_paise = (i + 1) * 15000  # Rs 150, 300, 450, 600
        link = client.payment_link.create({
            "amount": amount_paise,
            "currency": "INR",
            "accept_partial": False,
            "description": f"spike-test order #{i+1}",
            "notes": {"spike": "settlement-check", "seq": str(i + 1)},
        })
        links.append(link)
        print(f"  order #{i+1}  Rs {amount_paise/100:>7.2f}  ->  {link['short_url']}")

    print("\n[setup] Open each URL above, pay with test card:")
    print("        card 4111 1111 1111 1111 | any future expiry | any CVV | OTP: any / 'Success'")
    print("        Then wait a bit and run:  python spike/check_settlements.py check")


def _get(path, params=None):
    r = requests.get(f"{BASE}{path}", auth=_auth(), params=params or {}, timeout=30)
    return r.status_code, (r.json() if r.content else {})


def check():
    """Fetch payments, settlements, and the recon-combined report. Report verdict."""
    _guard_keys()
    print(f"[check] auth as {KEY_ID[:12]}... (test mode)\n")

    # 1. payments captured?
    sc, pays = _get("/payments", {"count": 20})
    captured = [p for p in pays.get("items", []) if p.get("status") == "captured"]
    print(f"  payments fetched: {len(pays.get('items', []))}  |  captured: {len(captured)}  (http {sc})")
    if not captured:
        print("  -> No captured payments yet. Run `setup`, pay the links, then re-run `check`.")

    # 2. settlements list
    sc, setl = _get("/settlements", {"count": 20})
    items = setl.get("items", [])
    print(f"  settlements returned: {len(items)}  (http {sc})")
    for s in items[:5]:
        print(f"     setl {s.get('id')}  amount Rs {s.get('amount',0)/100:.2f}  "
              f"status {s.get('status')}  utr {s.get('utr')}")

    # 3. recon-combined report for this month (the endpoint our whole matcher targets)
    now = dt.date.today()
    sc, recon = _get("/settlements/recon/combined",
                     {"year": now.year, "month": now.month, "count": 50})
    recon_items = recon.get("items", []) if isinstance(recon, dict) else []
    print(f"  recon/combined rows (this month): {len(recon_items)}  (http {sc})")
    if sc != 200:
        print(f"     raw: {json.dumps(recon)[:300]}")
    for row in recon_items[:5]:
        print(f"     {row.get('type')}  entity {row.get('entity_id')}  "
              f"credit {row.get('credit')}  debit {row.get('debit')}  fee {row.get('fee')}")

    # verdict
    print("\n===== VERDICT =====")
    if recon_items:
        print("[GO]  test-mode recon/combined returns real rows. Build T4 on real data.")
    elif items:
        print("[PARTIAL]  settlements list populates but recon/combined is empty. "
              "Usable, but confirm recon fields before relying on them.")
    else:
        print("[NO-GO]  no settlement data in test mode. Switch to the synthetic-settlement "
              "generator (still valid -- track says 'synthetic records') or pivot to T3.")
    print("Record the outcome in LOG.md either way.")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    if cmd == "setup":
        setup()
    elif cmd == "check":
        check()
    else:
        sys.exit("usage: python spike/check_settlements.py [setup|check]")
