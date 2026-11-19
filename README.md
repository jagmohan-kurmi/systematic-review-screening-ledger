# Systematic Review Screening Ledger

Import RIS, BibTeX, or CSV records, group duplicate title/DOI identities deterministically, record independent reviewer votes and reasons, and export conflicts and counts.

## Install and use

```console
python -m pip install .
systematic-review-screening-ledger import fixtures/sample.csv --ledger review.json
systematic-review-screening-ledger export --ledger review.json --format csv --output review.csv
```

For votes, pass a JSON object with `record_id`, `reviewer`, `decision` (`include`, `exclude`, or `uncertain`), and optional `reason` to `vote`. Inspect `review.json` to select the record ID. Decisions are never automated. Exit codes are `0` (success) and `2` (invalid/unreadable data or output). Local files only; no network access is required.

## Limits

The tool organizes researcher-supplied records and does not replace scholarly judgment. Verify outputs against original sources.

## Tests

```console
python -m unittest discover -s tests -v
```
