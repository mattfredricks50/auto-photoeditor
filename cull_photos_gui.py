"""
GUI for culling blurry / blown-out photos (v3).

New in v3:
- Dehaze button: fixes hazy images, saves to ./dehazed subfolder
- Click any thumbnail to view full-size preview (arrow keys to navigate)
- Per-row Keep / Move toggle — scan in dry-run, override decisions, then Apply

Run:
    pip install opencv-python numpy pillow
    python cull_photos_gui.py
"""

import shutil
import threading
from pathlib import Path
from tkinter import (Tk, Toplevel, filedialog, StringVar, DoubleVar,
                     BooleanVar, IntVar, ttk, messagebox, Canvas)

import cv2
from PIL import Image, ImageTk

# All image algorithms are shared with the CLI in photo_core.py
from photo_core import (EXTS, blur_score, blown_ratio, haze_score,
                        dehaze, touch_up, haze_action)

THUMB_SIZE = 140
PREVIEW_MAX = 900


# ---------- Thumbnails (UI-only) ----------

def make_thumb(path, size=THUMB_SIZE):
    try:
        img = Image.open(path)
        img.thumbnail((size, size))
        return ImageTk.PhotoImage(img)
    except Exception:
        return None


# ---------- App ----------

class Row:
    """One image row in the results list."""
    def __init__(self, path, flagged, detail, b=None, x=None, readable=True):
        self.path = path
        self.flagged = flagged       # AI's decision
        self.override_keep = False   # user said keep this flagged one
        self.override_move = False   # user said move this unflagged one
        self.detail = detail
        self.b = b                   # cached blur score (None if unreadable)
        self.x = x                   # cached blown ratio
        self.readable = readable

    @property
    def will_move(self):
        if self.flagged and self.override_keep:
            return False
        if not self.flagged and self.override_move:
            return True
        return self.flagged


class App:
    def __init__(self, root):
        self.root = root
        root.title("Photo Culler")
        root.geometry("1000x750")

        self.folder = StringVar()
        self.blur = DoubleVar(value=100.0)
        self.blown = DoubleVar(value=0.40)
        self.progress = IntVar(value=0)
        self.stop_flag = threading.Event()
        self.thumbs = []
        self.rows = []            # list[Row]
        self.preview_imgs = []    # keep refs for full-size preview windows

        self._build_ui()

    # ----- UI layout -----

    def _build_ui(self):
        root = self.root

        # Folder
        frm = ttk.Frame(root, padding=10); frm.pack(fill="x")
        ttk.Label(frm, text="Folder:").pack(side="left")
        ttk.Entry(frm, textvariable=self.folder, width=60).pack(
            side="left", padx=5, fill="x", expand=True)
        ttk.Button(frm, text="Browse…", command=self.pick_folder).pack(side="left")

        # Sliders
        sld = ttk.LabelFrame(root, text="Thresholds", padding=10)
        sld.pack(fill="x", padx=10)

        ttk.Label(sld, text="Blur (lower = stricter):").grid(row=0, column=0, sticky="w")
        self.blur_lbl = ttk.Label(sld, text="100"); self.blur_lbl.grid(row=0, column=2, padx=5)
        ttk.Scale(sld, from_=10, to=500, variable=self.blur, orient="horizontal",
                  length=400, command=self._on_blur
                  ).grid(row=0, column=1, sticky="ew", padx=5)

        ttk.Label(sld, text="Blown-out (% saturated):").grid(row=1, column=0, sticky="w", pady=(8,0))
        self.blown_lbl = ttk.Label(sld, text="40%"); self.blown_lbl.grid(row=1, column=2, padx=5, pady=(8,0))
        ttk.Scale(sld, from_=0.10, to=0.90, variable=self.blown, orient="horizontal",
                  length=400, command=self._on_blown
                  ).grid(row=1, column=1, sticky="ew", padx=5, pady=(8,0))
        sld.columnconfigure(1, weight=1)

        # Buttons
        opt = ttk.Frame(root, padding=10); opt.pack(fill="x")
        self.scan_btn = ttk.Button(opt, text="1. Scan (preview)", command=self.scan)
        self.scan_btn.pack(side="left")
        self.apply_btn = ttk.Button(opt, text="2. Apply moves",
                                    command=self.apply_moves, state="disabled")
        self.apply_btn.pack(side="left", padx=5)
        self.dehaze_btn = ttk.Button(opt, text="Dehaze + touch-up folder",
                                     command=self.run_dehaze)
        self.dehaze_btn.pack(side="left", padx=15)
        self.stop_btn = ttk.Button(opt, text="Stop", command=self.stop, state="disabled")
        self.stop_btn.pack(side="right")

        self.pbar = ttk.Progressbar(root, variable=self.progress, maximum=100)
        self.pbar.pack(fill="x", padx=10, pady=(0,5))

        # Status line
        self.status = ttk.Label(root, text="Ready.", anchor="w")
        self.status.pack(fill="x", padx=10)

        # Scrollable rows
        log_frame = ttk.Frame(root); log_frame.pack(fill="both", expand=True, padx=10, pady=10)
        self.canvas = Canvas(log_frame, highlightthickness=0)
        sb = ttk.Scrollbar(log_frame, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y"); self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = ttk.Frame(self.canvas)
        self.canvas.create_window((0,0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(
            scrollregion=self.canvas.bbox("all")))
        self.canvas.bind_all("<MouseWheel>",
                             lambda e: self.canvas.yview_scroll(int(-e.delta/120), "units"))

    # ----- Helpers -----

    def _on_blur(self, v):
        self.blur_lbl.config(text=f"{float(v):.0f}")
        self.recompute()

    def _on_blown(self, v):
        self.blown_lbl.config(text=f"{float(v)*100:.0f}%")
        self.recompute()

    def pick_folder(self):
        f = filedialog.askdirectory()
        if f: self.folder.set(f)

    def set_status(self, text):
        self.root.after(0, lambda: self.status.config(text=text))

    def clear_rows(self):
        for c in self.inner.winfo_children(): c.destroy()
        self.thumbs.clear()
        self.rows.clear()

    def stop(self):
        self.stop_flag.set()
        self.stop_btn.config(state="disabled")

    # ----- Full-size preview popup -----

    def open_preview(self, idx):
        if idx < 0 or idx >= len(self.rows): return
        row = self.rows[idx]
        if not row.path.exists(): return

        win = Toplevel(self.root)
        win.title(row.path.name)
        try:
            img = Image.open(row.path)
            img.thumbnail((PREVIEW_MAX, PREVIEW_MAX))
            photo = ImageTk.PhotoImage(img)
        except Exception as e:
            ttk.Label(win, text=f"Could not open: {e}").pack(padx=20, pady=20)
            return
        self.preview_imgs.append(photo)
        ttk.Label(win, image=photo).pack()
        ttk.Label(win, text=row.detail).pack(pady=5)

        def go(delta):
            win.destroy()
            self.open_preview(idx + delta)
        win.bind("<Left>", lambda e: go(-1))
        win.bind("<Right>", lambda e: go(1))
        win.bind("<Escape>", lambda e: win.destroy())
        win.focus_set()

    # ----- Row rendering -----

    def add_row(self, row):
        idx = len(self.rows)
        self.rows.append(row)

        frame = ttk.Frame(self.inner, relief="flat", borderwidth=1)
        frame.grid(row=idx, column=0, sticky="ew", pady=2)
        self.inner.columnconfigure(0, weight=1)

        # Thumbnail (clickable)
        thumb = make_thumb(row.path)
        if thumb:
            self.thumbs.append(thumb)
            lbl = ttk.Label(frame, image=thumb, cursor="hand2")
            lbl.grid(row=0, column=0, padx=5, rowspan=2)
            lbl.bind("<Button-1>", lambda e, i=idx: self.open_preview(i))

        # Status label
        status_lbl = ttk.Label(frame, width=14,
                               font=("TkDefaultFont", 10, "bold"))
        status_lbl.grid(row=0, column=1, sticky="w", padx=5)

        detail_lbl = ttk.Label(frame, text=row.detail, font=("Menlo", 10))
        detail_lbl.grid(row=1, column=1, sticky="w", padx=5)

        # Override buttons
        btns = ttk.Frame(frame)
        btns.grid(row=0, column=2, rowspan=2, padx=10, sticky="e")
        keep_btn = ttk.Button(btns, text="Keep", width=6,
                              command=lambda i=idx: self.toggle(i, "keep"))
        move_btn = ttk.Button(btns, text="Move", width=6,
                              command=lambda i=idx: self.toggle(i, "move"))
        keep_btn.pack(side="left", padx=2)
        move_btn.pack(side="left", padx=2)
        frame.columnconfigure(1, weight=1)

        row._status_lbl = status_lbl
        row._detail_lbl = detail_lbl
        row._keep_btn = keep_btn
        row._move_btn = move_btn
        self.refresh_row(idx)

    def refresh_row(self, idx):
        row = self.rows[idx]
        if row.will_move:
            txt, color = ("WOULD MOVE", "#cc6600")
        else:
            txt, color = ("KEEP", "#2a8a2a")
        if (row.flagged and row.override_keep) or (not row.flagged and row.override_move):
            txt += " *"  # asterisk = overridden
        row._status_lbl.config(text=txt, foreground=color)

    def recompute(self):
        """Re-evaluate every scanned row against the current slider values.

        Uses the cached blur/blown scores, so this is instant — no images are
        re-read. User Keep/Move overrides are preserved. Called live while the
        sliders move."""
        if not self.rows:
            return
        blur_thr = self.blur.get()
        blown_thr = self.blown.get()
        flagged_count = 0
        for idx, row in enumerate(self.rows):
            if not row.readable:
                continue
            reasons = []
            if row.b < blur_thr: reasons.append(f"blurry({row.b:.0f})")
            if row.x >= blown_thr: reasons.append(f"blown({row.x*100:.0f}%)")
            row.flagged = bool(reasons)
            if row.flagged: flagged_count += 1
            row.detail = f"{row.path.name}  blur={row.b:.0f} blown={row.x*100:.0f}%"
            if reasons: row.detail += f"  [{', '.join(reasons)}]"
            row._detail_lbl.config(text=row.detail)
            self.refresh_row(idx)
        self.set_status(f"{flagged_count} flagged at current thresholds. "
                        f"Adjust sliders freely, then click Apply.")

    def toggle(self, idx, action):
        row = self.rows[idx]
        if action == "keep":
            row.override_keep = not row.override_keep
            row.override_move = False
        else:
            row.override_move = not row.override_move
            row.override_keep = False
        self.refresh_row(idx)

    # ----- Scan (dry-run only) -----

    def scan(self):
        if not self.folder.get():
            messagebox.showwarning("No folder", "Pick a folder first."); return
        self.scan_btn.config(state="disabled")
        self.apply_btn.config(state="disabled")
        self.dehaze_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.stop_flag.clear()
        self.clear_rows()
        threading.Thread(target=self._scan_thread, daemon=True).start()

    def _scan_thread(self):
        folder = Path(self.folder.get())
        blur_thr = self.blur.get()
        blown_thr = self.blown.get()

        images = sorted([p for p in folder.iterdir() if p.suffix.lower() in EXTS])
        self.set_status(f"Scanning {len(images)} images…")

        flagged_count = 0
        for i, p in enumerate(images):
            if self.stop_flag.is_set():
                self.set_status("Stopped."); break

            img = cv2.imread(str(p))
            if img is None:
                row = Row(p, False, f"{p.name}  (unreadable)", readable=False)
            else:
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                b = blur_score(gray)
                x = blown_ratio(gray)
                reasons = []
                if b < blur_thr: reasons.append(f"blurry({b:.0f})")
                if x >= blown_thr: reasons.append(f"blown({x*100:.0f}%)")
                flagged = bool(reasons)
                if flagged: flagged_count += 1
                detail = f"{p.name}  blur={b:.0f} blown={x*100:.0f}%"
                if reasons: detail += f"  [{', '.join(reasons)}]"
                row = Row(p, flagged, detail, b=b, x=x)

            self.root.after(0, self.add_row, row)
            self.progress.set(int((i+1) / max(len(images), 1) * 100))

        self.set_status(f"Scan complete. {flagged_count} flagged. "
                        f"Review with Keep/Move, then click Apply.")
        self.root.after(0, lambda: self.scan_btn.config(state="normal"))
        self.root.after(0, lambda: self.apply_btn.config(state="normal"))
        self.root.after(0, lambda: self.dehaze_btn.config(state="normal"))
        self.root.after(0, lambda: self.stop_btn.config(state="disabled"))

    # ----- Apply moves -----

    def apply_moves(self):
        to_move = [r for r in self.rows if r.will_move]
        if not to_move:
            messagebox.showinfo("Nothing to do", "No files marked to move."); return
        if not messagebox.askyesno("Confirm",
                                   f"Move {len(to_move)} files to ./trash?"):
            return
        folder = Path(self.folder.get())
        trash = folder / "trash"; trash.mkdir(exist_ok=True)
        moved = 0
        for r in to_move:
            try:
                shutil.move(str(r.path), str(trash / r.path.name))
                moved += 1
            except Exception as e:
                print(f"Failed to move {r.path}: {e}")
        self.set_status(f"Moved {moved} files to {trash}.")
        self.apply_btn.config(state="disabled")

    # ----- Dehaze -----

    def run_dehaze(self):
        if not self.folder.get():
            messagebox.showwarning("No folder", "Pick a folder first."); return
        self.scan_btn.config(state="disabled")
        self.dehaze_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.stop_flag.clear()
        threading.Thread(target=self._dehaze_thread, daemon=True).start()

    def _dehaze_thread(self):
        folder = Path(self.folder.get())
        dehaze_dir = folder / "dehazed"
        touchup_dir = folder / "touched_up"
        images = sorted([p for p in folder.iterdir() if p.suffix.lower() in EXTS])
        self.set_status(f"Dehazing {len(images)} images…")
        n_dehaze = n_touch = 0
        for i, p in enumerate(images):
            if self.stop_flag.is_set():
                self.set_status("Dehaze stopped."); break
            img = cv2.imread(str(p))
            if img is None:
                continue
            action = haze_action(haze_score(img))
            if action == "dehaze":
                dehaze_dir.mkdir(exist_ok=True)
                cv2.imwrite(str(dehaze_dir / p.name), dehaze(img))
                n_dehaze += 1
            elif action == "touch_up":
                # Borderline: not hazy enough for a full dehaze, so dehaze + auto levels
                touchup_dir.mkdir(exist_ok=True)
                cv2.imwrite(str(touchup_dir / p.name), touch_up(img))
                n_touch += 1
            self.progress.set(int((i+1) / max(len(images), 1) * 100))
            self.set_status(f"Dehazing… {i+1}/{len(images)}  "
                            f"(dehazed {n_dehaze}, touched up {n_touch})")
        self.set_status(f"Dehaze complete. {n_dehaze} dehazed -> {dehaze_dir.name}/, "
                        f"{n_touch} touched up -> {touchup_dir.name}/.")
        self.root.after(0, lambda: self.scan_btn.config(state="normal"))
        self.root.after(0, lambda: self.dehaze_btn.config(state="normal"))
        self.root.after(0, lambda: self.stop_btn.config(state="disabled"))


if __name__ == "__main__":
    root = Tk()
    App(root)
    root.mainloop()
