"""
Move blurry or blown-out images to a trash folder.

Usage:
    python cull_photos.py /path/to/photos
    python cull_photos.py /path/to/photos --blur 100 --blown 0.40 --dry-run

    # Dehaze pass: clearly-hazy images -> ./dehazed,
    # borderline ones (just under the cutoff) get dehaze + auto levels -> ./touched_up
    python cull_photos.py /path/to/photos --dehaze
    python cull_photos.py /path/to/photos --dehaze --haze 0.35 --touchup-margin 0.30 --dry-run

Tune --blur up if too few flagged, down if too many.

All image algorithms live in photo_core.py (shared with the GUI).
"""

import argparse
import shutil
from pathlib import Path

import cv2

from photo_core import (EXTS, blur_score, blown_ratio, haze_score,
                        dehaze, touch_up, haze_action,
                        DEHAZE_THRESHOLD, TOUCHUP_MARGIN)


def dehaze_folder(folder, haze_thr, touchup_margin, dry_run):
    dehaze_dir = folder / "dehazed"
    touchup_dir = folder / "touched_up"

    images = sorted([p for p in folder.iterdir() if p.suffix.lower() in EXTS])
    border_lo = haze_thr * (1 - touchup_margin)
    print(f"Dehaze pass over {len(images)} images in {folder}")
    print(f"  haze > {haze_thr:.2f}            -> dehaze       -> {dehaze_dir.name}/")
    print(f"  {border_lo:.2f} < haze <= {haze_thr:.2f}  -> dehaze+levels -> {touchup_dir.name}/")
    print("-" * 60)

    n_dehaze = n_touch = 0
    for p in images:
        img = cv2.imread(str(p))
        if img is None:
            print(f"SKIP  (unreadable)  {p.name}")
            continue
        h = haze_score(img)
        action = haze_action(h, haze_thr, touchup_margin)

        if action == "dehaze":
            tag = "WOULD DEHAZE" if dry_run else "DEHAZE  "
            print(f"{tag}  haze={h:.2f}  {p.name}")
            if not dry_run:
                dehaze_dir.mkdir(exist_ok=True)
                cv2.imwrite(str(dehaze_dir / p.name), dehaze(img))
            n_dehaze += 1
        elif action == "touch_up":
            tag = "WOULD TOUCH UP" if dry_run else "TOUCH UP"
            print(f"{tag}  haze={h:.2f}  {p.name}")
            if not dry_run:
                touchup_dir.mkdir(exist_ok=True)
                cv2.imwrite(str(touchup_dir / p.name), touch_up(img))
            n_touch += 1
        else:
            print(f"skip      haze={h:.2f}  {p.name}")

    print("-" * 60)
    verb = "Would process" if dry_run else "Processed"
    print(f"{verb}: {n_dehaze} dehazed, {n_touch} touched up  ({len(images)} total)")


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
                    help="Run the dehaze / touch-up pass instead of culling.")
    ap.add_argument("--haze", type=float, default=DEHAZE_THRESHOLD,
                    help=f"Haze threshold for --dehaze (0=clear, 1=hazy). Default {DEHAZE_THRESHOLD}.")
    ap.add_argument("--touchup-margin", type=float, default=TOUCHUP_MARGIN,
                    help="Borderline band width below the haze threshold, as a "
                         f"fraction. Default {TOUCHUP_MARGIN} (i.e. 30%% below).")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print decisions but don't move/write files.")
    args = ap.parse_args()

    folder = args.folder.resolve()

    if args.dehaze:
        dehaze_folder(folder, args.haze, args.touchup_margin, args.dry_run)
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
