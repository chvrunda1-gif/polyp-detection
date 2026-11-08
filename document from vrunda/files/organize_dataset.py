"""
Kvasir-SEG Dataset Organizer
==============================
Run this script after downloading Kvasir-SEG.
It will organize images into polyp / no_polyp / test_samples folders.

Kvasir-SEG structure after unzip:
    kvasir-seg/
    ├── images/        ← 1000 polyp images
    └── masks/         ← 1000 segmentation masks

Usage:
    python organize_dataset.py
"""

import os
import shutil
import random
from pathlib import Path

# ─────────────────────────────────────────
# EDIT THIS: path to your unzipped folder
# ─────────────────────────────────────────
KVASIR_SEG_PATH = r"kvasir-seg"   # e.g. r"C:\Downloads\kvasir-seg"

# Output folder (inside your project)
OUTPUT_PATH = r"data"

# How many images for testing the app
TEST_SAMPLE_COUNT = 10

# Train/val split ratio
TRAIN_RATIO = 0.8
# ─────────────────────────────────────────


def organize():
    kvasir = Path(KVASIR_SEG_PATH)
    images_dir = kvasir / "images"
    masks_dir  = kvasir / "masks"

    if not images_dir.exists():
        print(f"❌ ERROR: Could not find '{images_dir}'")
        print("   Make sure KVASIR_SEG_PATH points to the unzipped folder.")
        return

    # Collect all image files
    all_images = sorted(list(images_dir.glob("*.jpg")) + list(images_dir.glob("*.png")))
    print(f"✅ Found {len(all_images)} images in Kvasir-SEG")

    # Shuffle for random split
    random.seed(42)
    random.shuffle(all_images)

    # Split
    test_images  = all_images[:TEST_SAMPLE_COUNT]
    rest         = all_images[TEST_SAMPLE_COUNT:]
    split_idx    = int(len(rest) * TRAIN_RATIO)
    train_images = rest[:split_idx]
    val_images   = rest[split_idx:]

    # All Kvasir-SEG images are POLYP images
    # We'll create a clear folder structure
    folders = {
        "polyp/train":    train_images,
        "polyp/val":      val_images,
        "test_samples":   test_images,
    }

    out = Path(OUTPUT_PATH)

    for folder, images in folders.items():
        dest = out / folder
        dest.mkdir(parents=True, exist_ok=True)
        for img_path in images:
            shutil.copy2(img_path, dest / img_path.name)
            # Also copy mask if available
            if folder != "test_samples" and masks_dir.exists():
                mask_path = masks_dir / img_path.name
                if mask_path.exists():
                    mask_dest = out / folder.replace("polyp", "masks")
                    mask_dest.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(mask_path, mask_dest / img_path.name)

    # Create no_polyp folder with placeholder (Kvasir-SEG has no normal images)
    no_polyp_dir = out / "no_polyp"
    no_polyp_dir.mkdir(parents=True, exist_ok=True)
    readme = no_polyp_dir / "README.txt"
    readme.write_text(
        "Add normal (non-polyp) colonoscopy images here.\n"
        "Source: Hyper-Kvasir 'normal-cecum' and 'normal-z-line' folders.\n"
        "Download: https://datasets.simula.no/hyper-kvasir/\n"
    )

    # Write dataset summary
    summary = out / "dataset_info.txt"
    summary.write_text(f"""Kvasir-SEG Dataset Summary
===========================
Total images      : {len(all_images)}
Training (polyp)  : {len(train_images)}
Validation (polyp): {len(val_images)}
Test samples      : {len(test_images)}
No-polyp images   : 0 (add from Hyper-Kvasir — see no_polyp/README.txt)

Folder structure:
  data/
  ├── polyp/
  │   ├── train/     ({len(train_images)} images)
  │   └── val/       ({len(val_images)} images)
  ├── masks/
  │   ├── train/     (segmentation masks)
  │   └── val/       (segmentation masks)
  ├── no_polyp/      (add normal images here)
  └── test_samples/  ({len(test_images)} images — use these to demo the app)
""", encoding='utf-8')

    print("\n✅ Dataset organized successfully!\n")
    print(f"   📁 Output folder  : {out.resolve()}")
    print(f"   🟢 Train (polyp)  : {len(train_images)} images")
    print(f"   🔵 Val (polyp)    : {len(val_images)} images")
    print(f"   🧪 Test samples   : {len(test_images)} images")
    print(f"\n   ➡  Use images from  data/test_samples/  to test your app")
    print(f"   ➡  Use data/polyp/train/ + data/polyp/val/ to train your model")
    print(f"\n⚠️  No-polyp images needed — see data/no_polyp/README.txt\n")


if __name__ == "__main__":
    organize()
