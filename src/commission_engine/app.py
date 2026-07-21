"""Desktop app — the no-terminal way to run a forecast.

A small branded window, styled to match the reconciliation report: choose
the deal export, the engine runs, and the report appears right in the
window — headline, method table, chart, monthly view, and the questions to
confirm. A copy is always saved next to the export, and a Download button
saves the self-contained HTML report wherever the user wants it. Nothing
ever opens a browser and nothing leaves the machine.

The same deterministic pipeline as the CLI — this module adds only the
window. Passing a CSV path as an argument skips the window entirely (used
by automated packaging smoke tests).
"""

import shutil
import sys
from datetime import date
from pathlib import Path

from commission_engine.cli import PipelineOutput, run_pipeline
from commission_engine.ledger.schema import CrossCheckError
from commission_engine.reconcile.report import ReconciliationReport
from commission_engine.rules.registry import load_clients

APP_TITLE = "Blackfin Commission Forecast"
REPORTS_FOLDER = "Forecast Reports"

# the report's palette — the app and the report should read as one product
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"
BLUE = "#2a78d6"
BLUE_DARK = "#1c5cab"
BLUE_LIGHT = "#86b6ef"
ROW_TINT = "#eef4fc"
GOOD = "#006300"
BAD = "#d03b3b"

FOOTER = "Deterministic math. Every number computed by code from the deal export."


def _single_client_id() -> str:
    clients = load_clients()
    if len(clients) == 1:
        return next(iter(clients))
    raise ValueError(
        f"multiple clients configured ({sorted(clients)}); pass the client id explicitly"
    )


def _run(csv_path: Path, *, as_of: date | None = None) -> PipelineOutput:
    """Headless core: forecast the configured client for one export file.
    Reports are written to a folder beside the export."""
    return run_pipeline(
        _single_client_id(),
        csv_path,
        csv_path.parent / REPORTS_FOLDER,
        as_of=as_of,
    )


def run_for_csv(csv_path: Path, *, as_of: date | None = None) -> Path:
    """Compatibility wrapper used by smoke tests: returns the HTML path."""
    return _run(csv_path, as_of=as_of).html_path


def _pick_font(root) -> str:
    """The platform's modern UI face, with a portable fallback."""
    import tkinter.font as tkfont

    available = set(tkfont.families(root))
    for family in ("Segoe UI", "SF Pro Text", "Helvetica Neue", "DejaVu Sans"):
        if family in available:
            return family
    return "TkDefaultFont"


def _money(value) -> str:
    return f"${value:,.2f}"


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

        family = _pick_font(root)
        self.family = family
        f = lambda size, weight="normal": (family, size, weight)  # noqa: E731
        self.f = f

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
            padding=(24, 11),
        )
        style.map("Ghost.TButton", background=[("active", "#f0efec")])
        style.configure(
            "Report.Vertical.TScrollbar",
            background=GRID,
            troughcolor=SURFACE,
            borderwidth=0,
            arrowsize=12,
        )

        outer = ttk.Frame(root, padding=(44, 34, 44, 0))
        outer.pack(fill="both", expand=True)
        ttk.Frame(outer, width=512, height=0).pack()
        self.outer = outer

        header = ttk.Frame(outer)
        header.pack(fill="x", anchor="w")
        ttk.Label(
            header, text="BLACKFIN SPORTS GROUP", foreground=INK2, font=(family, 10, "bold")
        ).pack(anchor="w")
        ttk.Label(header, text="Commission Forecast", foreground=INK, font=f(24, "bold")).pack(
            anchor="w", pady=(2, 2)
        )
        ttk.Label(header, text="by Nisse Group", foreground=MUTED, font=f(10)).pack(anchor="w")
        tk.Frame(header, bg=GRID, height=1).pack(fill="x", pady=(18, 0))

        # ---- home view
        self.home = ttk.Frame(outer)
        self.intro = ttk.Label(
            self.home,
            text=(
                "Choose the deal export from HubSpot (a CSV file). The engine "
                "cross-checks every row, runs every projection method, and shows "
                "the reconciliation report right here."
            ),
            foreground=INK2,
            wraplength=500,
            justify="left",
            font=f(11),
        )
        self.intro.pack(anchor="w", pady=(26, 0))
        self.action = ttk.Button(
            self.home,
            text="Choose the deal export (CSV)…",
            style="Accent.TButton",
            command=self.choose_and_run,
        )
        self.action.pack(anchor="w", pady=(22, 14))
        self.status = ttk.Label(self.home, text="", foreground=INK2, font=f(10))
        self.status.pack(anchor="w")
        self.home.pack(fill="x", anchor="w")

        # ---- refusal / error panel (shown on the home view)
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

        # ---- report view (built per run)
        self.report_view = None

        footer = tk.Frame(root, bg=SURFACE)
        footer.pack(side="bottom", fill="x")
        tk.Frame(footer, bg=GRID, height=1).pack(fill="x", padx=44)
        tk.Label(footer, text=FOOTER, bg=SURFACE, fg=INK2, font=f(9)).pack(
            anchor="w", padx=44, pady=(8, 14)
        )

        self.output: PipelineOutput | None = None

    # ---------------------------------------------------------------- states

    def _show_home(self):
        if self.report_view is not None:
            self.report_view.destroy()
            self.report_view = None
        self.panel.pack_forget()
        self.home.pack(fill="x", anchor="w")
        self.root.geometry("")

    def _show_panel(self, accent, title, body, buttons):
        for child in self.panel_buttons.winfo_children():
            child.destroy()
        if self.report_view is not None:
            self.report_view.destroy()
            self.report_view = None
        self.home.pack_forget()
        self.panel.configure(highlightbackground=accent, highlightcolor=accent)
        self.panel_title.configure(text=title, fg=accent)
        self.panel_body.configure(text=body)
        for label, command, primary in buttons:
            btn_style = "Accent.TButton" if primary else "Ghost.TButton"
            self.ttk.Button(self.panel_buttons, text=label, style=btn_style, command=command).pack(
                side="left", padx=(0, 10)
            )
        self.panel.pack(fill="x", pady=(26, 26))
        self.root.geometry("")

    # ---------------------------------------------------------------- run

    def choose_and_run(self):
        from tkinter import filedialog

        chosen = filedialog.askopenfilename(
            title=f"{APP_TITLE} — choose the deal export (CSV)",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not chosen:
            return
        csv_path = Path(chosen)
        self._show_home()
        self.action.state(["disabled"])
        self.status.configure(text=f"Running the forecast on {csv_path.name} …")
        self.root.update_idletasks()
        try:
            self.output = _run(csv_path)
        except CrossCheckError as exc:
            self.status.configure(text="")
            self._show_panel(
                BAD,
                "No forecast was produced — a number does not check out.",
                "One row's recorded commission disagrees with the configured "
                "commission rule, and the engine refuses to build a forecast on "
                f"numbers that don't check out.\n\n{exc}\n\n"
                "Send this message to Nisse Group and we'll chase it down.",
                [("Choose a different file…", self.choose_and_run, True)],
            )
        except Exception as exc:  # anything else: say it plainly, don't vanish
            self.status.configure(text="")
            self._show_panel(
                BAD,
                "Something went wrong — no report was produced.",
                f"{exc}\n\nSend this message to Nisse Group and we'll chase it down.",
                [("Try again…", self.choose_and_run, True)],
            )
        else:
            self.status.configure(text="")
            self._show_report()
        finally:
            self.action.state(["!disabled"])

    def download_report(self):
        from tkinter import filedialog

        if self.output is None:
            return
        target = filedialog.asksaveasfilename(
            title=f"{APP_TITLE} — save the report",
            initialfile=self.output.html_path.name,
            defaultextension=".html",
            filetypes=[("HTML report", "*.html")],
        )
        if not target:
            return
        shutil.copyfile(self.output.html_path, target)
        self.saved_note.configure(text=f"Saved a copy to {Path(target).name}")

    # ---------------------------------------------------------------- report view

    def _table(self, parent, rows, *, aligns, widths, header=True, highlight_row=None):
        tk = self.tk
        table = tk.Frame(parent, bg=SURFACE)
        for r, row in enumerate(rows):
            is_header = header and r == 0
            tint = ROW_TINT if highlight_row is not None and r == highlight_row else SURFACE
            for c, cell in enumerate(row):
                tk.Label(
                    table,
                    text=cell,
                    bg=tint,
                    fg=INK2 if is_header else INK,
                    font=self.f(9, "bold") if is_header else self.f(9),
                    anchor=aligns[c],
                    width=widths[c],
                    padx=6,
                    pady=3,
                ).grid(row=r * 2, column=c, sticky="ew")
            tk.Frame(table, bg=GRID, height=1).grid(
                row=r * 2 + 1, column=0, columnspan=len(row), sticky="ew"
            )
        return table

    def _chart(self, parent, report: ReconciliationReport):
        from commission_engine.reconcile.render import _nice_step

        tk = self.tk
        bars = [(e.month, float(e.commission_2dp), False) for e in report.historical]
        bars += [(m, float(v), True) for m, v in report.projected]

        width, height = 648, 190
        left, right, top, bottom = 46, 6, 8, 22
        plot_w, plot_h = width - left - right, height - top - bottom
        peak = max(v for _, v, _ in bars)
        step = _nice_step(peak / 4)
        ticks = 0
        while ticks * step < peak:
            ticks += 1
        ticks = max(ticks, 1)
        y_max = ticks * step

        canvas = tk.Canvas(
            parent, width=width, height=height, bg=SURFACE, highlightthickness=0, bd=0
        )
        for t in range(ticks + 1):
            y = top + plot_h * (1 - (t * step) / y_max)
            if t > 0:
                canvas.create_line(left, y, width - right, y, fill=GRID)
            canvas.create_text(
                left - 6,
                y,
                text=f"{t * step:,.0f}",
                anchor="e",
                fill=MUTED,
                font=(self.family, 7),
            )
        band = plot_w / len(bars)
        bar_w = min(18.0, band - 2)
        base_y = top + plot_h
        boundary = left + band * len(report.historical)
        canvas.create_line(boundary, top, boundary, base_y, fill=BASELINE)
        for i, (month, value, projected) in enumerate(bars):
            x = left + band * i + (band - bar_w) / 2
            y = top + plot_h * (1 - value / y_max)
            canvas.create_rectangle(
                x, y, x + bar_w, base_y, fill=BLUE_LIGHT if projected else BLUE, width=0
            )
            if month.month in (1, 4, 7, 10):
                canvas.create_text(
                    x + bar_w / 2,
                    base_y + 11,
                    text=f"{month:%b %y}",
                    fill=MUTED,
                    font=(self.family, 7),
                )
        canvas.create_line(left, base_y, width - right, base_y, fill=BASELINE)
        return canvas

    def _show_report(self):
        tk, ttk, f = self.tk, self.ttk, self.f
        report = self.output.report
        self.home.pack_forget()
        self.panel.pack_forget()
        if self.report_view is not None:
            self.report_view.destroy()

        view = ttk.Frame(self.outer)
        self.report_view = view

        # action bar: download is the primary act on this screen
        bar = ttk.Frame(view)
        bar.pack(fill="x", pady=(18, 6))
        ttk.Button(
            bar, text="Download report…", style="Accent.TButton", command=self.download_report
        ).pack(side="left", padx=(0, 10))
        ttk.Button(
            bar, text="Run another forecast…", style="Ghost.TButton", command=self.choose_and_run
        ).pack(side="left")
        self.saved_note = ttk.Label(
            view,
            text=f"Saved automatically next to your export, in “{REPORTS_FOLDER}”.",
            foreground=INK2,
            font=f(9),
        )
        self.saved_note.pack(anchor="w", pady=(0, 10))

        # scrollable report body
        holder = tk.Frame(view, bg=SURFACE, highlightthickness=1, highlightbackground=GRID)
        holder.pack(fill="both", expand=True)
        canvas = tk.Canvas(holder, bg=SURFACE, highlightthickness=0, width=692, height=430)
        vsb = ttk.Scrollbar(
            holder, orient="vertical", command=canvas.yview, style="Report.Vertical.TScrollbar"
        )
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        body = tk.Frame(canvas, bg=SURFACE)
        canvas.create_window((0, 0), window=body, anchor="nw")
        body.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        def scroll(event):
            if getattr(event, "num", None) == 4 or getattr(event, "delta", 0) > 0:
                canvas.yview_scroll(-2, "units")
            else:
                canvas.yview_scroll(2, "units")

        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            canvas.bind_all(seq, scroll)

        pad = {"padx": 22}

        def section(text):
            tk.Label(
                body, text=text, bg=SURFACE, fg=INK2, font=(self.family, 9, "bold"), anchor="w"
            ).pack(anchor="w", pady=(18, 2), **pad)
            tk.Frame(body, bg=GRID, height=1).pack(fill="x", **pad)

        # A. headline
        section(f"{report.client_name.upper()} — RECONCILIATION, AS OF {report.as_of:%d %b %Y}")
        tk.Label(
            body,
            text=f"Projected {report.horizon}-month commission ({report.presented.label})",
            bg=SURFACE,
            fg=INK2,
            font=f(9),
            anchor="w",
        ).pack(anchor="w", pady=(10, 0), **pad)
        tk.Label(
            body,
            text=_money(report.headline_total),
            bg=SURFACE,
            fg=INK,
            font=f(26, "bold"),
            anchor="w",
        ).pack(anchor="w", **pad)
        lines = []
        if report.target_low is not None and report.target_high is not None:
            lines.append(
                f"Client's expected range: {_money(report.target_low)} – "
                f"{_money(report.target_high)}"
            )
            variance = report.headline_variance_pct
            if report.headline_in_range:
                lines.append("The projection falls inside the client's expected range.")
            elif variance < 0:
                lines.append(f"Variance: {abs(variance):.1f}% below the range floor.")
            else:
                lines.append(f"Variance: {abs(variance):.1f}% above the range ceiling.")
        first, last = report.historical[0].month, report.historical[-1].month
        lines.append(
            f"Recorded history: {len(report.historical)} months ({first:%b %Y} – {last:%b %Y}), "
            f"total {_money(report.historical_total)}."
        )
        for line in lines:
            tk.Label(body, text=line, bg=SURFACE, fg=INK, font=f(10), anchor="w").pack(
                anchor="w", **pad
            )

        # B. methods
        section("EVERY METHOD, NOTHING DISCARDED")
        mid = report.target_mid
        vs_label = "vs midpoint" if mid is None else f"vs mid {_money(mid)}"
        rows = [("Method", f"{report.horizon}-mo total", vs_label, "In range")]
        highlight = None
        for i, row in enumerate(report.methods, start=1):
            if row.error is not None:
                rows.append((row.label, f"could not run: {row.error}", "—", "—"))
                continue
            label = f"{row.label}   ● presented" if row.presented else row.label
            if row.presented:
                highlight = i
            variance = (
                "—"
                if row.variance_vs_midpoint_pct is None
                else f"{row.variance_vs_midpoint_pct:+.1f}%"
            )
            in_range = "—" if row.in_range is None else ("yes" if row.in_range else "no")
            rows.append((label, _money(row.total), variance, in_range))
        self._table(
            body,
            rows,
            aligns=("w", "e", "e", "center"),
            widths=(30, 13, 15, 8),
            highlight_row=highlight,
        ).pack(anchor="w", pady=(8, 4), **pad)
        tk.Label(
            body,
            text=f"Presented method rationale: {report.presented.rationale}",
            bg=SURFACE,
            fg=INK2,
            font=f(9),
            anchor="w",
            justify="left",
            wraplength=630,
        ).pack(anchor="w", pady=(4, 0), **pad)

        # C. monthly view
        section("MONTHLY VIEW — RECORDED, THEN PROJECTED")
        legend = tk.Frame(body, bg=SURFACE)
        legend.pack(anchor="w", pady=(8, 0), **pad)
        legend_items = (
            (BLUE, "Recorded"),
            (BLUE_LIGHT, f"Projected ({report.presented.label})"),
        )
        for color, label in legend_items:
            tk.Frame(legend, bg=color, width=10, height=10).pack(side="left", padx=(0, 5))
            tk.Label(legend, text=label, bg=SURFACE, fg=INK2, font=f(9)).pack(
                side="left", padx=(0, 14)
            )
        self._chart(body, report).pack(anchor="w", pady=(6, 0), **pad)

        rows = [("Month", "Deals", "Gross", "Commission")]
        for e in report.historical:
            rows.append(
                (f"{e.month:%b %Y}", str(e.deal_count), _money(e.gross), _money(e.commission_2dp))
            )
        rows.append(("Total", "", "", _money(report.historical_total)))
        self._table(body, rows, aligns=("w", "e", "e", "e"), widths=(12, 7, 15, 14)).pack(
            anchor="w", pady=(12, 0), **pad
        )
        rows = [("Month", "Commission (projected)")]
        for month, value in report.projected:
            rows.append((f"{month:%b %Y}", _money(value)))
        rows.append((f"{report.horizon}-month total", _money(report.presented.total)))
        self._table(body, rows, aligns=("w", "e"), widths=(18, 22)).pack(
            anchor="w", pady=(12, 0), **pad
        )
        tk.Label(
            body,
            text=(
                "Monthly figures are rounded to the cent; totals are computed on the "
                "unrounded values, so summing a printed column can differ by a few cents."
            ),
            bg=SURFACE,
            fg=MUTED,
            font=f(8),
            anchor="w",
            justify="left",
            wraplength=630,
        ).pack(anchor="w", pady=(6, 0), **pad)

        # D. flags
        section("CONFIRM WITH CLIENT")
        if report.flags:
            for i, flag in enumerate(report.flags, start=1):
                tk.Label(
                    body,
                    text=f"{i}.  {flag.question}",
                    bg=SURFACE,
                    fg=INK,
                    font=f(10),
                    anchor="w",
                    justify="left",
                    wraplength=630,
                ).pack(anchor="w", pady=(8, 0), **pad)
        else:
            tk.Label(
                body,
                text="No flags raised by this run.",
                bg=SURFACE,
                fg=INK,
                font=f(10),
                anchor="w",
            ).pack(anchor="w", pady=(8, 0), **pad)
        tk.Frame(body, bg=SURFACE, height=18).pack()

        view.pack(fill="both", expand=True)
        self.root.geometry("788x680")

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
