#!/usr/bin/env python3
"""
Generate image-map.json from an images directory.

Expected image layout:

  images/
    default-placeholder.png
    SEESII全品类/
      page_1_封面_1.PNG
      page_5_操作指南_1.PNG
      page_5_操作指南_2.PNG

Usage:

  python generate_image_map.py
  python generate_image_map.py --images-dir images --output image-map.json --overwrite

Output structure:

  {
    "SEESII全品类": {
      "封面": ["images/SEESII全品类/page_1_封面_1.PNG"],
      "操作指南": [
        "images/SEESII全品类/page_5_操作指南_1.PNG",
        "images/SEESII全品类/page_5_操作指南_2.PNG"
      ]
    },
    "default": ["images/default-placeholder.png"]
  }
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


IMAGE_NAME_RE = re.compile(r"^page_(?P<page_order>\d+)_(?P<page_name>.+)_(?P<image_order>\d+)\.png$", re.IGNORECASE)
DEFAULT_PLACEHOLDER = "default-placeholder.png"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate image-map.json by scanning subdirectories under images/."
    )
    parser.add_argument(
        "--images-dir",
        default="images",
        help="Images root directory. Default: images",
    )
    parser.add_argument(
        "--output",
        default="image-map.json",
        help="Output image-map.json path. Default: image-map.json",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite the existing output file instead of merging new YAML entries and images.",
    )
    return parser.parse_args()


def normalize_json_path(path: Path, base_dir: Path) -> str:
    """Return a stable JSON path using forward slashes."""
    try:
        json_path = path.resolve().relative_to(base_dir.resolve())
    except ValueError:
        json_path = path.resolve()
    return json_path.as_posix()


def normalize_yaml_key(directory_name: str) -> str:
    """
    Convert an image subdirectory name to the image-map top-level key.

    In this project the folder is usually named like "SEESII全品类" while the YAML
    file is "SEESII全品类.yaml", so the folder name is used directly. If a folder is
    literally named with .yaml/.yml, the suffix is stripped.
    """
    lower_name = directory_name.lower()
    if lower_name.endswith(".yaml"):
        return directory_name[:-5]
    if lower_name.endswith(".yml"):
        return directory_name[:-4]
    return directory_name


def scan_images(images_dir: Path, path_base_dir: Path) -> dict[str, dict[str, list[str]]]:
    """
    Scan image subdirectories and build:

      {
        "YAML文件名": {
          "页面名称": ["图片路径1", "图片路径2"]
        }
      }
    """
    image_map: dict[str, dict[str, list[str]]] = {}

    if not images_dir.exists():
        raise FileNotFoundError(f"Images directory does not exist: {images_dir}")
    if not images_dir.is_dir():
        raise NotADirectoryError(f"Images path is not a directory: {images_dir}")

    for yaml_dir in sorted((item for item in images_dir.iterdir() if item.is_dir()), key=lambda item: item.name):
        yaml_key = normalize_yaml_key(yaml_dir.name)
        pages: dict[str, list[tuple[int, str]]] = {}

        for image_file in sorted((item for item in yaml_dir.iterdir() if item.is_file()), key=lambda item: item.name):
            match = IMAGE_NAME_RE.match(image_file.name)
            if not match:
                continue

            page_name = match.group("page_name")
            image_order = int(match.group("image_order"))
            image_path = normalize_json_path(image_file, path_base_dir)
            pages.setdefault(page_name, []).append((image_order, image_path))

        if not pages:
            continue

        image_map[yaml_key] = {
            page_name: [image_path for _, image_path in sorted(items, key=lambda item: (item[0], item[1]))]
            for page_name, items in sorted(pages.items(), key=lambda item: item[0])
        }

    return image_map


def default_entry(images_dir: Path, path_base_dir: Path) -> list[str]:
    return [normalize_json_path(images_dir / DEFAULT_PLACEHOLDER, path_base_dir)]


def load_existing_map(output_path: Path) -> dict[str, Any]:
    if not output_path.exists() or output_path.stat().st_size == 0:
        return {}

    with output_path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise ValueError(f"Existing JSON root must be an object: {output_path}")

    return data


def merge_image_maps(existing: dict[str, Any], generated: dict[str, dict[str, list[str]]]) -> dict[str, Any]:
    """
    Merge generated content into existing content.

    Existing custom keys are preserved. For generated YAML keys, this adds missing
    pages and appends missing image paths while preserving the generated order.
    """
    merged = dict(existing)

    for yaml_key, generated_pages in generated.items():
        existing_pages = merged.get(yaml_key)
        if not isinstance(existing_pages, dict):
            merged[yaml_key] = generated_pages
            continue

        for page_name, generated_images in generated_pages.items():
            existing_images = existing_pages.get(page_name)
            if not isinstance(existing_images, list):
                existing_pages[page_name] = generated_images
                continue

            seen = {item for item in existing_images if isinstance(item, str)}
            for image_path in generated_images:
                if image_path not in seen:
                    existing_images.append(image_path)
                    seen.add(image_path)

    return merged


def write_json(output_path: Path, data: dict[str, Any]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.write("\n")


def main() -> None:
    args = parse_args()
    images_dir = Path(args.images_dir)
    output_path = Path(args.output)

    path_base_dir = Path.cwd()
    generated = scan_images(images_dir, path_base_dir)

    if args.overwrite:
        final_map: dict[str, Any] = dict(generated)
        final_map["default"] = default_entry(images_dir, path_base_dir)
    else:
        existing = load_existing_map(output_path)
        final_map = merge_image_maps(existing, generated)
        final_map.setdefault("default", default_entry(images_dir, path_base_dir))

    write_json(output_path, final_map)
    print(f"Generated {output_path} with {len(final_map)} top-level entries.")


if __name__ == "__main__":
    main()
