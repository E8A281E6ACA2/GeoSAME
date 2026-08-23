# Reproducibility

## Environment

- Python 3.10+
- No third-party dependency is required for the released deterministic core
- No API key is needed for the public smoke path

## Minimal semantic-check example

```bash
python -m pip install -e .
python examples/minimal_example.py
```

The input is synthetic and stored in `examples/example_input.json`. The command exits non-zero if any required check fails.

## Aggregate metric reproduction

```bash
python scripts/reproduce_aggregate_metrics.py
```

The script performs three functions:

1. validates integer-count identities and denominators;
2. recomputes manuscript-level rates, including Challenge60 confusion-matrix metrics;
3. checks the recomputed values against a versioned expected-metric file.

## Regression tests

```bash
python -m unittest discover -s tests -v
```

## What is and is not reproduced

Reproduced here:

- deterministic verifier behavior exercised by the tests;
- one offline synthetic example;
- arithmetic derived from released aggregate counts;
- explicit denominator and scope guards.

Not reproduced here:

- download or redistribution of third-party benchmark items;
- generation of the original candidate set;
- external model calls or provider-specific decoding;
- raw teacher annotations or adjudication records;
- internal experiment orchestration and review archives.

A later archival release may provide additional approved artifacts after publication and rights review.
