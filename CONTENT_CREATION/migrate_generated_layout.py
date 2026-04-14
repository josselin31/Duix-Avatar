#!/usr/bin/env python3
"""Migrate flat GENERATED outputs to per-brief folder layout."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
CONTENT_DIR = ROOT_DIR / "CONTENT_CREATION"
GENERATED_DIR = CONTENT_DIR / "GENERATED"


def case_dir_for_stem(stem: str) -> Path:
    return GENERATED_DIR / stem


def artifacts_dir_for_stem(stem: str) -> Path:
    return case_dir_for_stem(stem) / "artifacts"


def migrate_stem(stem: str) -> None:
    case_dir = case_dir_for_stem(stem)
    artifacts_dir = artifacts_dir_for_stem(stem)
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    source = CONTENT_DIR / f"{stem}.md"
    if source.exists():
        target_source = case_dir / f"{stem}.md"
        target_source.write_text(source.read_text(encoding="utf-8").strip() + "\n", encoding="utf-8")
        print(f"[ok] source copy -> {target_source.relative_to(ROOT_DIR)}")

    flat_files = sorted(GENERATED_DIR.glob(f"{stem}.*"))
    for file_path in flat_files:
        if file_path.is_dir():
            continue
        name = file_path.name
        if name == f"{stem}.rendered.mp4":
            target = case_dir / name
        else:
            target = artifacts_dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(file_path), str(target))
        print(f"[ok] moved {file_path.relative_to(ROOT_DIR)} -> {target.relative_to(ROOT_DIR)}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate CONTENT_CREATION/GENERATED to per-stem layout.")
    parser.add_argument("--stem", default="", help="Optional single stem (example: 1)")
    args = parser.parse_args()

    if not GENERATED_DIR.exists():
        print(f"No generated directory found at {GENERATED_DIR}")
        return 0

    if args.stem:
        migrate_stem(args.stem.strip())
        return 0

    stems = sorted({p.stem.split(".")[0] for p in GENERATED_DIR.glob("*.*") if p.is_file()})
    if not stems:
        print("No flat generated files to migrate.")
        return 0

    for stem in stems:
        migrate_stem(stem)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
