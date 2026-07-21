"""Desktop app — the no-terminal way to run a forecast.

A small branded window, styled to match the reconciliation report: choose
the deal export, the engine runs, the report opens in the browser. Success
and refusal are shown inside the window in plain language — no bare OS
message boxes.

The same deterministic pipeline as the CLI — this module adds only the
window. Passing a CSV path as an argument skips the window entirely (used
by automated packaging smoke tests).
"""

import sys
import threading
import webbrowser
from datetime import date
from pathlib import Path

from commission_engine.cli import run_pipeline
from commission_engine.ledger.schema import CrossCheckError
from commission_engine.rules.registry import load_clients

APP_TITLE = "Blackfin Commission Forecast"
REPORTS_FOLDER = "Forecast Reports"

# the report's palette — the app and the report should read as one product
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
BLUE = "#2a78d6"
BLUE_DARK = "#1c5cab"
GOOD = "#0ca30c"
BAD = "#d03b3b"

FOOTER = "Deterministic math. Every number computed by code from the deal export."


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


def _pick_font(root) -> tuple[str, str]:
    """The platform's modern UI face, with a portable fallback."""
    import tkinter.font as tkfont

    available = set(tkfont.families(root))
    for family in ("Segoe UI", "SF Pro Text", "Helvetica Neue", "DejaVu Sans"):
        if family in available:
            return family, family
    return "TkDefaultFont", "TkDefaultFont"


class ForecastWindow:
    def __init__(self):
        import tkinter as tk
        from tkinter import ttk

        self.tk = tk
        self.ttk = ttk
        root = tk.Tk()
        self.root = root
        root.title(APP_TITLE)
        root.configure(bg=SURFACE)
        root.resizable(False, False)
        root.geometry("600x460")

        family, _ = _pick_font(root)
        f = lambda size, weight="normal": (family, size, weight)  # noqa: E731

        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TFrame", background=SURFACE)
        style.configure("TLabel", background=SURFACE, foreground=INK, font=f(11))
        style.configure(
            "Accent.TButton",
            background=BLUE,
            foreground="#ffffff",
            font=f(12, "bold"),
            borderwidth=0,
            focuscolor=BLUE,
            padding=(26, 12),
        )
        style.map("Accent.TButton", background=[("active", BLUE_DARK), ("disabled", GRID)])
        style.configure(
            "Ghost.TButton",
            background=SURFACE,
            foreground=INK2,
            font=f(11),
            borderwidth=1,
            relief="solid",
            focuscolor=SURFACE,
            padding=(18, 9),
        )
        style.map("Ghost.TButton", background=[("active", "#f0efec")])

        outer = ttk.Frame(root, padding=(44, 34, 44, 0))
        outer.pack(fill="both", expand=True)

        ttk.Label(
            outer, text="BLACKFIN SPORTS GROUP", foreground=INK2, font=(family, 10, "bold")
        ).pack(anchor="w")
        ttk.Label(outer, text="Commission Forecast", foreground=INK, font=f(24, "bold")).pack(
            anchor="w", pady=(2, 2)
        )
        ttk.Label(outer, text="by Nisse Group", foreground=MUTED, font=f(10)).pack(anchor="w")

        rule = tk.Frame(outer, bg=GRID, height=1)
        rule.pack(fill="x", pady=(18, 26))

        self.intro = ttk.Label(
            outer,
            text=(
                "Choose the deal export from HubSpot (a CSV file). The engine "
                "cross-checks every row, runs every projection method, and opens "
                "the reconciliation report in your browser."
            ),
            foreground=INK2,
            wraplength=500,
            justify="left",
            font=f(11),
        )
        self.intro.pack(anchor="w")

        self.action = ttk.Button(
            outer,
            text="Choose the deal export (CSV)",
            style="Accent.TButton",
            command=self.choose_and_run,
        )
        self.action.pack(anchor="w", pady=(22, 0))

        self.status = ttk.Label(outer, text="", foreground=MUTED, font=f(10))
        self.status.pack(anchor="w", pady=(14, 0))

        # result panel — filled in on success or refusal
        self.panel = tk.Frame(outer, bg=SURFACE, highlightthickness=1, highlightbackground=GRID)
        self.panel_title = tk.Label(
            self.panel, bg=SURFACE, fg=INK, font=f(12, "bold"), anchor="w", justify="left"
        )
        self.panel_body = tk.Label(
            self.panel,
            bg=SURFACE,
            fg=INK2,
            font=f(10),
            anchor="w",
            justify="left",
            wraplength=452,
        )
        self.panel_buttons = ttk.Frame(self.panel)
        self.panel_title.pack(anchor="w", padx=20, pady=(16, 4))
        self.panel_body.pack(anchor="w", padx=20)
        self.panel_buttons.pack(anchor="w", padx=20, pady=(12, 16))

        footer = tk.Frame(root, bg=SURFACE)
        footer.pack(side="bottom", fill="x")
        tk.Frame(footer, bg=GRID, height=1).pack(fill="x", padx=44)
        tk.Label(footer, text=FOOTER, bg=SURFACE, fg=MUTED, font=f(9)).pack(
            anchor="w", padx=44, pady=(8, 14)
        )

        self.report_path: Path | None = None

    # ---------------------------------------------------------------- states

    def _clear_panel(self):
        for child in self.panel_buttons.winfo_children():
            child.destroy()
        self.panel.pack_forget()

    def _show_panel(self, accent: str, title: str, body: str, buttons: list[tuple[str, object]]):
        self._clear_panel()
        self.panel.configure(highlightbackground=accent, highlightcolor=accent)
        self.panel_title.configure(text=title, fg=accent if accent != GRID else INK)
        self.panel_body.configure(text=body)
        for label, command in buttons:
            btn_style = "Accent.TButton" if command == self.open_report else "Ghost.TButton"
            self.ttk.Button(self.panel_buttons, text=label, style=btn_style, command=command).pack(
                side="left", padx=(0, 10)
            )
        self.panel.pack(fill="x", pady=(22, 26))
        self.root.geometry("")  # grow the window to fit the result panel

    def choose_and_run(self):
        from tkinter import filedialog

        chosen = filedialog.askopenfilename(
            title=f"{APP_TITLE} — choose the deal export (CSV)",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not chosen:
            return
        csv_path = Path(chosen)
        self._clear_panel()
        self.action.state(["disabled"])
        self.status.configure(text=f"Running the forecast on {csv_path.name} …")
        self.root.update_idletasks()
        try:
            self.report_path = run_for_csv(csv_path)
        except CrossCheckError as exc:
            self.status.configure(text="")
            self._show_panel(
                BAD,
                "No forecast was produced — a number does not check out.",
                "One row's recorded commission disagrees with the configured "
                "commission rule, and the engine refuses to build a forecast on "
                f"numbers that don't check out.\n\n{exc}\n\n"
                "Send this message to Nisse Group and we'll chase it down.",
                [("Choose a different file", self.choose_and_run)],
            )
        except Exception as exc:  # anything else: say it plainly, don't vanish
            self.status.configure(text="")
            self._show_panel(
                BAD,
                "Something went wrong — no report was produced.",
                f"{exc}\n\nSend this message to Nisse Group and we'll chase it down.",
                [("Try again", self.choose_and_run)],
            )
        else:
            self.status.configure(text="")
            self.open_report()
            self._show_panel(
                GOOD,
                "Report ready — it just opened in your browser.",
                f"Saved in the “{REPORTS_FOLDER}” folder next to your export:\n{self.report_path}",
                [("Open report", self.open_report), ("Run another", self.choose_and_run)],
            )
        finally:
            self.action.state(["!disabled"])

    def open_report(self):
        if self.report_path is not None:
            uri = self.report_path.resolve().as_uri()
            # some browser launchers block until the browser exits; never
            # freeze the window over that
            threading.Thread(target=webbrowser.open, args=(uri,), daemon=True).start()

    def run(self):
        self.root.mainloop()


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:]) if argv is None else argv

    if argv:  # headless mode: app <export.csv> [as-of-date]
        as_of = date.fromisoformat(argv[1]) if len(argv) > 1 else None
        html_path = run_for_csv(Path(argv[0]), as_of=as_of)
        print(html_path)
        return 0

    try:
        window = ForecastWindow()
    except Exception as exc:  # no display: not a desktop session
        print(f"error: could not open a window ({exc})", file=sys.stderr)
        return 1
    window.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
