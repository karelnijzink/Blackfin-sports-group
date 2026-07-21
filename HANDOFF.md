# Handoff — Blackfin commission forecast (M1)

Prepared for Blackfin Sports Group by Nisse Group.

A forecast you check, not a black box: the app reads a HubSpot deal export,
applies the commission rule, and produces a reconciliation report — our
computed numbers beside the numbers you already know, with variance. Every
figure is computed by plain code. No AI touches any number.

## Running a forecast (no technical setup)

**1. Download the app** from the repository's *Releases* page
(`Blackfin Commission Forecast — desktop apps`):

- **Windows** — `BlackfinForecast-Windows.exe`
- **Mac** — `BlackfinForecast-macOS.zip` (double-click the zip to unpack
  `BlackfinForecast.app`)

**2. First open only** (the app is unsigned, which is normal for internal
tools, so your computer asks once):

- *Windows*: if a blue "Windows protected your PC" screen appears, click
  **More info**, then **Run anyway**.
- *Mac*: **right-click** the app, choose **Open**, then **Open** again.

**3. Use it.** Double-click the app and choose the deal export (the CSV
file) — that's the whole job. The report appears right in the app, and a
copy is saved in a **Forecast Reports** folder next to your export. Use
**Download report…** to save the report file anywhere; it opens in any
browser and prints cleanly to PDF.

**If the app refuses to make a forecast:** that's a feature, not a crash.
It means one row's recorded commission doesn't match the commission rule,
and the engine will not build a forecast on numbers that don't check out.
The message names the exact row — send it to Nisse Group and we'll chase
it down.

## What the report shows

- **A. Headline** — the presented method's 12-month total beside the
  expected range, with variance.
- **B. Method table** — every projection method, always, with variance
  against the range midpoint. The presented method is marked and carries a
  stated rationale; nothing is discarded silently.
- **C. Monthly view** — recorded months, then the projection continuing
  the sequence, as tables and a chart.
- **D. Confirm with client** — every data question the engine raised
  (missing months, outlier months, rows it could not verify). The engine
  never fills a gap with a guess; it asks.

## Guarantees

- **Read-only.** The app reads export files. It never writes to HubSpot,
  QuickBooks, or any other system, and it never sends data anywhere — it
  runs entirely on your computer.
- **No contracts.** Input is structured deal data only.
- **Cross-checked.** Every row's recorded commission is checked against
  the configured rule; a disagreement beyond $0.05 stops the run.

---

## Appendix — for a technical reader

### What's in this repository

```
HANDOFF.md          this file
README.md           full documentation: design rules, layout, add-a-client guide
src/                the engine (rules, ledger, forecast, reconcile, CLI, desktop app)
clients.yaml        per-client configuration; Blast Media is configured
tests/              the acceptance suite, including the golden Blast Media numbers
packaging/          PyInstaller entry point (desktop apps built by CI)
.github/workflows/  build-desktop-apps: builds and releases the Windows/Mac apps
data/               place real client CSV exports here (kept out of git)
deliverables/       pre-generated Blast Media reconciliation (handoff bundle only)
```

### Command line

Requires Python 3.12; nothing else — no database, no services, no network.

```sh
python3.12 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/forecast run \
  --client blast_media \
  --csv data/Blast_Media_Commission_Deals_Import.csv \
  --as-of 2026-07-21 \
  --out out
```

Acceptance suite (`pip install -e ".[dev]"` first):

```sh
.venv/bin/python -m pytest
```

All tests must pass. `tests/test_golden_blast_media.py` encodes the Blast
Media answer key — any change that moves a number fails loudly.

### Adding the next client

One entry in `clients.yaml` (rule type + parameters, expected range,
presented method + rationale). Flat and tiered marginal-band rules are
built in; a genuinely new rule shape is one small class. The engine,
loader, and report code do not change per client — see README. The desktop
app picks up config from a `clients.yaml` placed next to the executable
(overrides the built-in copy), so config changes don't require a rebuild.

### Rebuilding the desktop apps

Run the *build-desktop-apps* workflow (GitHub → Actions → Run workflow).
It builds one-file apps for Windows and macOS, smoke-tests each frozen
binary against the golden fixture, and publishes them to a Release.

### Roadmap

- **M2** — tiered rates live with a second client; payment-schedule
  spreading (one deal split across months).
- **M3** — read-only HubSpot API ingest replacing CSV exports; QuickBooks
  billed actuals as a second stream; computed-vs-billed variance.

Questions: Karel Nijzink, Nisse Group — karelnijzink@gmail.com
