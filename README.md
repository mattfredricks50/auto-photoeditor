# Auto PhotoEditor

A small tool for **culling bad photos** and **fixing hazy ones**. It scores every
image in a folder for blur, exposure, and haze, then helps you move the bad ones
to a `trash/` folder (originals are never deleted) and optionally produce dehazed
copies.

There are two ways to use it:

- **GUI** (`cull_photos_gui.py`) — recommended. Scan, review with thumbnails,
  override decisions, then apply.
- **CLI** (`cull_photos.py`) — quick batch runs from a terminal.

---

## First-time setup (Windows)

1. Make sure **Python 3** is installed. Get it from
   [python.org](https://www.python.org/downloads/) and check **"Add Python to PATH"**
   during install.
2. Double-click **`install.bat`**. This installs the required packages
   (`opencv-python`, `numpy`, `pillow`).

That's it. You only need to do this once.

> **Why double-clicking the `.py` didn't open:** Windows runs double-clicked
> `.py` files through the `py` launcher, which may point at a different Python
> than the one where the packages are installed. The result is a window that
> flashes and closes (a hidden `ModuleNotFoundError: No module named 'cv2'`).
> Using `install.bat` + `run_gui.bat` guarantees the same interpreter is used
> for both, so this can't happen.

---

## Running it

### GUI (recommended)

Double-click **`run_gui.bat`** (not the `.py` file).

Workflow:

1. **Browse** to the folder of photos.
2. Adjust the **Blur** and **Blown-out** sliders if needed (defaults are a good start).
3. **1. Scan (preview)** — analyzes every image and lists them with thumbnails.
   Nothing is moved yet. **After scanning, you can drag the sliders and the
   keep/move decisions update live** (it re-thresholds the already-computed
   scores, so it's instant — no need to re-scan).
4. **Review** — click any thumbnail for a full-size preview (← / → to flip
   through, Esc to close). Use each row's **Keep** / **Move** buttons to override
   the automatic decision; overridden rows are marked with `*`.
5. **2. Apply moves** — confirms, then moves everything marked *move* into
   `trash/`.

**Dehaze + touch-up:** click **"Dehaze + touch-up folder"** to process hazy
images. Clearly hazy ones get a full dehaze saved to `dehazed/`; borderline ones
(just under the cutoff) get dehaze **plus** auto contrast/brightness saved to
`touched_up/`. Originals are untouched.

### CLI

```bat
python cull_photos.py "C:\path\to\photos"

REM Preview only — print decisions without moving anything:
python cull_photos.py "C:\path\to\photos" --dry-run

REM Tune sensitivity:
python cull_photos.py "C:\path\to\photos" --blur 100 --blown 0.40

REM Dehaze pass (instead of culling):
REM   clearly hazy   -> ./dehazed
REM   borderline     -> ./touched_up   (dehaze + auto contrast/brightness)
python cull_photos.py "C:\path\to\photos" --dehaze
python cull_photos.py "C:\path\to\photos" --dehaze --haze 0.35 --touchup-margin 0.30 --dry-run
```

The CLI and GUI now share all image algorithms (see Architecture below), so
they always behave identically. The GUI's clickable previews and per-row
Keep/Move overrides are interactive-only and have no CLI equivalent.

---

## How the scoring works

| Metric        | What it measures                                              | Flagged when            |
|---------------|--------------------------------------------------------------|-------------------------|
| **Blur**      | Variance of the Laplacian — low variance = soft/blurry image | `score < --blur` (def. 100) |
| **Blown-out** | Fraction of near-white (≥250) or near-black (≤5) pixels       | `ratio >= --blown` (def. 0.40) |
| **Haze**      | Low contrast + low saturation (dehaze feature only)          | `> 0.35` dehaze; `> 0.245` touch up |

**Tuning tips:**

- Too many *good* photos flagged as blurry? **Lower** the blur threshold.
- Not catching enough blurry photos? **Raise** it.

---

## Files

| File                  | Purpose                                          |
|-----------------------|--------------------------------------------------|
| `photo_core.py`       | **Shared** image algorithms (scoring + filters)  |
| `cull_photos_gui.py`  | The GUI app (imports `photo_core`)               |
| `cull_photos.py`      | Command-line version (imports `photo_core`)      |
| `install.bat`         | One-time dependency installer                    |
| `run_gui.bat`         | Launches the GUI with the correct Python         |
| `requirements.txt`    | Python dependencies                              |

### Architecture

All scoring (`blur_score`, `blown_ratio`, `haze_score`) and all filters
(`dehaze`, `auto_contrast_brightness`, `touch_up`) live in **`photo_core.py`**.
Both the CLI and GUI import from it, so there's only one place to change an
algorithm and both front-ends stay in sync. The `haze_action()` helper there
decides, per image, whether to fully dehaze, touch up, or leave it alone.

Output folders created next to your photos:

- `trash/` — photos you moved (safe to delete once you've checked them)
- `dehazed/` — fully dehazed copies (originals untouched)
- `touched_up/` — borderline images: dehaze + auto contrast/brightness

---

## Safety

Nothing is ever permanently deleted. Flagged photos are **moved** to `trash/`,
and dehazed images are written as **new copies**. You can always recover or undo
by moving files back out of `trash/`.
