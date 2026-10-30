#!/usr/bin/env python3
"""casebook.py: turn the biggest money laundering cases into transaction monitoring rules.

Standard library only, Python 3.8+.

    python3 casebook.py scan examples/transactions.example.csv
    python3 casebook.py scan examples/transactions.example.csv --json
    python3 casebook.py coverage examples/transactions.example.csv
    python3 casebook.py coverage examples/transactions.example.csv \\
        --monitored-channels cash_deposit,wire_in,wire_out
    python3 casebook.py rules
    python3 casebook.py table --write        # rebuild the README case table

Every rule names the case it was written from. An alert therefore says not
only what looked wrong but which real failure it resembles.

Exit codes:
    scan       0 no alerts, 1 alerts raised
    coverage   0 coverage at or above --min-coverage, 1 below it
    table      --check exits 1 when README.md is out of sync
    any        3 input error
"""
import argparse
import csv
import datetime as dt
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CASES_FILE = ROOT / "cases.json"
README = ROOT / "README.md"
START = "<!-- TABLE:START -->"
END = "<!-- TABLE:END -->"

CHANNELS = ("cash_deposit", "atm_withdrawal", "wire_in", "wire_out", "ach", "check",
            "card", "casino_buyin")
REQUIRED = ("txn_id", "date", "customer_id", "customer_type", "residency",
            "declared_monthly_turnover", "mcc", "channel", "direction", "amount",
            "counterparty_type", "counterparty_country", "atm_country")

# ZZ is a user assigned ISO 3166 code, so the example data never labels a real
# country. Replace it with the current FATF lists and your own risk assessment.
DEFAULT_HIGH_RISK = {"ZZ"}
LUXURY_MCC = {"art_dealer", "yacht_broker", "real_estate", "jewellery", "auction_house"}

# Thresholds are starting points for tuning, not regulatory limits.
T = {
    "msb_monthly_min": 250_000,     # R1 foreign MSB wires per customer per month
    "msb_profile_x": 3.0,           # R1 multiple of declared turnover
    "cash_profile_x": 3.0,          # R2 multiple of declared turnover
    "cash_min": 10_000,             # R2 floor so small accounts do not drown the queue
    "pass_through_ratio": 0.9,      # R3 share of inflow that leaves again
    "pass_through_min": 100_000,    # R3 monthly inflow floor
    "offshore_share": 0.5,          # R4 share of inflow from offshore companies
    "luxury_min": 50_000,           # R4 luxury outflow floor
    "atm_window_days": 7,           # R5 deposit to foreign ATM window
    "atm_share": 0.5,               # R5 share of deposits withdrawn abroad
    "atm_min": 10_000,              # R5 floor
    "jurisdiction_min": 10_000,     # R6 single transaction floor
    "peer_x": 3.0,                  # R7 multiple of peer median cash
    "peer_min_count": 3,            # R7 peers needed before the benchmark means anything
    "peer_cash_min": 20_000,        # R7 floor
    "gaming_profile_x": 5.0,        # R8 multiple of declared income
    "gaming_min": 50_000,           # R8 floor
}


class InputError(ValueError):
    pass


class Rule:
    __slots__ = ("id", "name", "case", "reads", "fn")

    def __init__(self, rid, name, case, reads, fn):
        self.id, self.name, self.case, self.reads, self.fn = rid, name, case, reads, fn


def month(txn):
    return txn["date"].strftime("%Y-%m")


def by_customer_month(txns, channels):
    out = defaultdict(list)
    for t in txns:
        if t["channel"] in channels:
            out[(t["customer_id"], month(t))].append(t)
    return out


def alert(rule, cid, period, amount, reason):
    return {"rule": rule, "customer_id": cid, "period": period,
            "amount": round(amount, 2), "reason": reason}


def r1_foreign_msb_corridor(txns, ctx):
    hits = []
    for (cid, m), rows in by_customer_month(txns, {"wire_in"}).items():
        msb = sum(t["amount"] for t in rows if t["counterparty_type"] == "foreign_msb")
        declared = rows[0]["declared_monthly_turnover"]
        if msb >= T["msb_monthly_min"] and msb > T["msb_profile_x"] * declared:
            hits.append(alert("R1", cid, m, msb,
                              f"{msb:,.0f} in wires from foreign money service businesses, "
                              f"declared turnover {declared:,.0f}"))
    return hits


def r2_cash_over_profile(txns, ctx):
    hits = []
    for (cid, m), rows in by_customer_month(txns, {"cash_deposit"}).items():
        cash = sum(t["amount"] for t in rows)
        declared = rows[0]["declared_monthly_turnover"]
        if cash >= T["cash_min"] and cash > T["cash_profile_x"] * declared:
            hits.append(alert("R2", cid, m, cash,
                              f"cash deposits {cash:,.0f} are {cash / max(declared, 1):.1f}x "
                              f"declared turnover {declared:,.0f}"))
    return hits


def r3_nonresident_pass_through(txns, ctx):
    hits = []
    for (cid, m), rows in by_customer_month(txns, {"wire_in", "wire_out"}).items():
        if rows[0]["residency"] != "non_resident":
            continue
        inflow = sum(t["amount"] for t in rows if t["direction"] == "in")
        outflow = sum(t["amount"] for t in rows if t["direction"] == "out")
        if inflow >= T["pass_through_min"] and outflow >= T["pass_through_ratio"] * inflow:
            hits.append(alert("R3", cid, m, inflow,
                              f"non resident account passed {outflow / inflow:.0%} of "
                              f"{inflow:,.0f} straight back out"))
    return hits


def r4_shell_to_luxury(txns, ctx):
    hits = []
    for (cid, m), rows in by_customer_month(txns, {"wire_in", "wire_out"}).items():
        inflow = sum(t["amount"] for t in rows if t["direction"] == "in")
        offshore = sum(t["amount"] for t in rows if t["direction"] == "in"
                       and t["counterparty_type"] == "offshore_company")
        luxury = sum(t["amount"] for t in rows if t["direction"] == "out"
                     and t["mcc"] in LUXURY_MCC)
        if inflow and offshore / inflow >= T["offshore_share"] and luxury >= T["luxury_min"]:
            hits.append(alert("R4", cid, m, luxury,
                              f"{offshore / inflow:.0%} of inflow from offshore companies, "
                              f"{luxury:,.0f} out to luxury assets"))
    return hits


def r5_deposit_then_foreign_atm(txns, ctx):
    hits = []
    window = dt.timedelta(days=T["atm_window_days"])
    per_customer = defaultdict(list)
    for t in txns:
        if t["channel"] in ("cash_deposit", "atm_withdrawal"):
            per_customer[t["customer_id"]].append(t)
    for cid, rows in per_customer.items():
        deposits = [t for t in rows if t["channel"] == "cash_deposit"]
        abroad = [t for t in rows if t["channel"] == "atm_withdrawal"
                  and t["atm_country"] and t["atm_country"] != ctx["home"]]
        if not deposits or not abroad:
            continue
        deposited = sum(t["amount"] for t in deposits)
        matched = sum(w["amount"] for w in abroad
                      if any(d["date"] <= w["date"] <= d["date"] + window for d in deposits))
        if matched >= T["atm_min"] and matched >= T["atm_share"] * deposited:
            countries = ",".join(sorted({w["atm_country"] for w in abroad}))
            hits.append(alert("R5", cid, month(abroad[0]), matched,
                              f"{matched:,.0f} withdrawn at ATMs in {countries} within "
                              f"{T['atm_window_days']} days of {deposited:,.0f} in cash deposits"))
    return hits


def r6_secrecy_jurisdiction(txns, ctx):
    hits = []
    for t in txns:
        if (t["channel"] in ("wire_in", "wire_out")
                and t["counterparty_country"] in ctx["high_risk"]
                and t["amount"] >= T["jurisdiction_min"]):
            hits.append(alert("R6", t["customer_id"], month(t), t["amount"],
                              f"{t['channel']} with counterparty in {t['counterparty_country']} "
                              f"({t['txn_id']})"))
    return hits


def r7_cash_front_revenue(txns, ctx):
    hits = []
    cash = defaultdict(float)
    mcc_of = {}
    for t in txns:
        if t["channel"] == "cash_deposit" and t["customer_type"] == "business":
            cash[(t["customer_id"], month(t))] += t["amount"]
            mcc_of[t["customer_id"]] = t["mcc"]
    for (cid, m), total in cash.items():
        peers = [v for (pid, pm), v in cash.items()
                 if pm == m and pid != cid and mcc_of[pid] == mcc_of[cid]]
        if len(peers) < T["peer_min_count"]:
            continue
        median = statistics.median(peers)
        if total >= T["peer_cash_min"] and total > T["peer_x"] * median:
            hits.append(alert("R7", cid, m, total,
                              f"{mcc_of[cid]} banked {total:,.0f} in cash, {total / median:.1f}x "
                              f"the median of {len(peers)} peers"))
    return hits


def r8_gaming_over_profile(txns, ctx):
    hits = []
    for (cid, m), rows in by_customer_month(txns, {"casino_buyin"}).items():
        play = sum(t["amount"] for t in rows)
        declared = rows[0]["declared_monthly_turnover"]
        if play >= T["gaming_min"] and play > T["gaming_profile_x"] * declared:
            hits.append(alert("R8", cid, m, play,
                              f"buy ins of {play:,.0f} against declared income {declared:,.0f}"))
    return hits


RULES = [
    Rule("R1", "foreign_msb_corridor", "wachovia", {"wire_in"}, r1_foreign_msb_corridor),
    Rule("R2", "cash_over_profile", "hsbc", {"cash_deposit"}, r2_cash_over_profile),
    Rule("R3", "nonresident_pass_through", "danske", {"wire_in", "wire_out"},
         r3_nonresident_pass_through),
    Rule("R4", "shell_to_luxury", "1mdb", {"wire_in", "wire_out"}, r4_shell_to_luxury),
    Rule("R5", "deposit_then_foreign_atm", "td_bank", {"cash_deposit", "atm_withdrawal"},
         r5_deposit_then_foreign_atm),
    Rule("R6", "secrecy_jurisdiction", "bcci,nauru", {"wire_in", "wire_out"},
         r6_secrecy_jurisdiction),
    Rule("R7", "cash_front_revenue", "capone", {"cash_deposit"}, r7_cash_front_revenue),
    Rule("R8", "gaming_over_profile", "nevada_casinos", {"casino_buyin"},
         r8_gaming_over_profile),
]
RULE_BY_ID = {r.id: r for r in RULES}


def load_transactions(path):
    try:
        with open(path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            missing = [c for c in REQUIRED if c not in (reader.fieldnames or [])]
            if missing:
                raise InputError(f"missing columns: {', '.join(missing)}")
            rows = []
            for n, row in enumerate(reader, start=2):
                try:
                    row["date"] = dt.date.fromisoformat(row["date"])
                    row["amount"] = float(row["amount"])
                    row["declared_monthly_turnover"] = float(row["declared_monthly_turnover"])
                except ValueError as exc:
                    raise InputError(f"line {n}: {exc}") from None
                if row["channel"] not in CHANNELS:
                    raise InputError(f"line {n}: unknown channel {row['channel']!r}")
                rows.append(row)
            return rows
    except OSError as exc:
        raise InputError(str(exc)) from None


def pick_rules(spec):
    if not spec:
        return list(RULES)
    ids = [s.strip().upper() for s in spec.split(",") if s.strip()]
    unknown = [i for i in ids if i not in RULE_BY_ID]
    if unknown:
        raise InputError(f"unknown rule ids: {', '.join(unknown)}")
    return [RULE_BY_ID[i] for i in ids]


def scan(txns, rules, ctx):
    alerts = []
    for rule in rules:
        for a in rule.fn(txns, ctx):
            a["case"] = rule.case
            alerts.append(a)
    return sorted(alerts, key=lambda a: (a["rule"], a["customer_id"], a["period"]))


def coverage(txns, rules, monitored):
    """Share of transaction volume that reaches at least one enabled rule."""
    readers = defaultdict(list)
    for rule in rules:
        for ch in rule.reads:
            readers[ch].append(rule.id)
    volume = defaultdict(float)
    for t in txns:
        volume[t["channel"]] += t["amount"]
    total = sum(volume.values()) or 1.0
    rows = []
    for ch in CHANNELS:
        if ch not in volume:
            continue
        ingested = monitored is None or ch in monitored
        live = sorted(readers.get(ch, [])) if ingested else []
        rows.append({"channel": ch, "volume": round(volume[ch], 2),
                     "share": volume[ch] / total, "rules": live, "covered": bool(live)})
    covered = sum(r["volume"] for r in rows if r["covered"])
    return {"coverage": covered / total, "total_volume": round(total, 2), "channels": rows}


def load_cases():
    return json.loads(CASES_FILE.read_text(encoding="utf-8"))


def build_table(cases):
    head = ("| Case | Years | Verified scale | Outcome | Control that failed | Rule |\n"
            "| --- | --- | --- | --- | --- | --- |")
    lines = [head]
    for c in cases:
        rules = ", ".join(f"`{r}`" for r in c["rules"])
        lines.append(f"| [{c['name']}]({c['source']}) | {c['years']} | {c['scale']} | "
                     f"{c['outcome']} | {c['control_failed']} | {rules} |")
    return "\n".join(lines)


def splice(readme, table):
    if START not in readme or END not in readme:
        raise InputError("README.md has no table markers")
    head, rest = readme.split(START, 1)
    _, tail = rest.split(END, 1)
    return f"{head}{START}\n{table}\n{END}{tail}"


def cmd_scan(args):
    txns = load_transactions(args.csv)
    ctx = {"home": args.home.upper(),
           "high_risk": {c.strip().upper() for c in args.high_risk.split(",") if c.strip()}}
    alerts = scan(txns, pick_rules(args.rules), ctx)
    if args.json:
        print(json.dumps(alerts, indent=2))
    else:
        print(f"{len(txns)} transactions, {len(alerts)} alerts\n")
        for a in alerts:
            print(f"{a['rule']}  {a['customer_id']:<10} {a['period']}  "
                  f"[{a['case']}]  {a['reason']}")
    return 1 if alerts else 0


def cmd_coverage(args):
    txns = load_transactions(args.csv)
    monitored = None
    if args.monitored_channels:
        monitored = {c.strip() for c in args.monitored_channels.split(",") if c.strip()}
        bad = monitored - set(CHANNELS)
        if bad:
            raise InputError(f"unknown channels: {', '.join(sorted(bad))}")
    report = coverage(txns, pick_rules(args.rules), monitored)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"{'channel':<16}{'volume':>16}{'share':>8}  rules")
        for r in report["channels"]:
            rules = ",".join(r["rules"]) if r["covered"] else "NONE, unmonitored"
            print(f"{r['channel']:<16}{r['volume']:>16,.0f}{r['share']:>8.1%}  {rules}")
        print(f"\nmonitored share of volume: {report['coverage']:.1%}")
    return 0 if report["coverage"] >= args.min_coverage else 1


def cmd_rules(args):
    cases = {c["id"]: c for c in load_cases()}
    for r in RULES:
        names = " and ".join(cases[c]["name"] for c in r.case.split(",") if c in cases)
        print(f"{r.id}  {r.name:<26} reads {','.join(sorted(r.reads)):<28} from {names}")
    return 0


def cmd_table(args):
    table = build_table(load_cases())
    if not (args.write or args.check):
        print(table)
        return 0
    current = README.read_text(encoding="utf-8")
    updated = splice(current, table)
    if args.check:
        if updated != current:
            print("README.md table is out of sync with cases.json, run: "
                  "python3 casebook.py table --write", file=sys.stderr)
            return 1
        return 0
    README.write_text(updated, encoding="utf-8")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="run the case derived rules over a transactions CSV")
    s.add_argument("csv")
    s.add_argument("--rules", help="comma separated rule ids, default all")
    s.add_argument("--home", default="US", help="home country for R5, default US")
    s.add_argument("--high-risk", default=",".join(sorted(DEFAULT_HIGH_RISK)),
                   help="comma separated ISO country codes for R6")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_scan)

    c = sub.add_parser("coverage", help="share of volume that reaches at least one rule")
    c.add_argument("csv")
    c.add_argument("--rules", help="comma separated rule ids, default all")
    c.add_argument("--monitored-channels",
                   help="channels your monitoring system actually ingests, default all")
    c.add_argument("--min-coverage", type=float, default=0.95)
    c.add_argument("--json", action="store_true")
    c.set_defaults(fn=cmd_coverage)

    r = sub.add_parser("rules", help="list rules and the case each one came from")
    r.set_defaults(fn=cmd_rules)

    t = sub.add_parser("table", help="render the README case table from cases.json")
    g = t.add_mutually_exclusive_group()
    g.add_argument("--write", action="store_true")
    g.add_argument("--check", action="store_true")
    t.set_defaults(fn=cmd_table)

    args = p.parse_args(argv)
    try:
        return args.fn(args)
    except InputError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
