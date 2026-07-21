# Handoff — Blackfin commission engine (M1)

Prepared for Blackfin Sports Group by Nisse Group.

This is the productized version of the Blast Media forecast pilot: a
deterministic engine that reads a HubSpot deal export, applies the client's
commission rule, and produces a reconciliation report you can verify line by
line. Every number is computed by plain code — no AI touches any figure.

## What's in the box

```
HANDOFF.md          this file
README.md           full documentation: design rules, layout, add-a-client guide
src/                the engine (rules, ledger, forecast, reconcile, CLI)
clients.yaml        per-client configuration; Blast Media is configured
tests/              the acceptance suite, including the golden Blast Media numbers
deliverables/       pre-generated Blast Media reconciliation (HTML, markdown, PDF)*
data/               empty; place real client CSV exports here (kept out of git)
```

\* `deliverables/` ships in the handoff bundle only, not in the git history —
regenerate it any time with the one command below.

## Run it on a fresh machine

Requires Python 3.12 (nothing else — no database, no services, no network).

```sh
python3.12 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/forecast run \
  --client blast_media \
  --csv data/Blast_Media_Commission_Deals_Import.csv \
  --as-of 2026-07-21 \
  --out out
```

This prints the reconciliation to the console and writes
`out/blast_media_reconciliation.html` (self-contained — open it in any
browser, print to PDF from there) and `out/blast_media_reconciliation.md`.

To check the engine against the recorded acceptance numbers:

```sh
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest
```

All tests must pass. `tests/test_golden_blast_media.py` encodes the Blast
Media answer key — the monthly stream, the five projection totals, and the
two data flags — so any change that moves a number fails loudly.

## What the report shows

- **A. Headline** — the presented method's 12-month total beside the
  expected range, with variance.
- **B. Method table** — every projection method, always, with variance
  against the range midpoint. The presented method is marked and carries a
  stated rationale; nothing is discarded silently.
- **C. Monthly view** — recorded months, then the projection continuing the
  sequence, as tables and a chart.
- **D. Confirm with client** — every data question the engine raised
  (missing months, outlier months, rows it could not verify). The engine
  never fills a gap with a guess; it asks.

## Guarantees

- **Read-only.** The engine reads export files. It never writes to HubSpot,
  QuickBooks, or any other system.
- **No contracts.** Input is structured deal data only.
- **Cross-checked.** Every row's recorded commission is checked against the
  configured rule; a disagreement beyond $0.05 stops the run rather than
  producing a forecast built on a wrong rule.

## Adding the next client

One entry in `clients.yaml` (rule type + parameters, expected range,
presented method + rationale). Flat and tiered marginal-band rules are
built in; a genuinely new rule shape is one small class. The engine,
loader, and report code do not change per client — see README for the
worked example.

## Roadmap

- **M2** — tiered rates live with a second client; payment-schedule
  spreading (one deal split across months).
- **M3** — read-only HubSpot API ingest replacing CSV exports; QuickBooks
  billed actuals as a second stream; computed-vs-billed variance.

Questions: Karel Nijzink, Nisse Group — karelnijzink@gmail.com
