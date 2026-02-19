"""
ui/app.py
Course Search Bot — Professional GUI
Clean, modern dark interface built with tkinter + ttk.
"""
from __future__ import annotations
import csv
import logging
import os
import re
import threading
from queue import Queue, Empty
from tkinter import filedialog, messagebox
import tkinter as tk
import tkinter.ttk as ttk

from fpdf import FPDF

from config.config import AppConfig
from core.indexer import Indexer
from core.search_engine import SearchEngine, SearchResult
from security.storage import MetadataStore

logger = logging.getLogger(__name__)

# ── Colour palette ────────────────────────────────────────────────────────────
BG        = "#0f1117"
PANEL     = "#1a1d27"
BORDER    = "#2a2d3e"
ACCENT    = "#4f8ef7"
ACCENT2   = "#7c5cbf"
SUCCESS   = "#3ecf8e"
WARNING   = "#f0a500"
TEXT      = "#e8eaf0"
SUBTEXT   = "#8890a8"
HIGHLIGHT = "#ffd166"
FONT_MAIN = ("Segoe UI", 10)
FONT_H1   = ("Segoe UI Semibold", 18)
FONT_H2   = ("Segoe UI Semibold", 13)
FONT_MONO = ("Consolas", 9)


class StyledButton(tk.Button):
    def __init__(self, parent, text, command, style="primary", **kw):
        colours = {
            "primary": (ACCENT, "#ffffff"),
            "secondary": (PANEL, TEXT),
            "success": (SUCCESS, "#000000"),
            "danger": ("#e05252", "#ffffff"),
        }
        bg, fg = colours.get(style, colours["primary"])
        super().__init__(
            parent,
            text=text,
            command=command,
            bg=bg,
            fg=fg,
            activebackground=ACCENT2,
            activeforeground="#ffffff",
            relief="flat",
            cursor="hand2",
            font=("Segoe UI Semibold", 10),
            padx=14,
            pady=7,
            **kw,
        )
        self.bind("<Enter>", lambda e: self.config(bg=ACCENT2))
        self.bind("<Leave>", lambda e: self.config(bg=bg))


class App:
    APP_NAME = "Course Search Bot"
    VERSION  = "v2.0"

    def __init__(self):
        self.cfg = AppConfig.from_yaml("config/settings.yaml")
        self.cfg.ensure_dirs()

        logging.basicConfig(level=self.cfg.log_level)

        self.store   = MetadataStore(self.cfg.storage.db_path)
        self.indexer = Indexer(self.cfg, self.store)
        self.engine  = SearchEngine(self.cfg, self.indexer, self.store)

        self._results: list[SearchResult] = []
        self._queue: Queue = Queue()

        self._build_window()

    # ── Window setup ──────────────────────────────────────────────────────────

    def _build_window(self):
        self.root = tk.Tk()
        self.root.title(f"{self.APP_NAME}  {self.VERSION}")
        self.root.geometry("920x720")
        self.root.minsize(760, 580)
        self.root.configure(bg=BG)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Try to set window icon (skip gracefully if not found)
        try:
            self.root.iconbitmap("ui/icon.ico")
        except Exception:
            pass

        self._style_ttk()
        self._build_header()
        self._build_folder_row()
        self._build_index_row()
        self._build_search_row()
        self._build_results_area()
        self._build_statusbar()

    def _style_ttk(self):
        s = ttk.Style()
        s.theme_use("clam")
        s.configure("TProgressbar", troughcolor=PANEL, background=ACCENT, thickness=6)
        s.configure("TEntry", fieldbackground=PANEL, foreground=TEXT, insertcolor=TEXT)

    # ── Header ────────────────────────────────────────────────────────────────

    def _build_header(self):
        hdr = tk.Frame(self.root, bg=PANEL, pady=18)
        hdr.pack(fill="x")

        tk.Label(
            hdr, text="🎓  Course Search Bot",
            bg=PANEL, fg=TEXT,
            font=FONT_H1,
        ).pack(side="left", padx=24)

        tk.Label(
            hdr, text=self.VERSION,
            bg=PANEL, fg=SUBTEXT,
            font=("Segoe UI", 9),
        ).pack(side="left")

        # Chunk count badge
        self.badge_var = tk.StringVar(value="No index loaded")
        tk.Label(
            hdr, textvariable=self.badge_var,
            bg=ACCENT2, fg="#ffffff",
            font=("Segoe UI", 9),
            padx=10, pady=3,
        ).pack(side="right", padx=24)

    # ── Folder row ────────────────────────────────────────────────────────────

    def _build_folder_row(self):
        row = tk.Frame(self.root, bg=BG, pady=14)
        row.pack(fill="x", padx=24)

        tk.Label(row, text="📁  Documents Folder", bg=BG, fg=SUBTEXT,
                 font=("Segoe UI", 9)).pack(anchor="w")

        inner = tk.Frame(row, bg=BORDER, bd=1, relief="flat")
        inner.pack(fill="x", pady=(4, 0))

        self.folder_var = tk.StringVar(value=os.path.abspath("course_docs"))
        entry = tk.Entry(
            inner, textvariable=self.folder_var,
            bg=PANEL, fg=TEXT, insertbackground=TEXT,
            relief="flat", font=FONT_MAIN,
            bd=8,
        )
        entry.pack(side="left", fill="x", expand=True)

        StyledButton(inner, "Browse…", self._browse_folder, style="secondary").pack(
            side="right", padx=4, pady=4
        )

    # ── Index row ─────────────────────────────────────────────────────────────

    def _build_index_row(self):
        row = tk.Frame(self.root, bg=BG, pady=6)
        row.pack(fill="x", padx=24)

        self.progress = ttk.Progressbar(row, mode="indeterminate", length=200)
        self.progress.pack(side="left", fill="x", expand=True, padx=(0, 12))

        StyledButton(row, "⚙  Build / Load Index", self._start_index, style="primary").pack(
            side="right"
        )

    # ── Search row ────────────────────────────────────────────────────────────

    def _build_search_row(self):
        sep = tk.Frame(self.root, bg=BORDER, height=1)
        sep.pack(fill="x", padx=24, pady=10)

        row = tk.Frame(self.root, bg=BG)
        row.pack(fill="x", padx=24, pady=(0, 10))

        tk.Label(row, text="🔍  Search your documents",
                 bg=BG, fg=SUBTEXT, font=("Segoe UI", 9)).pack(anchor="w")

        inner = tk.Frame(row, bg=BORDER, bd=1, relief="flat")
        inner.pack(fill="x", pady=(4, 0))

        self.query_var = tk.StringVar()
        self.query_entry = tk.Entry(
            inner, textvariable=self.query_var,
            bg=PANEL, fg=TEXT, insertbackground=TEXT,
            relief="flat", font=("Segoe UI", 12),
            bd=10,
        )
        self.query_entry.pack(side="left", fill="x", expand=True)
        self.query_entry.bind("<Return>", lambda _: self._search())

        StyledButton(inner, "Search", self._search, style="primary").pack(
            side="right", padx=4, pady=4
        )

    # ── Results area ─────────────────────────────────────────────────────────

    def _build_results_area(self):
        frame = tk.Frame(self.root, bg=BG)
        frame.pack(fill="both", expand=True, padx=24, pady=(0, 8))

        # Toolbar
        bar = tk.Frame(frame, bg=BG)
        bar.pack(fill="x", pady=(0, 6))

        self.result_count_var = tk.StringVar(value="")
        tk.Label(bar, textvariable=self.result_count_var,
                 bg=BG, fg=SUBTEXT, font=("Segoe UI", 9)).pack(side="left")

        StyledButton(bar, "Export CSV", self._export_csv, style="secondary").pack(side="right", padx=(6, 0))
        StyledButton(bar, "Export PDF", self._export_pdf, style="secondary").pack(side="right")

        # Text widget
        txt_frame = tk.Frame(frame, bg=BORDER, bd=1, relief="flat")
        txt_frame.pack(fill="both", expand=True)

        self.results_text = tk.Text(
            txt_frame,
            bg=PANEL, fg=TEXT, insertbackground=TEXT,
            relief="flat", font=FONT_MONO,
            wrap="word", bd=8,
            state="disabled",
            cursor="arrow",
        )
        scroll = tk.Scrollbar(txt_frame, command=self.results_text.yview,
                              bg=PANEL, troughcolor=BG)
        self.results_text.configure(yscrollcommand=scroll.set)

        scroll.pack(side="right", fill="y")
        self.results_text.pack(fill="both", expand=True)

        # Tags
        self.results_text.tag_config("header",   foreground=ACCENT,     font=("Segoe UI Semibold", 10))
        self.results_text.tag_config("score_hi", foreground=SUCCESS,     font=("Segoe UI Semibold", 10))
        self.results_text.tag_config("score_mid",foreground=WARNING,     font=("Segoe UI Semibold", 10))
        self.results_text.tag_config("bold",      font=("Consolas", 9, "bold"), foreground=HIGHLIGHT)
        self.results_text.tag_config("dim",       foreground=SUBTEXT)
        self.results_text.tag_config("divider",   foreground=BORDER)

    # ── Status bar ────────────────────────────────────────────────────────────

    def _build_statusbar(self):
        bar = tk.Frame(self.root, bg=PANEL, pady=5)
        bar.pack(fill="x", side="bottom")
        self.status_var = tk.StringVar(value="Ready — select a folder and build index to begin.")
        tk.Label(bar, textvariable=self.status_var,
                 bg=PANEL, fg=SUBTEXT, font=("Segoe UI", 9)).pack(side="left", padx=16)

    # ── Actions ───────────────────────────────────────────────────────────────

    def _browse_folder(self):
        path = filedialog.askdirectory(title="Select your documents folder")
        if path:
            self.folder_var.set(path)

    def _start_index(self):
        folder = self.folder_var.get().strip()
        if not folder:
            messagebox.showwarning("No Folder", "Please select a documents folder first.")
            return
        if not os.path.isdir(folder):
            try:
                os.makedirs(folder, exist_ok=True)
            except Exception as e:
                messagebox.showerror("Error", f"Cannot create folder:\n{e}")
                return

        self._set_status("Building index… this may take a minute on first run.")
        self.progress.start(12)

        def worker():
            try:
                def on_progress(done, total):
                    pct = int(done / total * 100)
                    self._queue.put(("progress", pct))

                self.engine.load_or_build(folder, progress_cb=on_progress)
                count = self.store.count_chunks()
                self._queue.put(("done", count))
            except Exception as e:
                self._queue.put(("error", str(e)))

        threading.Thread(target=worker, daemon=True).start()
        self.root.after(100, self._poll_queue)

    def _poll_queue(self):
        try:
            while True:
                msg, val = self._queue.get_nowait()
                if msg == "done":
                    self.progress.stop()
                    self.badge_var.set(f"{val:,} chunks indexed")
                    self._set_status(f"✅  Index ready — {val:,} text chunks loaded.")
                    return
                elif msg == "error":
                    self.progress.stop()
                    self._set_status("❌  Error during indexing.")
                    messagebox.showerror("Indexing Error", str(val))
                    return
        except Empty:
            pass
        self.root.after(100, self._poll_queue)

    def _search(self):
        query = self.query_var.get().strip()
        if not query:
            messagebox.showwarning("Empty Query", "Please type something to search for.")
            return
        if not self.engine.is_ready:
            messagebox.showwarning("Not Ready", "Please build the index first.")
            return

        try:
            self._results = self.engine.search(query)
        except Exception as e:
            messagebox.showerror("Search Error", str(e))
            return

        self._render_results(query)

    def _render_results(self, query: str):
        self.results_text.configure(state="normal")
        self.results_text.delete("1.0", "end")

        if not self._results:
            self.results_text.insert("end", "\n  No matching results found.\n  Try different keywords.\n", "dim")
            self.result_count_var.set("0 results")
        else:
            self.result_count_var.set(f"{len(self._results)} result(s) found")
            q_words = re.findall(r"\b\w+\b", query.lower())
            pattern = re.compile(
                r"\b(" + "|".join(re.escape(w) for w in q_words) + r")\b",
                re.IGNORECASE,
            )

            for i, res in enumerate(self._results, start=1):
                score_tag = "score_hi" if res.score >= 0.6 else "score_mid"
                self.results_text.insert("end", f"  [{i}]  ", "dim")
                self.results_text.insert(
                    "end",
                    f"{res.file}  —  Page {res.page}",
                    "header",
                )
                self.results_text.insert("end", "   Score: ", "dim")
                self.results_text.insert("end", f"{res.score:.0%}\n", score_tag)

                # Highlighted context
                ctx = res.context
                last = 0
                for m in pattern.finditer(ctx):
                    s, e = m.start(), m.end()
                    if s > last:
                        self.results_text.insert("end", "  " + ctx[last:s])
                    self.results_text.insert("end", ctx[s:e], "bold")
                    last = e
                self.results_text.insert("end", "  " + ctx[last:] + "\n")
                self.results_text.insert(
                    "end", "  " + "─" * 80 + "\n\n", "divider"
                )

        self.results_text.configure(state="disabled")

    # ── Exports ───────────────────────────────────────────────────────────────

    def _export_csv(self):
        if not self._results:
            messagebox.showwarning("Nothing to Export", "Run a search first.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            title="Save results as CSV",
        )
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["Rank", "File", "Page", "Score", "Context"])
            for i, r in enumerate(self._results, 1):
                w.writerow([i, r.file, r.page, f"{r.score:.4f}", r.context])
        self._set_status(f"✅  Exported {len(self._results)} results to CSV.")
        messagebox.showinfo("Exported", f"Results saved to:\n{path}")

    def _export_pdf(self):
        if not self._results:
            messagebox.showwarning("Nothing to Export", "Run a search first.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf")],
            title="Save results as PDF",
        )
        if not path:
            return

        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()
        pdf.set_font("Arial", "B", 16)
        pdf.cell(0, 12, "Course Search Bot — Results", ln=True, align="C")
        pdf.set_font("Arial", "", 9)
        pdf.set_text_color(120, 120, 120)
        pdf.cell(0, 6, f"Total results: {len(self._results)}", ln=True, align="C")
        pdf.ln(6)

        for i, r in enumerate(self._results, 1):
            pdf.set_font("Arial", "B", 11)
            pdf.set_text_color(30, 30, 30)
            pdf.cell(0, 8, f"[{i}] {r.file}  —  Page {r.page}  (Score: {r.score:.0%})", ln=True)
            pdf.set_font("Arial", "", 9)
            pdf.set_text_color(60, 60, 60)
            safe_ctx = r.context.encode("latin-1", errors="replace").decode("latin-1")
            pdf.multi_cell(0, 5, safe_ctx)
            pdf.ln(4)
            pdf.set_draw_color(200, 200, 200)
            pdf.line(10, pdf.get_y(), 200, pdf.get_y())
            pdf.ln(4)

        pdf.output(path)
        self._set_status(f"✅  Exported {len(self._results)} results to PDF.")
        messagebox.showinfo("Exported", f"Results saved to:\n{path}")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _set_status(self, msg: str):
        self.status_var.set(msg)
        self.root.update_idletasks()

    def _on_close(self):
        self.store.close()
        self.root.destroy()

    def run(self):
        self.root.mainloop()
