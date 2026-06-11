"""
Move blurry or blown-out images to a trash folder.

Usage:
    python cull_photos.py /path/to/photos
    python cull_photos.py /path/to/photos --blur 100 --blown 0.40 --dry-run

    # Dehaze hazy images into a 'dehazed' subfolder (instead of culling):
    python cull_photos.py /path/to/photos --dehaze
    python cull_photos.py /path/to/photos --dehaze --haze 0.35 --dry-run

Tune --blur up if too few flagged, down if too many.
"""

import argparse
import shutil
from pathlib import Path
import cv2
import numpy as np

EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}


def blur_score(gray):
    # Laplacian variance — lower = blurrier
    return cv2.Laplacian(gray, cv2.CV_64F).var()


def blown_ratio(gray):
    # Fraction of pixels at the extremes (overexposed or fully black)
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


def dehaze_folder(folder, haze_thr, dry_run):
    out_dir = folder / "dehazed"
    if not dry_run:
        out_dir.mkdir(exist_ok=True)

    images = sorted([p for p in folder.iterdir() if p.suffix.lower() in EXTS])
    print(f"Dehazing pass over {len(images)} images in {folder}")
    print(f"Processing images with haze > {haze_thr}")
    print("-" * 60)

    done = 0
    for p in images:
        img = cv2.imread(str(p))
        if img is None:
            print(f"SKIP  (unreadable)  {p.name}")
            continue
        h = haze_score(img)
        if h > haze_thr:
            tag = "WOULD DEHAZE" if dry_run else "DEHAZE"
            print(f"{tag}  haze={h:.2f}  {p.name}")
            if not dry_run:
                cv2.imwrite(str(out_dir / p.name), dehaze(img))
            done += 1
        else:
            print(f"skip  haze={h:.2f}  {p.name}")

    print("-" * 60)
    print(f"{'Would dehaze' if dry_run else 'Dehazed'}: {done} / {len(images)}  ->  {out_dir}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", type=Path)
    ap.add_argument("--blur", type=float, default=100.0,
                    help="Blur threshold (variance). Lower = blurrier. Default 100.")
    ap.add_argument("--blown", type=float, default=0.40,
                    help="Blown-out threshold (fraction of saturated pixels). Default 0.40.")
    ap.add_argument("--trash", type=str, default="trash",
                    help="Name of trash subfolder. Default 'trash'.")
    ap.add_argument("--dehaze", action="store_true",
                    help="Dehaze hazy images into a 'dehazed' subfolder instead of culling.")
    ap.add_argument("--haze", type=float, default=0.35,
                    help="Haze threshold for --dehaze (0=clear, 1=hazy). Default 0.35.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print decisions but don't move/write files.")
    args = ap.parse_args()

    folder = args.folder.resolve()

    if args.dehaze:
        dehaze_folder(folder, args.haze, args.dry_run)
        return

    trash = folder / args.trash
    if not args.dry_run:
        trash.mkdir(exist_ok=True)

    images = [p for p in folder.iterdir() if p.suffix.lower() in EXTS]
    print(f"Scanning {len(images)} images in {folder}")
    print(f"Thresholds: blur < {args.blur}, blown >= {args.blown:.0%}")
    print("-" * 60)

    moved = 0
    for p in sorted(images):
        img = cv2.imread(str(p))
        if img is None:
            print(f"SKIP  (unreadable)  {p.name}")
            continue
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        b = blur_score(gray)
        x = blown_ratio(gray)

        reasons = []
        if b < args.blur:
            reasons.append(f"blurry({b:.0f})")
        if x >= args.blown:
            reasons.append(f"blown({x:.0%})")

        if reasons:
            tag = "WOULD MOVE" if args.dry_run else "MOVE"
            print(f"{tag}  {','.join(reasons):<25} {p.name}")
            if not args.dry_run:
                shutil.move(str(p), str(trash / p.name))
            moved += 1
        else:
            print(f"keep  blur={b:6.0f} blown={x:5.0%}  {p.name}")

    print("-" * 60)
    print(f"{'Would move' if args.dry_run else 'Moved'}: {moved} / {len(images)}")


if __name__ == "__main__":
    main()
