#!/usr/bin/env python3
"""Build the synthetic transactions.example.csv used by the README and the tests.

    python3 examples/make_transactions.py > examples/transactions.example.csv

Seeded, so the output is identical on every run. Sixty ordinary customers
create background noise. Eight planted customers each replay the pattern of
one case in cases.json, and their ids say which (C-WACH replays Wachovia).
Every name, id and amount is invented. ZZ is a user assigned country code.
"""
import csv
import datetime as dt
import random
import sys

rng = random.Random(20261030)
MONTHS = [dt.date(2026, 7, 1), dt.date(2026, 8, 1), dt.date(2026, 9, 1)]
COLUMNS = ["txn_id", "date", "customer_id", "customer_type", "residency",
           "declared_monthly_turnover", "mcc", "channel", "direction", "amount",
           "counterparty_type", "counterparty_country", "atm_country"]
rows = []


def day(m, d=None):
    return m + dt.timedelta(days=d if d is not None else rng.randint(0, 27))


def add(cust, date, channel, direction, amount, cp_type="bank", cp_country="US",
        atm_country="", mcc=None):
    rows.append({
        "txn_id": "", "date": date.isoformat(), "customer_id": cust["id"],
        "customer_type": cust["type"], "residency": cust["residency"],
        "declared_monthly_turnover": cust["declared"], "mcc": mcc or cust["mcc"],
        "channel": channel, "direction": direction, "amount": round(amount, 2),
        "counterparty_type": cp_type, "counterparty_country": cp_country,
        "atm_country": atm_country,
    })


def customer(cid, ctype="individual", declared=5000, mcc="none", residency="resident"):
    return {"id": cid, "type": ctype, "declared": declared, "mcc": mcc, "residency": residency}


# Background: 40 households, 20 small businesses.
for n in range(40):
    c = customer(f"C-{n:04d}", declared=rng.choice([3500, 4500, 6000, 8000]))
    for m in MONTHS:
        add(c, day(m, 0), "ach", "in", c["declared"] * rng.uniform(0.9, 1.0), "employer")
        for _ in range(rng.randint(6, 14)):
            add(c, day(m), "card", "out", rng.uniform(8, 220), "merchant", mcc="retail")
        add(c, day(m), "ach", "out", c["declared"] * rng.uniform(0.25, 0.4), "lender")
        if rng.random() < 0.5:
            add(c, day(m), "check", "out", rng.uniform(50, 900), "individual")
        if rng.random() < 0.4:
            add(c, day(m), "cash_deposit", "in", rng.uniform(100, 1200), "self")
        add(c, day(m), "atm_withdrawal", "out", rng.uniform(60, 400), "self", atm_country="US")
        if rng.random() < 0.15:
            add(c, day(m), "wire_out", "out", rng.uniform(500, 4000), "bank",
                rng.choice(["GB", "DE", "MX", "PH"]))

BUSINESS_MIX = ["laundromat"] * 5 + ["restaurant"] * 7 + ["grocery"] * 5 + ["software"] * 3
for n, mcc in enumerate(BUSINESS_MIX):
    declared = {"laundromat": 18000, "restaurant": 60000, "grocery": 90000,
                "software": 120000}[mcc]
    c = customer(f"B-{n:04d}", "business", declared, mcc)
    cash_share = {"laundromat": 0.45, "restaurant": 0.25, "grocery": 0.2, "software": 0.0}[mcc]
    for m in MONTHS:
        add(c, day(m), "card", "in", declared * (1 - cash_share) * rng.uniform(0.85, 1.05),
            "card_acquirer")
        if cash_share:
            for _ in range(4):
                add(c, day(m), "cash_deposit", "in",
                    declared * cash_share / 4 * rng.uniform(0.8, 1.2), "self")
        add(c, day(m), "ach", "out", declared * rng.uniform(0.5, 0.7), "supplier")
        add(c, day(m), "check", "out", declared * rng.uniform(0.05, 0.15), "supplier")
        if rng.random() < 0.3:
            add(c, day(m), "wire_in", "in", rng.uniform(2000, 15000), "bank", "CA")

# R1, Wachovia: a US account fed by Mexican exchange houses.
c = customer("C-WACH", "business", 200000, "import_export")
for m in MONTHS:
    for _ in range(6):
        add(c, day(m), "wire_in", "in", rng.uniform(120000, 180000), "foreign_msb", "MX")
    add(c, day(m), "ach", "out", 180000, "supplier")

# R2, HSBC: cash far above the profile.
c = customer("C-HSBC", "individual", 6000)
for m in MONTHS[1:]:
    for _ in range(5):
        add(c, day(m), "cash_deposit", "in", rng.uniform(14000, 22000), "self")
    add(c, day(m, 27), "wire_out", "out", 70000, "bank", "MX")

# R3, Danske: a non resident shell passing money straight through.
c = customer("C-DANS", "business", 30000, "holding", "non_resident")
for m in MONTHS:
    for _ in range(3):
        amt = rng.uniform(150000, 300000)
        d = day(m, rng.randint(0, 20))
        add(c, d, "wire_in", "in", amt, "bank", "RU")
        add(c, d + dt.timedelta(days=2), "wire_out", "out", amt * 0.98, "bank",
            rng.choice(["LV", "CY", "HK"]))

# R4, 1MDB: offshore money that ends up as art and property.
c = customer("C-1MDB", "individual", 25000)
add(c, day(MONTHS[1], 3), "wire_in", "in", 3_000_000, "offshore_company", "VG")
add(c, day(MONTHS[1], 4), "wire_in", "in", 250_000, "bank", "US")
add(c, day(MONTHS[1], 12), "wire_out", "out", 1_200_000, "merchant", "US", mcc="art_dealer")
add(c, day(MONTHS[1], 20), "wire_out", "out", 1_600_000, "merchant", "US", mcc="real_estate")

# R5, TD Bank: cash in at branches, out again at ATMs abroad.
c = customer("C-TDBK", "individual", 3000)
base = day(MONTHS[2], 2)
for i in range(6):
    add(c, base + dt.timedelta(days=i), "cash_deposit", "in", rng.uniform(8000, 9500), "self")
for i in range(12):
    add(c, base + dt.timedelta(days=3 + i // 3), "atm_withdrawal", "out",
        rng.uniform(3000, 4000), "self", atm_country="CO")

# R6, BCCI and Nauru: payments to an opaque jurisdiction.
c = customer("C-BCCI", "business", 80000, "trading")
for m in MONTHS:
    add(c, day(m), "card", "in", 80000 * rng.uniform(0.9, 1.1), "card_acquirer")
add(c, day(MONTHS[0]), "wire_out", "out", 45000, "bank", "ZZ")
add(c, day(MONTHS[2]), "wire_out", "out", 62000, "bank", "ZZ")

# R7, Capone: a laundromat that banks far more cash than any other laundromat.
# It declares the inflated figure, so the profile rule R2 stays quiet on purpose.
c = customer("C-CAPO", "business", 70000, "laundromat")
for m in MONTHS:
    for _ in range(4):
        add(c, day(m), "cash_deposit", "in", rng.uniform(14000, 17000), "self")
    add(c, day(m), "ach", "out", 25000, "supplier")

# R8, Nevada casinos: a player whose buy ins dwarf any declared income.
c = customer("C-BOWY", "individual", 15000)
for m in MONTHS:
    for _ in range(4):
        add(c, day(m), "casino_buyin", "out", rng.uniform(60000, 140000), "casino", mcc="casino")
    add(c, day(m, 1), "wire_in", "in", 250000, "individual", "US")

rows.sort(key=lambda r: (r["date"], r["customer_id"], r["channel"]))
for i, r in enumerate(rows, start=1):
    r["txn_id"] = f"T{i:06d}"

w = csv.DictWriter(sys.stdout, fieldnames=COLUMNS, lineterminator="\n")
w.writeheader()
w.writerows(rows)
