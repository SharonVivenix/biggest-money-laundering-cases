# Biggest Money Laundering Cases

<p align="center">
  <a href="https://www.idenfy.com/">
  </a>
</p>

Most lists of the [biggest money laundering cases](https://www.idenfy.com/blog/biggest-money-laundering-cases/) read like true crime. Cartels, a sovereign fund, a superyacht, a fine with a lot of zeros. Read them as an engineer would read an incident report and a different pattern shows up. Almost none of these banks lacked an AML policy. What they lacked was a specific detection that would have fired on a specific data shape, or a monitoring pipeline that actually received the data in the first place.

This repo treats nine well documented money laundering cases as postmortems. Each one is reduced to the control that failed, and each failure is turned into a transaction monitoring rule you can run. [casebook.py](casebook.py) is a standard library only Python script that ships eight case derived rules, a coverage report that measures how much of your transaction volume reaches any rule at all, and a generator for the case table below. Every alert it raises names the case its rule came from.

```bash
git clone https://github.com/SharonVivenix/biggest-money-laundering-cases.git
cd biggest-money-laundering-cases
python3 casebook.py rules
python3 casebook.py scan examples/transactions.example.csv
python3 casebook.py coverage examples/transactions.example.csv
```

```text
cases.json  ──►  casebook.py table   ──►  README case table (regenerated, CI checked)
                       │
transactions.csv ──►  casebook.py scan     ──►  alerts tagged with rule id and source case
                 └─►  casebook.py coverage ──►  share of volume that any rule can see
```

## The cases as postmortems

Figures come from court filings, regulator releases and official reports, linked from each case name. Where a number in wide circulation differs from the filing, the filing wins (see [Numbers that circulate](#numbers-that-circulate-versus-what-the-filings-say)). `cases.json` is the source of truth and `python3 casebook.py table --write` rebuilds this table from it.

<!-- TABLE:START -->
| Case | Years | Verified scale | Outcome | Control that failed | Rule |
| --- | --- | --- | --- | --- | --- |
| [Wachovia and the Mexican casas de cambio](https://www.justice.gov/archive/usao/fls/PressReleases/2010/100317-02.html) | 2004 to 2007 | At least $373B in wires from Mexican currency exchange houses, over $420B in transactions not effectively monitored | $160M in 2010 ($110M forfeiture plus $50M OCC penalty), deferred prosecution | Correspondent flows from foreign money service businesses never compared to what those businesses could plausibly earn | `R1` |
| [HSBC and the Sinaloa and Norte del Valle cartels](https://www.justice.gov/opa/pr/hsbc-holdings-plc-and-hsbc-bank-usa-na-admit-anti-money-laundering-and-sanctions-violations) | 2006 to 2010 | At least $881M in drug proceeds laundered, $670B in HSBC Mexico wires and $9.4B in US dollar purchases left unmonitored | About $1.9B in forfeiture and penalties in 2012, deferred prosecution | Mexico sat in the lowest risk tier, so bulk cash far above any customer profile went unreviewed | `R2` |
| [Danske Bank Estonia branch](https://www.justice.gov/opa/pr/danske-bank-pleads-guilty-fraud-us-banks-multi-billion-dollar-scheme-access-us-financial) | 2007 to 2015 | About EUR 200B in non resident flows, $160B of it routed through US banks | Guilty plea to conspiracy to commit bank fraud in 2022, about $2B forfeited | Non resident accounts moved money in and straight back out, and the branch ran on a separate IT system head office did not monitor | `R3` |
| [1MDB, Malaysia's sovereign fund](https://www.justice.gov/opa/pr/goldman-sachs-charged-foreign-bribery-case-and-agrees-pay-over-29-billion) | 2009 to 2014 | About $4.5B misappropriated, per the US Department of Justice | Goldman Sachs paid about $2.9B in a 2020 global resolution, former prime minister Najib Razak convicted in 2020 | Bond proceeds hopped through offshore shells and ended in art, property and a superyacht without anyone asking who the shells were | `R4` |
| [Bank of Credit and Commerce International](https://irp.fas.org/congress/1992_rpt/bcci/) | 1972 to 1991 | Billions for cartels and corrupt officials, never fully quantified | Shut down by regulators in several countries in July 1991 | Incorporated in Luxembourg, run from London, booked through the Cayman Islands, so no single supervisor ever saw the whole bank | `R6` |
| [Nauru's offshore banking sector](https://www.fincen.gov/resources/statutes-and-regulations/311-special-measures) | 1990s to 2005 | An estimated $70B of Russian money in 1998, by a widely cited Russian central bank figure | US Treasury Section 311 designation in 2002, removed from the FATF blacklist in 2005 after new AML laws | Hundreds of shell banks licensed from a single address with no supervision behind them | `R6` |
| [Al Capone and cash fronts](https://www.fbi.gov/history/famous-cases/al-capone) | 1920s | Unknown, the cash was never on paper | Convicted of tax evasion in 1931, eleven year sentence | Nothing compared a cash business's takings with similar businesses on the same street | `R7` |
| [TD Bank](https://www.justice.gov/opa/pr/td-bank-pleads-guilty-bank-secrecy-act-and-money-laundering-conspiracy-violations-18b) | 2014 to 2024 | 92% of transaction volume, about $18.3T, unmonitored from 2018 to 2024, more than $670M moved by three laundering networks | Guilty plea in October 2024, about $3B in combined penalties, OCC asset cap | Whole channels such as ACH and checks were excluded from automated monitoring, and the rule set stayed static for years | `R5`, `coverage` |
| [Las Vegas Strip casinos and an illegal bookmaker](https://cdcgaming.com/nevada-regulators-outline-reasons-behind-7-8-million-levied-against-caesars/) | 2017 to 2023 | One illegal bookmaker gambled millions across three operators for years | About $26.8M in Nevada fines in 2025 (Resorts World $10.5M, MGM $8.5M, Caesars $7.8M) | Player play was never tested against a credible source of funds | `R8` |
<!-- TABLE:END -->

## From case to rule

Each rule below is deliberately small. A production rule set would add segmentation, rolling windows and tuning, but the shape of each detection is visible in a dozen lines of [casebook.py](casebook.py). All thresholds sit in one dictionary, `T`, so tuning never means editing rule logic.

### R1 foreign_msb_corridor, from Wachovia

From 2004 to 2007, Mexican currency exchange houses sent at least $373 billion in wires into Wachovia accounts, plus more than $4 billion in bulk cash. The bank was not blind to the flow. It simply never compared the flow against what an exchange house of that size could earn. R1 sums wires from foreign money service businesses per customer per month and alerts when the total clears a floor and also exceeds three times declared turnover.

### R2 cash_over_profile, from HSBC

HSBC USA rated Mexico in its lowest risk category, which kept HSBC Mexico's flows out of meaningful review. Drug proceeds came in as physical cash, in volumes no customer profile could explain. R2 is the oldest rule in AML and still the one that was missing: monthly cash deposits against declared turnover, with a floor so small accounts do not swamp the alert queue.

### R3 nonresident_pass_through, from Danske Bank

Danske Bank's Estonian branch served non resident customers who moved money in and straight back out, and the branch ran on its own IT platform that head office monitoring never saw properly. R3 targets the behaviour rather than the geography. A non resident account that sends 90 percent or more of a month's inflow back out is acting as a pipe, not a customer.

### R4 shell_to_luxury, from 1MDB

The US Department of Justice estimates about $4.5 billion was misappropriated from 1MDB. Bond money moved through offshore companies and came out as art, real estate and a superyacht. R4 joins the two ends: an account mostly funded by offshore companies that then pays an art dealer, yacht broker, property seller or auction house.

### R5 deposit_then_foreign_atm, from TD Bank

One of the networks in the TD Bank case deposited cash at US branches and withdrew it from ATMs in Colombia. R5 looks for foreign ATM withdrawals that land within seven days of cash deposits and add up to at least half of them. TD Bank's bigger lesson concerns coverage, which gets its own section below.

### R6 secrecy_jurisdiction, from BCCI and Nauru

BCCI was incorporated in Luxembourg, run from London and booked through the Cayman Islands, so no single supervisor saw the whole bank. Nauru licensed hundreds of shell banks with no supervision behind them. R6 flags wires above a floor to or from a configurable list of high risk jurisdictions. The sample data uses `ZZ`, a user assigned country code, so no real country is labelled. Populate `--high-risk` from the current FATF lists and your own risk assessment. Keeping those lists current is the job of an [AML screening](https://www.idenfy.com/aml-screening/) layer, and it is the part teams most often let go stale.

### R7 cash_front_revenue, from Al Capone

Capone was convicted of tax evasion, not of the crimes that produced the money. The cash businesses that covered for him had one tell: they took in more than similar businesses could. R7 compares each cash business with the median of its peers in the same category and month. The sample laundromat declares its inflated takings up front, so R2 stays quiet while R7 fires. A front that lies on its onboarding form beats a profile rule, it does not beat a peer benchmark.

### R8 gaming_over_profile, from the Las Vegas Strip casinos

An illegal bookmaker gambled millions across three Strip operators for years. Nevada fined Resorts World $10.5 million, MGM $8.5 million and Caesars $7.8 million in 2025. R8 tests monthly buy ins against declared income, the same profile logic as R2, pointed at a channel banks never see.

## The TD Bank lesson: measure coverage before tuning rules

The Justice Department's account of the TD Bank case describes 92 percent of transaction volume, about $18.3 trillion, going without automated monitoring from January 2018 to April 2024. Whole channels such as ACH and checks were outside the system. No amount of rule tuning fixes a channel that never reaches the rules.

`casebook.py coverage` measures exactly that. It reports, per channel, how much volume exists and which rules read it, then gives a single monitored share of volume. Pass `--monitored-channels` to describe what your monitoring pipeline really ingests, which is often less than what the core banking system produces:

```text
$ python3 casebook.py coverage examples/transactions.example.csv \
    --monitored-channels cash_deposit,wire_in,wire_out
channel                   volume   share  rules
cash_deposit           1,171,268    4.8%  R2,R5,R7
atm_withdrawal            71,111    0.3%  NONE, unmonitored
wire_in                8,960,283   37.1%  R1,R3,R4,R6
wire_out               5,008,908   20.7%  R3,R4,R6
ach                    3,835,411   15.9%  NONE, unmonitored
check                    421,300    1.7%  NONE, unmonitored
card                   3,511,587   14.5%  NONE, unmonitored
casino_buyin           1,174,813    4.9%  NONE, unmonitored

monitored share of volume: 62.7%
```

Two things are worth noticing. Dropping the ATM feed silently disables R5, so a missing channel takes rules down with it. And even with every channel ingested, this rule set reads nothing on ACH, check or card, which is a real gap in the repo, not a bug in the report. The command exits 1 below `--min-coverage` (default 0.95), so it can gate a deployment the same way a test suite does. For background on why ongoing monitoring has to cover every channel, see [transaction monitoring](https://www.idenfy.com/blog/transaction-screening-vs-transaction-monitoring/) versus one off screening.

## What a scan looks like

The sample file holds 2,165 synthetic transactions: 60 ordinary households and businesses as background, and eight planted customers that each replay one case. Every planted customer fires its rule and no background customer fires anything.

```text
$ python3 casebook.py scan examples/transactions.example.csv
2165 transactions, 19 alerts

R1  C-WACH     2026-07  [wachovia]  1,003,533 in wires from foreign money service businesses, declared turnover 200,000
R2  C-HSBC     2026-08  [hsbc]  cash deposits 98,219 are 16.4x declared turnover 6,000
R2  C-TDBK     2026-09  [hsbc]  cash deposits 52,160 are 17.4x declared turnover 3,000
R3  C-DANS     2026-07  [danske]  non resident account passed 98% of 649,356 straight back out
R4  C-1MDB     2026-08  [1mdb]  92% of inflow from offshore companies, 2,800,000 out to luxury assets
R5  C-TDBK     2026-09  [td_bank]  42,623 withdrawn at ATMs in CO within 7 days of 52,160 in cash deposits
R6  C-BCCI     2026-07  [bcci,nauru]  wire_out with counterparty in ZZ (T000282)
R7  C-CAPO     2026-07  [capone]  laundromat banked 61,458 in cash, 7.5x the median of 5 peers
R8  C-BOWY     2026-07  [nevada_casinos]  buy ins of 344,696 against declared income 15,000
...
```

The TD Bank customer trips both R2 and R5, which is how it should be. Two independent rules agreeing on one customer is a stronger case file than either alone. Add `--json` for machine readable output or `--rules R2,R7` to run a subset. `scan` exits 1 when it raises any alert.

## Where each case sits in the laundering lifecycle

The `stage` field in `cases.json` tags each case with the [three stages of money laundering](https://www.idenfy.com/blog/3-stages-of-money-laundering/). The split is useful when deciding where a new rule belongs.

| Stage | Cases | What the rule watches |
| --- | --- | --- |
| Placement | Wachovia, HSBC, Capone, TD Bank | Cash and foreign flows entering the system above what the customer can explain |
| Layering | Danske Bank, BCCI, Nauru | Money moving through accounts, entities and jurisdictions faster than any business purpose needs |
| Integration | 1MDB, Las Vegas casinos | Laundered money coming back out as assets or play that look like ordinary spending |

## Numbers that circulate versus what the filings say

Popular write ups about money laundering cases repeat a few figures that the primary sources do not support. The table uses the filings.

* **Wachovia.** The often quoted line is that Wachovia "laundered" hundreds of billions of dollars. The deferred prosecution agreement says the bank failed to effectively monitor more than $420 billion in transactions with exchange houses, at least $373 billion of it in wires, and the forfeiture covered $110 million in proven drug proceeds. Unmonitored is not the same as laundered.
* **TD Bank.** The Justice Department portion was about $1.8 billion, but the combined penalties with FinCEN and the OCC came to about $3 billion, plus an asset cap. The laundering networks named in the plea moved more than $670 million, not tens of millions.
* **1MDB.** The misappropriated total is about $4.5 billion by the Justice Department's estimate, and Goldman Sachs paid about $2.9 billion to resolve the US side, so the scandal runs well past the round billion figure sometimes quoted.
* **Al Capone.** The story that the phrase money laundering comes from Capone's laundromats is folk etymology. The cash business pattern is real, the word origin is not established.

## Running it on your own data

Export transactions to a CSV with these columns. Extra columns are ignored, missing ones exit with code 3 and the column names.

| Column | Meaning |
| --- | --- |
| `txn_id`, `date` | Your id and an ISO date, `YYYY-MM-DD` |
| `customer_id`, `customer_type` | `individual` or `business` |
| `residency` | `resident` or `non_resident` |
| `declared_monthly_turnover` | From onboarding, income for people and turnover for businesses |
| `mcc` | Merchant or business category, used by R4 and R7 |
| `channel` | `cash_deposit`, `atm_withdrawal`, `wire_in`, `wire_out`, `ach`, `check`, `card`, `casino_buyin` |
| `direction`, `amount` | `in` or `out`, and a positive amount |
| `counterparty_type` | For example `bank`, `foreign_msb`, `offshore_company`, `merchant`, `casino` |
| `counterparty_country`, `atm_country` | ISO 3166 alpha 2 codes |

`examples/make_transactions.py` rebuilds the sample file and is seeded, so its output never changes between runs. Read it to see exactly what each planted customer does.

## Limits worth knowing

* Rules work on calendar months. Real programs use rolling windows, so an actor who splits activity across a month boundary can slip under a threshold here.
* Thresholds in `T` are starting points for tuning, not regulatory limits. Change one and the tests show which alerts moved.
* `declared_monthly_turnover` is only as good as onboarding. R7 exists because a profile can be a lie, and identity and business verification at onboarding are what make the profile worth comparing against.
* The rules flag patterns. A human investigator decides whether a pattern is suspicious and whether a report is due.

## FAQ

**What are the biggest money laundering cases?**
By documented scale, Danske Bank's Estonian branch (about EUR 200 billion in non resident flows), Wachovia (over $420 billion in unmonitored exchange house transactions), HSBC ($881 million in proven drug proceeds and $670 billion in unmonitored Mexican wires) and 1MDB (about $4.5 billion stolen). By penalty, TD Bank's 2024 resolution of about $3 billion is the largest in this repo.

**What do examples of money laundering cases have in common?**
A gap between what the data showed and what any control looked at. Wachovia and HSBC had the flows on their books, Danske had them on a branch platform, TD Bank had them in channels excluded from monitoring. The rules here are written to close those specific gaps.

**Can I run these rules in production?**
Treat them as reference implementations and test fixtures. They are useful for checking that a vendor or in house system catches the same shapes, and the coverage report is useful as is. A production program also needs case management, tuning against your own false positive rate and documented governance.

**Why are ACH, check and card unmonitored in the coverage report?**
Because none of the nine cases produced a rule for them. That is the TD Bank failure reproduced on purpose. Contributions that add a case backed rule for those channels are welcome.

## Contributing and credits

Corrections to case figures, new cases and new rules are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md). Every case needs a primary source link, and every rule needs a planted customer in the example generator plus a test.

The case selection is adapted from iDenfy's article [Biggest Money Laundering Cases](https://www.idenfy.com/blog/biggest-money-laundering-cases/), and iDenfy is the publisher of that source. Figures were checked against court filings and regulator releases and corrected where they differed. The rules, the coverage model and [casebook.py](casebook.py) are independent work. Verification and screening vendors, iDenfy included, are a layer your own program runs on and help you meet your obligations, the program and its decisions stay with the regulated business. Nothing in this repo is legal advice.

## License

MIT. See [LICENSE](LICENSE).
