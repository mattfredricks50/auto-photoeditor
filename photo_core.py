"""
Shared image analysis + processing for the photo culler.

Imported by BOTH cull_photos.py (CLI) and cull_photos_gui.py (GUI) so every
algorithm lives in exactly one place. If you change scoring or a filter, change
it here and both front-ends pick it up.
"""

import cv2
import numpy as np

# Image types we handle
EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}

# Defaults for the dehaze / touch-up pass
DEHAZE_THRESHOLD = 0.35   # haze score above this -> full dehaze
TOUCHUP_MARGIN = 0.30     # "borderline" = within this fraction below the threshold


# ---------- Scoring ----------

def blur_score(gray):
    """Laplacian variance — lower = blurrier."""
    return cv2.Laplacian(gray, cv2.CV_64F).var()


def blown_ratio(gray):
    """Fraction of pixels at the extremes (overexposed or fully black)."""
    total = gray.size
    blown = np.sum(gray >= 250) / total
    crushed = np.sum(gray <= 5) / total
    return max(blown, crushed)


def haze_score(bgr):
    """Higher = hazier. Combines low contrast + low saturation."""
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    contrast = gray.std()             # haze flattens contrast
    saturation = hsv[..., 1].mean()   # haze desaturates
    c_norm = max(0, 1 - contrast / 60)
    s_norm = max(0, 1 - saturation / 80)
    return (c_norm + s_norm) / 2


# ---------- Filters ----------

def dehaze(bgr):
    """CLAHE on luminance + saturation boost."""
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    l = clahe.apply(l)
    lab = cv2.merge([l, a, b])
    out = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    hsv = cv2.cvtColor(out, cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[..., 1] = np.clip(hsv[..., 1] * 1.35, 0, 255)
    return cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)


def auto_contrast_brightness(bgr, clip_percent=1.0):
    """Per-image contrast/brightness stretch via percentile clipping.

    Maps the clip_percent .. (100-clip_percent) brightness range onto 0..255,
    which fixes flat / dull exposure without blowing highlights."""
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    lo = np.percentile(gray, clip_percent)
    hi = np.percentile(gray, 100 - clip_percent)
    if hi <= lo:
        return bgr
    alpha = 255.0 / (hi - lo)
    beta = -lo * alpha
    return cv2.convertScaleAbs(bgr, alpha=alpha, beta=beta)


def touch_up(bgr):
    """Borderline-haze fix: full dehaze, then auto contrast/brightness."""
    return auto_contrast_brightness(dehaze(bgr))


# ---------- Decisions ----------

def haze_action(h, haze_thr=DEHAZE_THRESHOLD, touchup_margin=TOUCHUP_MARGIN):
    """Classify a haze score into the processing action to take.

    Returns:
        "dehaze"   -> clearly hazy, run the full dehaze
        "touch_up" -> borderline (just under the cutoff), run dehaze + auto levels
        None       -> clear enough, leave it alone
    """
    if h > haze_thr:
        return "dehaze"
    if h > haze_thr * (1 - touchup_margin):
        return "touch_up"
    return None
