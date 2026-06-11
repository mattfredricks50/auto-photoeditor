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
   Nothing is moved yet.
4. **Review** — click any thumbnail for a full-size preview (← / → to flip
   through, Esc to close). Use each row's **Keep** / **Move** buttons to override
   the automatic decision; overridden rows are marked with `*`.
5. **2. Apply moves** — confirms, then moves everything marked *move* into
   `trash/`.

**Dehaze:** click **"Dehaze folder →/dehazed"** to process hazy images and save
fixed copies into a `dehazed/` subfolder. Originals are untouched.

### CLI

```bat
python cull_photos.py "C:\path\to\photos"

REM Preview only — print decisions without moving anything:
python cull_photos.py "C:\path\to\photos" --dry-run

REM Tune sensitivity:
python cull_photos.py "C:\path\to\photos" --blur 100 --blown 0.40
```

---

## How the scoring works

| Metric        | What it measures                                              | Flagged when            |
|---------------|--------------------------------------------------------------|-------------------------|
| **Blur**      | Variance of the Laplacian — low variance = soft/blurry image | `score < --blur` (def. 100) |
| **Blown-out** | Fraction of near-white (≥250) or near-black (≤5) pixels       | `ratio >= --blown` (def. 0.40) |
| **Haze**      | Low contrast + low saturation (dehaze feature only)          | processed when score > 0.35 |

**Tuning tips:**

- Too many *good* photos flagged as blurry? **Lower** the blur threshold.
- Not catching enough blurry photos? **Raise** it.

---

## Files

| File                  | Purpose                                          |
|-----------------------|--------------------------------------------------|
| `cull_photos_gui.py`  | The GUI app                                      |
| `cull_photos.py`      | Command-line version                             |
| `install.bat`         | One-time dependency installer                    |
| `run_gui.bat`         | Launches the GUI with the correct Python         |
| `requirements.txt`    | Python dependencies                              |

Output folders created next to your photos:

- `trash/` — photos you moved (safe to delete once you've checked them)
- `dehazed/` — dehazed copies (originals untouched)

---

## Safety

Nothing is ever permanently deleted. Flagged photos are **moved** to `trash/`,
and dehazed images are written as **new copies**. You can always recover or undo
by moving files back out of `trash/`.
