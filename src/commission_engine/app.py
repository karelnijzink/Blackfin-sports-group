"""Double-click desktop launcher — the no-terminal way to run a forecast.

Interactive flow: a file picker asks for the deal export CSV, the engine
runs, the report opens in the default browser, and the files land in a
"Forecast Reports" folder next to the chosen export. Every error surfaces
as a plain-language dialog, including the engine's refusal to forecast when
the export and the commission rule disagree.

The same deterministic pipeline as the CLI — this module adds only dialogs.
Passing a CSV path as an argument skips every dialog (used by automated
packaging smoke tests).
"""

import sys
import webbrowser
from datetime import date
from pathlib import Path

from commission_engine.cli import run_pipeline
from commission_engine.ledger.schema import CrossCheckError
from commission_engine.rules.registry import load_clients

APP_TITLE = "Blackfin Commission Forecast"
REPORTS_FOLDER = "Forecast Reports"


def _pick_csv_dialog() -> Path | None:
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.update()
    chosen = filedialog.askopenfilename(
        title=f"{APP_TITLE} — choose the deal export (CSV)",
        filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
    )
    root.destroy()
    return Path(chosen) if chosen else None


def _show(kind: str, message: str) -> None:
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)  # the result must never open behind the browser
        root.update()
        if kind == "error":
            messagebox.showerror(APP_TITLE, message, parent=root)
        else:
            messagebox.showinfo(APP_TITLE, message, parent=root)
        root.destroy()
    except Exception:  # no display / no tkinter: still say it somewhere
        print(message, file=sys.stderr if kind == "error" else sys.stdout)


def _single_client_id() -> str:
    clients = load_clients()
    if len(clients) == 1:
        return next(iter(clients))
    raise ValueError(
        f"multiple clients configured ({sorted(clients)}); pass the client id explicitly"
    )


def run_for_csv(csv_path: Path, *, as_of: date | None = None) -> Path:
    """Headless core: forecast the configured client for one export file.
    Reports are written to a folder beside the export. Returns the HTML path."""
    output = run_pipeline(
        _single_client_id(),
        csv_path,
        csv_path.parent / REPORTS_FOLDER,
        as_of=as_of,
    )
    return output.html_path


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:]) if argv is None else argv

    if argv:  # headless mode: app <export.csv> [as-of-date]
        as_of = date.fromisoformat(argv[1]) if len(argv) > 1 else None
        html_path = run_for_csv(Path(argv[0]), as_of=as_of)
        print(html_path)
        return 0

    csv_path = _pick_csv_dialog()
    if csv_path is None:
        return 0  # user closed the picker; nothing to do

    try:
        html_path = run_for_csv(csv_path)
    except CrossCheckError as exc:
        _show(
            "error",
            "No forecast was produced.\n\n"
            "One row's recorded commission disagrees with the configured "
            "commission rule, and the engine refuses to build a forecast on "
            f"numbers that don't check out.\n\n{exc}\n\n"
            "Send this message to Nisse Group and we'll chase it down.",
        )
        return 1
    except Exception as exc:  # any other problem: say it plainly, don't vanish
        _show(
            "error",
            f"Something went wrong and no report was produced.\n\n{exc}\n\n"
            "Send this message to Nisse Group and we'll chase it down.",
        )
        return 1

    webbrowser.open(html_path.resolve().as_uri())
    _show(
        "info",
        "Report ready — it just opened in your browser.\n\n"
        f"Saved in the {REPORTS_FOLDER!r} folder next to your export:\n{html_path}",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
