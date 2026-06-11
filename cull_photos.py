"""
Move blurry or blown-out images to a trash folder.

Usage:
    python cull_photos.py /path/to/photos
    python cull_photos.py /path/to/photos --blur 100 --blown 0.40 --dry-run

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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", type=Path)
    ap.add_argument("--blur", type=float, default=100.0,
                    help="Blur threshold (variance). Lower = blurrier. Default 100.")
    ap.add_argument("--blown", type=float, default=0.40,
                    help="Blown-out threshold (fraction of saturated pixels). Default 0.40.")
    ap.add_argument("--trash", type=str, default="trash",
                    help="Name of trash subfolder. Default 'trash'.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print decisions but don't move files.")
    args = ap.parse_args()

    folder = args.folder.resolve()
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
