#!/usr/bin/env python3
"""GUI entry point for the iEEG structural connectivity pipeline.

Separate from the core DWI pipeline. Only for subjects with implanted
electrodes (electrodes2ROI.csv from ieeg_recon module 3). Subjects
without electrode data are automatically skipped.

Requires the DWI pipeline to have run first (tracking + alignment).

Launch:
  uv run dwi-ieeg-connectivity
"""

import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
from pathlib import Path


class IEEGConnectivityGUI:

    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("iEEG Structural Connectivity Pipeline")
        root.resizable(True, True)

        frame = tk.Frame(root, padx=16, pady=12)
        frame.pack(fill=tk.BOTH, expand=True)

        row = 0

        # ── Subjects ──────────────────────────────────────────────────
        tk.Label(frame, text="Subjects", anchor="w").grid(
            row=row, column=0, sticky="w", pady=(0, 4))
        row += 1
        self.subjects_var = tk.StringVar(
            value="sub-RID0445, sub-RID1046, sub-RID1081, sub-RID1116, sub-RID1171")
        tk.Entry(frame, textvariable=self.subjects_var, width=60).grid(
            row=row, column=0, columnspan=2, sticky="we", pady=(0, 8))
        row += 1

        # ── BIDS path ────────────────────────────────────────────────
        tk.Label(frame, text="BIDS Path", anchor="w").grid(
            row=row, column=0, sticky="w", pady=(0, 4))
        row += 1
        bids_frame = tk.Frame(frame)
        bids_frame.grid(row=row, column=0, columnspan=2, sticky="we", pady=(0, 8))
        self.bids_var = tk.StringVar()
        tk.Entry(bids_frame, textvariable=self.bids_var, width=48).pack(
            side=tk.LEFT, fill=tk.X, expand=True)
        tk.Button(bids_frame, text="Browse…", command=self._browse_bids).pack(
            side=tk.LEFT, padx=(6, 0))
        row += 1

        # ── Config (optional) ────────────────────────────────────────
        tk.Label(frame, text="Config (optional)", anchor="w").grid(
            row=row, column=0, sticky="w", pady=(0, 4))
        row += 1
        cfg_frame = tk.Frame(frame)
        cfg_frame.grid(row=row, column=0, columnspan=2, sticky="we", pady=(0, 8))
        self.config_var = tk.StringVar()
        tk.Entry(cfg_frame, textvariable=self.config_var, width=48).pack(
            side=tk.LEFT, fill=tk.X, expand=True)
        tk.Button(cfg_frame, text="Browse…", command=self._browse_config).pack(
            side=tk.LEFT, padx=(6, 0))
        row += 1

        # ── Sphere diameters ─────────────────────────────────────────
        tk.Label(frame, text="Sphere Diameters (mm)", anchor="w").grid(
            row=row, column=0, sticky="w", pady=(0, 4))
        row += 1
        sphere_frame = tk.Frame(frame)
        sphere_frame.grid(row=row, column=0, columnspan=2, sticky="w", pady=(0, 8))
        self.sph_3 = tk.BooleanVar(value=True)
        self.sph_5 = tk.BooleanVar(value=True)
        self.sph_10 = tk.BooleanVar(value=False)
        tk.Checkbutton(sphere_frame, text="3 mm", variable=self.sph_3).pack(
            side=tk.LEFT, padx=(0, 12))
        tk.Checkbutton(sphere_frame, text="5 mm", variable=self.sph_5).pack(
            side=tk.LEFT, padx=(0, 12))
        tk.Checkbutton(sphere_frame, text="10 mm", variable=self.sph_10).pack(
            side=tk.LEFT, padx=(0, 12))

        tk.Label(sphere_frame, text="  Other:").pack(side=tk.LEFT)
        self.sph_custom_var = tk.StringVar()
        tk.Entry(sphere_frame, textvariable=self.sph_custom_var, width=10).pack(
            side=tk.LEFT, padx=(4, 0))
        row += 1

        # ── Streamlines ──────────────────────────────────────────────
        tk.Label(frame, text="Streamlines (if tracking needs to re-run)",
                 anchor="w").grid(row=row, column=0, sticky="w", pady=(0, 4))
        row += 1
        self.streamlines_var = tk.StringVar(value="2500000")
        tk.Entry(frame, textvariable=self.streamlines_var, width=20).grid(
            row=row, column=0, sticky="w", pady=(0, 12))
        row += 1

        # ── Run / Quit ───────────────────────────────────────────────
        btn_frame = tk.Frame(frame)
        btn_frame.grid(row=row, column=0, columnspan=2, sticky="we", pady=(0, 8))
        self.run_btn = tk.Button(
            btn_frame, text="Run Pipeline", command=self._run, width=16,
            bg="#4CAF50", fg="white", font=("Helvetica", 12, "bold"))
        self.run_btn.pack(side=tk.LEFT, padx=(0, 8))
        tk.Button(btn_frame, text="Quit", command=root.quit, width=10).pack(
            side=tk.LEFT)
        row += 1

        # ── Log output ───────────────────────────────────────────────
        tk.Label(frame, text="Log", anchor="w").grid(
            row=row, column=0, sticky="w", pady=(4, 2))
        row += 1
        self.log = scrolledtext.ScrolledText(
            frame, height=16, width=72, state=tk.DISABLED, font=("Courier", 11))
        self.log.grid(row=row, column=0, columnspan=2, sticky="nswe")
        frame.rowconfigure(row, weight=1)
        frame.columnconfigure(0, weight=1)

    # ── Callbacks ─────────────────────────────────────────────────────

    def _browse_bids(self):
        path = filedialog.askdirectory(title="Select BIDS directory")
        if path:
            self.bids_var.set(path)

    def _browse_config(self):
        path = filedialog.askopenfilename(
            title="Select setup_environment.json",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")])
        if path:
            self.config_var.set(path)

    def _log(self, msg: str):
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, msg + "\n")
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def _get_sphere_diameters(self) -> list[float]:
        dias = []
        if self.sph_3.get():
            dias.append(3.0)
        if self.sph_5.get():
            dias.append(5.0)
        if self.sph_10.get():
            dias.append(10.0)
        custom = self.sph_custom_var.get().strip()
        if custom:
            for d in custom.split(","):
                try:
                    dias.append(float(d.strip()))
                except ValueError:
                    pass
        return sorted(set(dias))

    def _run(self):
        # Validate
        bids = self.bids_var.get().strip()
        if not bids:
            messagebox.showerror("Error", "BIDS path is required.")
            return
        bids_path = Path(bids)
        if not bids_path.is_dir():
            messagebox.showerror("Error", f"BIDS path not found:\n{bids_path}")
            return

        subjects_raw = self.subjects_var.get().strip()
        if not subjects_raw:
            messagebox.showerror("Error", "At least one subject is required.")
            return
        subjects = [s.strip() for s in subjects_raw.split(",") if s.strip()]

        sphere_dias = self._get_sphere_diameters()
        if not sphere_dias:
            messagebox.showerror("Error", "Select at least one sphere diameter.")
            return

        try:
            n_streamlines = int(self.streamlines_var.get().strip())
        except ValueError:
            messagebox.showerror("Error", "Streamlines must be an integer.")
            return

        config_path = None
        cfg_str = self.config_var.get().strip()
        if cfg_str:
            config_path = Path(cfg_str)

        # Disable button during run
        self.run_btn.configure(state=tk.DISABLED, text="Running…")
        self._log(f"Subjects:          {subjects}")
        self._log(f"BIDS path:         {bids_path}")
        self._log(f"Sphere diameters:  {sphere_dias}")
        self._log("")

        def _worker():
            _redirect_stdout(self._log)
            try:
                from dwi_preprocessing.ieeg_pipeline import run_ieeg_pipeline
                run_ieeg_pipeline(
                    subjects=subjects,
                    bids_path=bids_path,
                    config_path=config_path,
                    sphere_diameters=sphere_dias,
                    n_streamlines=n_streamlines,
                )
                self.root.after(0, lambda: self._log("\nProcessing complete!"))
            except Exception as e:
                self.root.after(0, lambda: self._log(f"\nERROR: {e}"))
                self.root.after(0, lambda: messagebox.showerror("Pipeline Error", str(e)))
            finally:
                _restore_stdout()
                self.root.after(0, lambda: self.run_btn.configure(
                    state=tk.NORMAL, text="Run Pipeline"))

        threading.Thread(target=_worker, daemon=True).start()


# ── Stdout redirect helper ────────────────────────────────────────────

class _StdoutRedirector:
    def __init__(self, callback):
        self._cb = callback
    def write(self, msg):
        if msg.strip():
            self._cb(msg.rstrip("\n"))
    def flush(self):
        pass

_orig_stdout = None
_orig_stderr = None

def _redirect_stdout(callback):
    global _orig_stdout, _orig_stderr
    _orig_stdout = sys.stdout
    _orig_stderr = sys.stderr
    redir = _StdoutRedirector(callback)
    sys.stdout = redir
    sys.stderr = redir

def _restore_stdout():
    global _orig_stdout, _orig_stderr
    if _orig_stdout:
        sys.stdout = _orig_stdout
    if _orig_stderr:
        sys.stderr = _orig_stderr


def main():
    root = tk.Tk()
    IEEGConnectivityGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
