# Contributing

New cases, corrected figures and new rules are welcome. Three rules apply.

## Every case needs a primary source

A case in `cases.json` links to a court filing, a regulator release or an official report. Not a news roundup, not a vendor blog, not an encyclopedia. When a widely repeated figure disagrees with the filing, use the filing and note the difference in the README section on circulating numbers.

## Every rule needs a planted customer and a test

A new rule in `casebook.py` names the case it came from, declares the channels it reads in `reads`, and keeps its thresholds in `T`. Add a planted customer to `examples/make_transactions.py` that replays the case, regenerate the sample, and add an assertion to `tests/test_casebook.py` that the customer fires and the background stays quiet.

```bash
python3 examples/make_transactions.py > examples/transactions.example.csv
python3 casebook.py table --write
python3 -m py_compile casebook.py examples/make_transactions.py
python3 -m unittest discover -s tests -v
```

## Keep it standard library only

Python 3.8+, no third party packages, so the script runs on a locked down compliance laptop. Sample data stays synthetic. Do not add real customer data or real account numbers, and do not label a real country as high risk in examples, use the `ZZ` code.

This is a reference implementation, not legal advice. Describe monitoring and screening vendors as a layer your own program runs on, never as something that makes a business compliant.
