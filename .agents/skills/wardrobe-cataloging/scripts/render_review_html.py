#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import html
import json
import os
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import quote


def _find_wardrobe_root() -> Path:
    start = Path(__file__).resolve().parent
    for candidate in [start, *start.parents]:
        if (candidate / "data" / "Raw Images").is_dir() and (candidate / "working").is_dir():
            return candidate
    raise RuntimeError(
        "Could not locate Wardrobe root. Expected an ancestor directory "
        "containing both `data/Raw Images/` and `working/`."
    )


WARDROBE = _find_wardrobe_root()
WORKING = WARDROBE / "working"
RAW_IMAGES = WARDROBE / "data" / "Raw Images"
CATALOG = WORKING / "wardrobe_catalog.csv"
REF_MAP = WORKING / "image_reference_map.csv"
DEFAULT_OUTPUT = WORKING / "wardrobe_review.html"
STORAGE_KEY = "wardrobe-review-actions.v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a static HTML review page for wardrobe_catalog.csv "
            "with local, browser-side review actions."
        )
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output HTML file path (default: {DEFAULT_OUTPUT})",
    )
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def split_pipe_field(value: str) -> list[str]:
    text = (value or "").strip()
    if not text:
        return []
    return [part.strip() for part in text.split("|") if part.strip()]


def split_item_ids(value: str) -> list[str]:
    text = (value or "").strip()
    if not text:
        return []
    return [part.strip() for part in re.split(r"\s*,\s*", text) if part.strip()]


def parse_img_number(value: str) -> int:
    match = re.search(r"Img\s+(\d+)", value or "")
    return int(match.group(1)) if match else 10**9


def extract_img_id(value: str) -> str:
    match = re.search(r"(Img\s+\d+)", value or "")
    return match.group(1) if match else (value or "").strip()


def rel_url(from_dir: Path, target: Path) -> str:
    relative = Path(os.path.relpath(target, from_dir))
    return quote(relative.as_posix(), safe="/")


def file_mtime(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")


def format_color(row: dict[str, str]) -> str:
    primary = row["Color (Primary)"].strip()
    secondary = row["Color (Secondary)"].strip()
    if secondary and secondary != "—":
        return f"{primary} / {secondary}"
    return primary or "—"


def item_sort_key(row: dict[str, str]) -> tuple[int, int, str]:
    item_id = row["Item ID"].strip()
    if "-" in item_id:
        prefix, suffix = item_id.split("-", 1)
    else:
        prefix, suffix = item_id, ""

    prefix_rank = {
        "BOT": 0,
        "TOP": 1,
        "SHO": 2,
        "ACC": 3,
    }.get(prefix, 9)

    try:
        numeric_suffix = int(suffix)
    except ValueError:
        numeric_suffix = 10**9

    return prefix_rank, numeric_suffix, item_id


def html_json_attr(value: object) -> str:
    return html.escape(json.dumps(value, ensure_ascii=True), quote=True)


def dedupe_keep_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value and value not in seen:
            output.append(value)
            seen.add(value)
    return output


def build_indexes(
    catalog_rows: list[dict[str, str]],
    ref_rows: list[dict[str, str]],
) -> tuple[
    dict[str, list[dict[str, str]]],
    dict[str, set[str]],
]:
    refs_by_filename: dict[str, list[dict[str, str]]] = defaultdict(list)
    catalog_item_ids_by_filename: dict[str, set[str]] = defaultdict(set)

    for row in ref_rows:
        refs_by_filename[row["Image Filename"]].append(row)

    for rows in refs_by_filename.values():
        rows.sort(key=lambda entry: parse_img_number(entry["Image Number"]))

    for row in catalog_rows:
        item_id = row["Item ID"].strip()
        for filename in split_pipe_field(row["Item Image Name"]):
            catalog_item_ids_by_filename[filename].add(item_id)

    return refs_by_filename, catalog_item_ids_by_filename


def render_html(
    catalog_rows: list[dict[str, str]],
    ref_rows: list[dict[str, str]],
    output_path: Path,
) -> str:
    catalog_rows = sorted(catalog_rows, key=item_sort_key)
    refs_by_filename, catalog_item_ids_by_filename = build_indexes(catalog_rows, ref_rows)
    raw_filenames = {path.name for path in RAW_IMAGES.iterdir() if path.is_file()}
    categories = sorted({row["Category"].strip() for row in catalog_rows if row["Category"].strip()})
    multi_image_items = sum(
        1 for row in catalog_rows if len(split_pipe_field(row["Item Image Name"])) > 1
    )
    item_cards: list[str] = []

    for item_index, row in enumerate(catalog_rows):
        item_id = row["Item ID"].strip()
        filenames = split_pipe_field(row["Item Image Name"])
        image_reference_labels = split_pipe_field(row["Image References"])
        catalog_ref_ids = [extract_img_id(label) for label in image_reference_labels if extract_img_id(label)]
        image_cards: list[str] = []

        for image_index, filename in enumerate(filenames):
            raw_path = RAW_IMAGES / filename
            exists = filename in raw_filenames and raw_path.is_file()
            image_href = rel_url(output_path.parent, raw_path) if exists else ""
            filename_refs = refs_by_filename.get(filename, [])
            matching_refs = [
                entry
                for entry in filename_refs
                if item_id in split_item_ids(entry["Mapped Item ID(s)"])
            ]
            reference_ids = dedupe_keep_order(
                [extract_img_id(entry["Image Number"]) for entry in (matching_refs or filename_refs)]
            )
            catalog_ref_id = extract_img_id(image_reference_labels[image_index]) if image_index < len(image_reference_labels) else ""
            other_item_ids = sorted(
                other_item_id
                for other_item_id in catalog_item_ids_by_filename.get(filename, set())
                if other_item_id != item_id
            )

            image_cards.append(
                f'<figure class="image-card" '
                f'data-item-id="{html.escape(item_id)}" '
                f'data-filename="{html.escape(filename)}" '
                f'data-catalog-ref="{html.escape(catalog_ref_id)}" '
                f'data-reference-ids="{html_json_attr(reference_ids)}" '
                f'data-other-item-ids="{html_json_attr(other_item_ids)}">'
                + (
                    f'<a href="{image_href}" target="_blank" rel="noopener noreferrer">'
                    f'<img src="{image_href}" alt="{html.escape(filename)}"></a>'
                    if exists
                    else '<div class="missing-image">Missing raw file</div>'
                )
                + '<figcaption>'
                f'<div class="image-title">{html.escape(filename)}</div>'
                + (
                    f'<div class="image-meta">Catalog ref: {html.escape(catalog_ref_id)}</div>'
                    if catalog_ref_id
                    else '<div class="image-meta">Catalog ref: none</div>'
                )
                + (
                    f'<div class="image-meta">Reference image IDs: {html.escape(", ".join(reference_ids))}</div>'
                    if reference_ids
                    else '<div class="image-meta">Reference image IDs: none</div>'
                )
                + (
                    f'<div class="image-related">Also cataloged under: {html.escape(", ".join(other_item_ids))}</div>'
                    if other_item_ids
                    else '<div class="image-related">No other current item references this image.</div>'
                )
                + (
                    '<div class="image-related missing-note">Raw image file missing from data/Raw Images/.</div>'
                    if not exists
                    else ""
                )
                + '<div class="card-actions">'
                f'<button type="button" class="action-btn image-action-btn">Mark wrong for {html.escape(item_id)}</button>'
                '</div>'
                '</figcaption></figure>'
            )

        item_cards.append(
            f'<article class="item-card" '
            f'data-item-id="{html.escape(item_id)}" '
            f'data-category="{html.escape(row["Category"].strip())}" '
            f'data-multi-image="{"1" if len(filenames) > 1 else "0"}" '
            f'data-original-index="{item_index}" '
            f'data-search="{html.escape(" ".join([item_id, row["Category"], row["Sub-Category"], row["Brand"], format_color(row), row["Item Image Name"]]).lower())}" '
            f'data-filenames="{html_json_attr(filenames)}" '
            f'data-catalog-refs="{html_json_attr(catalog_ref_ids)}">'
            '<div class="item-header">'
            '<div>'
            f'<h2>{html.escape(item_id)}</h2>'
            f'<p class="item-subtitle">{html.escape(row["Category"])}</p>'
            '</div>'
            '<div class="item-header-actions">'
            f'<span class="badge">{len(filenames)} image{"s" if len(filenames) != 1 else ""}</span>'
            '<button type="button" class="action-btn item-action-btn">Mark entire item invalid</button>'
            '</div>'
            '</div>'
            '<div class="meta-grid">'
            '<div class="meta-row">'
            '<span class="meta-label">Brand</span>'
            f'<span class="meta-value">{html.escape(row["Brand"].strip() or "—")}</span>'
            '</div>'
            '<div class="meta-row">'
            '<span class="meta-label">Color</span>'
            f'<span class="meta-value">{html.escape(format_color(row))}</span>'
            '</div>'
            '</div>'
            '<section class="gallery">'
            '<h3>Reference Images</h3>'
            '<div class="image-grid">'
            f'{"".join(image_cards)}'
            '</div></section>'
            '</article>'
        )

    category_options = "".join(
        f'<option value="{html.escape(category)}">{html.escape(category)}</option>'
        for category in categories
    )
    page_title = "Wardrobe Catalog Review"
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    export_meta = {
        "schema_version": 1,
        "storage_key": STORAGE_KEY,
        "wardrobe_root": str(WARDROBE),
        "page_generated_at": generated_at,
        "catalog_csv_mtime": file_mtime(CATALOG),
        "reference_map_mtime": file_mtime(REF_MAP),
        "catalog_items": len(catalog_rows),
        "reference_rows": len(ref_rows),
    }

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{page_title}</title>
  <style>
    :root {{
      --bg: #f3efe5;
      --panel: #fffaf0;
      --panel-strong: #fffdf7;
      --text: #1f1a17;
      --muted: #6e6259;
      --line: #dbcfc1;
      --accent: #1f6f5f;
      --accent-soft: #d9eee8;
      --danger: #8a2f1d;
      --danger-soft: #f7dfd7;
      --warning: #8b6c1b;
      --warning-soft: #f7eed0;
      --shadow: 0 16px 40px rgba(31, 26, 23, 0.08);
    }}
    * {{
      box-sizing: border-box;
    }}
    body {{
      margin: 0;
      font-family: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", Georgia, serif;
      color: var(--text);
      background:
        radial-gradient(circle at top left, rgba(31, 111, 95, 0.08), transparent 28%),
        radial-gradient(circle at top right, rgba(138, 47, 29, 0.08), transparent 26%),
        linear-gradient(180deg, #f8f4eb 0%, var(--bg) 100%);
    }}
    button,
    input,
    select {{
      font: inherit;
    }}
    .page {{
      width: min(1420px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 28px 0 48px;
    }}
    .hero,
    .filters,
    .review-queue,
    .item-card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 24px;
      box-shadow: var(--shadow);
    }}
    .hero {{
      padding: 28px;
      background: linear-gradient(135deg, rgba(255, 250, 240, 0.94), rgba(255, 255, 255, 0.88));
    }}
    .hero h1 {{
      margin: 0 0 10px;
      font-size: clamp(2rem, 4vw, 3.4rem);
      line-height: 0.95;
      letter-spacing: -0.04em;
    }}
    .hero p {{
      margin: 0;
      max-width: 76ch;
      color: var(--muted);
      line-height: 1.5;
    }}
    .stats {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 14px;
      margin-top: 22px;
    }}
    .stat-card {{
      background: var(--panel-strong);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 18px 20px;
    }}
    .stat-label {{
      display: block;
      font-size: 0.8rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--muted);
    }}
    .stat-value {{
      display: block;
      margin-top: 6px;
      font-size: 2rem;
      line-height: 1;
    }}
    .subtle {{
      margin-top: 12px;
      color: var(--muted);
      font-size: 0.92rem;
    }}
    .filters,
    .review-queue {{
      margin-top: 22px;
      padding: 22px;
    }}
    .filters-grid {{
      display: grid;
      grid-template-columns: 2fr 1fr 1fr 1fr;
      gap: 12px;
      align-items: end;
    }}
    .filters label,
    .queue-toolbar label {{
      display: grid;
      gap: 6px;
      font-size: 0.92rem;
      color: var(--muted);
    }}
    .filters input[type="search"],
    .filters select {{
      width: 100%;
      padding: 12px 14px;
      border-radius: 14px;
      border: 1px solid var(--line);
      background: var(--panel-strong);
      color: var(--text);
    }}
    .check-row,
    .queue-toolbar,
    .queue-summary {{
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      align-items: center;
      margin-top: 14px;
    }}
    .queue-toolbar {{
      justify-content: space-between;
    }}
    .queue-actions {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
    }}
    .queue-summary {{
      color: var(--muted);
      font-size: 0.94rem;
    }}
    .catalog {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 18px;
      margin-top: 24px;
      align-items: start;
    }}
    .item-card {{
      padding: 22px;
      transition: border-color 0.18s ease, box-shadow 0.18s ease, transform 0.18s ease;
    }}
    .item-card.is-invalid {{
      border-color: rgba(138, 47, 29, 0.45);
      box-shadow: 0 18px 42px rgba(138, 47, 29, 0.12);
    }}
    .item-header {{
      display: flex;
      justify-content: space-between;
      align-items: start;
      gap: 16px;
    }}
    .item-header h2,
    .gallery h3,
    .review-queue h2 {{
      margin: 0;
    }}
    .item-subtitle {{
      margin: 6px 0 0;
      color: var(--muted);
    }}
    .item-header-actions {{
      display: flex;
      flex-wrap: wrap;
      justify-content: flex-end;
      gap: 10px;
      align-items: center;
    }}
    .badge {{
      display: inline-flex;
      align-items: center;
      border-radius: 999px;
      padding: 7px 11px;
      background: var(--accent-soft);
      color: var(--accent);
      font-size: 0.82rem;
      white-space: nowrap;
    }}
    .meta-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 10px;
      margin-top: 18px;
    }}
    .meta-row {{
      padding: 12px 13px;
      background: var(--panel-strong);
      border: 1px solid var(--line);
      border-radius: 14px;
    }}
    .meta-label {{
      display: block;
      font-size: 0.78rem;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }}
    .meta-value {{
      display: block;
      margin-top: 6px;
      line-height: 1.35;
      word-break: break-word;
    }}
    .gallery {{
      margin-top: 22px;
    }}
    .image-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 16px;
      margin-top: 14px;
    }}
    .image-card {{
      margin: 0;
      background: var(--panel-strong);
      border: 1px solid var(--line);
      border-radius: 18px;
      overflow: hidden;
      transition: border-color 0.18s ease, box-shadow 0.18s ease, transform 0.18s ease;
    }}
    .image-card.is-detached {{
      border-color: rgba(138, 47, 29, 0.45);
      box-shadow: 0 14px 32px rgba(138, 47, 29, 0.12);
      transform: translateY(-1px);
    }}
    .image-card.is-disabled {{
      opacity: 0.68;
    }}
    .image-card img,
    .missing-image {{
      display: block;
      width: 100%;
      aspect-ratio: 4 / 5;
      object-fit: cover;
      background: #e8ded1;
    }}
    .missing-image {{
      display: grid;
      place-items: center;
      color: var(--danger);
      font-weight: 600;
      letter-spacing: 0.02em;
    }}
    .image-card figcaption {{
      padding: 14px;
    }}
    .image-title {{
      font-size: 0.95rem;
      word-break: break-word;
    }}
    .image-meta,
    .image-related {{
      margin-top: 6px;
      color: var(--muted);
      font-size: 0.89rem;
      line-height: 1.4;
    }}
    .missing-note {{
      color: var(--danger);
    }}
    .action-btn {{
      border: 1px solid var(--line);
      background: var(--panel-strong);
      color: var(--text);
      border-radius: 999px;
      padding: 9px 14px;
      cursor: pointer;
      transition: background 0.16s ease, border-color 0.16s ease, color 0.16s ease;
    }}
    .action-btn:hover {{
      border-color: rgba(31, 111, 95, 0.4);
    }}
    .action-btn.is-active {{
      background: var(--danger-soft);
      border-color: rgba(138, 47, 29, 0.32);
      color: var(--danger);
    }}
    .action-btn.is-secondary-active {{
      background: var(--warning-soft);
      border-color: rgba(139, 108, 27, 0.35);
      color: var(--warning);
    }}
    .action-btn:disabled {{
      cursor: not-allowed;
      opacity: 0.65;
    }}
    .card-actions {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin-top: 14px;
    }}
    .queue-list {{
      list-style: none;
      margin: 16px 0 0;
      padding: 0;
      display: grid;
      gap: 12px;
    }}
    .queue-list li {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: start;
      padding: 14px 16px;
      background: var(--panel-strong);
      border: 1px solid var(--line);
      border-radius: 16px;
    }}
    .queue-entry-copy {{
      color: var(--muted);
      line-height: 1.45;
    }}
    .queue-empty {{
      margin-top: 16px;
      color: var(--muted);
    }}
    .hidden {{
      display: none !important;
    }}
    .visually-hidden {{
      position: absolute;
      width: 1px;
      height: 1px;
      padding: 0;
      margin: -1px;
      overflow: hidden;
      clip: rect(0, 0, 0, 0);
      border: 0;
    }}
    @media (max-width: 980px) {{
      .filters-grid {{
        grid-template-columns: 1fr 1fr;
      }}
      .catalog {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}
      .queue-toolbar {{
        align-items: start;
      }}
    }}
    @media (max-width: 700px) {{
      .page {{
        width: min(100vw - 20px, 1420px);
        padding-top: 18px;
      }}
      .hero,
      .filters,
      .review-queue,
      .item-card {{
        padding: 18px;
        border-radius: 20px;
      }}
      .filters-grid {{
        grid-template-columns: 1fr;
      }}
      .catalog {{
        grid-template-columns: 1fr;
      }}
      .item-header,
      .queue-list li {{
        flex-direction: column;
      }}
      .item-header-actions {{
        justify-content: flex-start;
      }}
      .queue-actions {{
        width: 100%;
      }}
    }}
  </style>
</head>
<body>
  <div class="page">
    <header class="hero">
      <h1>{page_title}</h1>
      <p>
        Local review page for the wardrobe catalog. Mark image-to-item mismatches or invalidate an
        entire item in the browser, keep that state in local storage, and export JSON for the cleanup
        script later. No server, no API, just a local review queue.
      </p>
      <div class="stats">
        <div class="stat-card">
          <span class="stat-label">Catalog Items</span>
          <span class="stat-value">{len(catalog_rows)}</span>
        </div>
        <div class="stat-card">
          <span class="stat-label">Image References</span>
          <span class="stat-value">{len(ref_rows)}</span>
        </div>
        <div class="stat-card">
          <span class="stat-label">Multi-Image Items</span>
          <span class="stat-value">{multi_image_items}</span>
        </div>
      </div>
      <p class="subtle">
        Generated at {generated_at}. Catalog CSV updated {file_mtime(CATALOG)}.
        Reference map updated {file_mtime(REF_MAP)}.
      </p>
    </header>

    <section class="filters">
      <div class="filters-grid">
        <label>
          Search
          <input id="search" type="search" placeholder="Item ID, brand, color, filename...">
        </label>
        <label>
          Category
          <select id="category">
            <option value="">All categories</option>
            {category_options}
          </select>
        </label>
        <label>
          Sort
          <select id="sort">
            <option value="default">Original order</option>
            <option value="images">Most images first</option>
          </select>
        </label>
        <label>
          Quick Jump
          <select id="jump">
            <option value="">Choose item</option>
            {"".join(f'<option value="{html.escape(row["Item ID"])}">{html.escape(row["Item ID"])} · {html.escape(row["Category"])}</option>' for row in catalog_rows)}
          </select>
        </label>
      </div>
      <div class="check-row">
        <label><input id="multiOnly" type="checkbox"> Show only items with multiple images</label>
        <span id="visibleCount">Showing {len(catalog_rows)} of {len(catalog_rows)} items</span>
      </div>
    </section>

    <main id="catalog" class="catalog">
      {"".join(item_cards)}
    </main>

    <section class="review-queue">
      <div class="queue-toolbar">
        <div>
          <h2>Review Queue</h2>
          <div class="queue-summary">
            <span id="queueCounts">0 item invalidations, 0 image removals</span>
            <span id="queueStorageNote">Stored in this browser until you export or clear it.</span>
          </div>
        </div>
        <div class="queue-actions">
          <button type="button" id="copyJson" class="action-btn">Copy JSON</button>
          <button type="button" id="logJson" class="action-btn">Log JSON</button>
          <button type="button" id="downloadJson" class="action-btn">Download JSON</button>
          <button type="button" id="importJson" class="action-btn">Import JSON</button>
          <button type="button" id="clearReview" class="action-btn">Clear Review State</button>
          <input id="importJsonInput" class="visually-hidden" type="file" accept="application/json">
        </div>
      </div>
      <p class="subtle">
        Two action types are tracked: removing a specific image from an item, and invalidating an entire item.
        Invalidating an item takes precedence and automatically drops any per-image removals already marked under it.
      </p>
      <div id="queueEmpty" class="queue-empty">No review actions recorded yet.</div>
      <ul id="queueList" class="queue-list"></ul>
    </section>
  </div>

  <script>
    const REVIEW_EXPORT_META = {json.dumps(export_meta, ensure_ascii=True)};
    const STORAGE_KEY = {json.dumps(STORAGE_KEY)};
    const catalog = document.getElementById("catalog");
    const itemCards = Array.from(document.querySelectorAll(".item-card"));
    const imageCards = Array.from(document.querySelectorAll(".image-card"));
    const searchInput = document.getElementById("search");
    const categorySelect = document.getElementById("category");
    const sortSelect = document.getElementById("sort");
    const jumpSelect = document.getElementById("jump");
    const multiOnly = document.getElementById("multiOnly");
    const visibleCount = document.getElementById("visibleCount");
    const queueList = document.getElementById("queueList");
    const queueEmpty = document.getElementById("queueEmpty");
    const queueCounts = document.getElementById("queueCounts");
    const copyJsonButton = document.getElementById("copyJson");
    const logJsonButton = document.getElementById("logJson");
    const downloadJsonButton = document.getElementById("downloadJson");
    const importJsonButton = document.getElementById("importJson");
    const importJsonInput = document.getElementById("importJsonInput");
    const clearReviewButton = document.getElementById("clearReview");

    function freshState() {{
      return {{
        version: 1,
        invalid_items: {{}},
        detached_images: {{}},
      }};
    }}

    function parseDatasetJSON(value, fallback) {{
      try {{
        return JSON.parse(value || JSON.stringify(fallback));
      }} catch (error) {{
        return fallback;
      }}
    }}

    function escapeHtml(value) {{
      return String(value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
    }}

    function normalizeImportedState(raw) {{
      const state = freshState();
      const source = raw && typeof raw === "object" ? raw : {{}};

      if (source.invalid_items) {{
        const invalidItems = Array.isArray(source.invalid_items)
          ? source.invalid_items
          : Object.values(source.invalid_items);
        for (const entry of invalidItems) {{
          if (!entry || !entry.item_id) {{
            continue;
          }}
          state.invalid_items[entry.item_id] = {{
            type: "invalidate_item",
            item_id: entry.item_id,
            filenames: Array.isArray(entry.filenames) ? entry.filenames : [],
            catalog_refs: Array.isArray(entry.catalog_refs) ? entry.catalog_refs : [],
            marked_at: entry.marked_at || new Date().toISOString(),
            note: entry.note || "",
          }};
        }}
      }}

      if (source.detached_images) {{
        const detachedImages = Array.isArray(source.detached_images)
          ? source.detached_images
          : Object.values(source.detached_images);
        for (const entry of detachedImages) {{
          if (!entry || !entry.item_id || !entry.filename) {{
            continue;
          }}
          const key = entry.item_id + "::" + entry.filename;
          state.detached_images[key] = {{
            type: "detach_image",
            item_id: entry.item_id,
            filename: entry.filename,
            catalog_ref: entry.catalog_ref || "",
            reference_image_ids: Array.isArray(entry.reference_image_ids) ? entry.reference_image_ids : [],
            other_item_ids: Array.isArray(entry.other_item_ids) ? entry.other_item_ids : [],
            marked_at: entry.marked_at || new Date().toISOString(),
            note: entry.note || "",
          }};
        }}
      }}

      return state;
    }}

    function loadState() {{
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) {{
        return freshState();
      }}
      try {{
        return normalizeImportedState(JSON.parse(raw));
      }} catch (error) {{
        console.warn("Could not parse local review state. Resetting it.", error);
        return freshState();
      }}
    }}

    let reviewState = loadState();

    function persistState() {{
      localStorage.setItem(STORAGE_KEY, JSON.stringify(reviewState));
      renderReviewState();
    }}

    function imageActionKey(itemId, filename) {{
      return itemId + "::" + filename;
    }}

    function buildExportObject() {{
      const invalidItems = Object.values(reviewState.invalid_items).sort((a, b) => a.item_id.localeCompare(b.item_id));
      const detachedImages = Object.values(reviewState.detached_images)
        .filter((entry) => !reviewState.invalid_items[entry.item_id])
        .sort((a, b) => {{
          const itemCompare = a.item_id.localeCompare(b.item_id);
          return itemCompare !== 0 ? itemCompare : a.filename.localeCompare(b.filename);
        }});

      return {{
        schema_version: 1,
        exported_at: new Date().toISOString(),
        source: REVIEW_EXPORT_META,
        invalid_items: invalidItems,
        detached_images: detachedImages,
      }};
    }}

    function updateItemCards() {{
      for (const itemCard of itemCards) {{
        const itemId = itemCard.dataset.itemId;
        const itemInvalid = Boolean(reviewState.invalid_items[itemId]);
        itemCard.classList.toggle("is-invalid", itemInvalid);

        const itemButton = itemCard.querySelector(".item-action-btn");
        itemButton.classList.toggle("is-active", itemInvalid);
        itemButton.textContent = itemInvalid ? "Item marked invalid" : "Mark entire item invalid";

        const itemImages = Array.from(itemCard.querySelectorAll(".image-card"));
        for (const imageCard of itemImages) {{
          const key = imageActionKey(imageCard.dataset.itemId, imageCard.dataset.filename);
          const detached = Boolean(reviewState.detached_images[key]);
          const button = imageCard.querySelector(".image-action-btn");

          imageCard.classList.toggle("is-detached", detached);
          imageCard.classList.toggle("is-disabled", itemInvalid);
          button.disabled = itemInvalid;

          if (itemInvalid) {{
            button.classList.remove("is-active");
            button.textContent = "Covered by item invalidation";
          }} else if (detached) {{
            button.classList.add("is-active");
            button.textContent = "Marked wrong for " + imageCard.dataset.itemId;
          }} else {{
            button.classList.remove("is-active");
            button.textContent = "Mark wrong for " + imageCard.dataset.itemId;
          }}
        }}
      }}
    }}

    function renderQueue() {{
      const exportObject = buildExportObject();
      const invalidItems = exportObject.invalid_items;
      const detachedImages = exportObject.detached_images;

      queueCounts.textContent =
        invalidItems.length + " item invalidation" + (invalidItems.length === 1 ? "" : "s") +
        ", " +
        detachedImages.length + " image removal" + (detachedImages.length === 1 ? "" : "s");

      const rows = [];

      for (const entry of invalidItems) {{
        rows.push(
          '<li>' +
            '<div class="queue-entry-copy">' +
              '<strong>Invalidate ' + escapeHtml(entry.item_id) + '</strong><br>' +
              '<span>Images: ' + escapeHtml(String((entry.filenames || []).length)) + '</span>' +
            '</div>' +
            '<button type="button" class="action-btn is-active queue-undo-item" data-item-id="' + escapeHtml(entry.item_id) + '">Undo</button>' +
          '</li>'
        );
      }}

      for (const entry of detachedImages) {{
        const otherRefs = entry.other_item_ids && entry.other_item_ids.length
          ? "Other items: " + escapeHtml(entry.other_item_ids.join(", "))
          : "Will become uncategorized unless you reassign it later.";
        rows.push(
          '<li>' +
            '<div class="queue-entry-copy">' +
              '<strong>Remove image from ' + escapeHtml(entry.item_id) + '</strong><br>' +
              '<span>' + escapeHtml(entry.filename) + '</span><br>' +
              '<span>Catalog ref: ' + escapeHtml(entry.catalog_ref || "none") + '</span><br>' +
              '<span>' + otherRefs + '</span>' +
            '</div>' +
            '<button type="button" class="action-btn is-active queue-undo-image" data-item-id="' + escapeHtml(entry.item_id) + '" data-filename="' + escapeHtml(entry.filename) + '">Undo</button>' +
          '</li>'
        );
      }}

      queueList.innerHTML = rows.join("");
      queueEmpty.classList.toggle("hidden", rows.length > 0);
    }}

    function renderReviewState() {{
      updateItemCards();
      renderQueue();
      applyFilters();
    }}

    function toggleItemInvalid(itemCard) {{
      const itemId = itemCard.dataset.itemId;
      if (reviewState.invalid_items[itemId]) {{
        delete reviewState.invalid_items[itemId];
      }} else {{
        reviewState.invalid_items[itemId] = {{
          type: "invalidate_item",
          item_id: itemId,
          filenames: parseDatasetJSON(itemCard.dataset.filenames, []),
          catalog_refs: parseDatasetJSON(itemCard.dataset.catalogRefs, []),
          marked_at: new Date().toISOString(),
          note: "",
        }};

        for (const key of Object.keys(reviewState.detached_images)) {{
          if (key.startsWith(itemId + "::")) {{
            delete reviewState.detached_images[key];
          }}
        }}
      }}

      persistState();
    }}

    function toggleImageDetached(imageCard) {{
      const itemId = imageCard.dataset.itemId;
      if (reviewState.invalid_items[itemId]) {{
        return;
      }}

      const filename = imageCard.dataset.filename;
      const key = imageActionKey(itemId, filename);
      if (reviewState.detached_images[key]) {{
        delete reviewState.detached_images[key];
      }} else {{
        reviewState.detached_images[key] = {{
          type: "detach_image",
          item_id: itemId,
          filename: filename,
          catalog_ref: imageCard.dataset.catalogRef || "",
          reference_image_ids: parseDatasetJSON(imageCard.dataset.referenceIds, []),
          other_item_ids: parseDatasetJSON(imageCard.dataset.otherItemIds, []),
          marked_at: new Date().toISOString(),
          note: "",
        }};
      }}

      persistState();
    }}

    function applyFilters() {{
      const query = searchInput.value.trim().toLowerCase();
      const category = categorySelect.value;
      const requireMulti = multiOnly.checked;
      let visible = 0;

      for (const card of itemCards) {{
        const matchesQuery = !query || card.dataset.search.includes(query);
        const matchesCategory = !category || card.dataset.category === category;
        const matchesMulti = !requireMulti || card.dataset.multiImage === "1";
        const shouldShow = matchesQuery && matchesCategory && matchesMulti;
        card.classList.toggle("hidden", !shouldShow);
        if (shouldShow) {{
          visible += 1;
        }}
      }}

      visibleCount.textContent = "Showing " + visible + " of {len(catalog_rows)} items";
      applySort();
    }}

    function applySort() {{
      const mode = sortSelect.value;
      const visibleCards = itemCards.filter((card) => !card.classList.contains("hidden"));
      const hiddenCards = itemCards.filter((card) => card.classList.contains("hidden"));

      if (mode === "images") {{
        visibleCards.sort((a, b) => {{
          const aCount = parseDatasetJSON(a.dataset.filenames, []).length;
          const bCount = parseDatasetJSON(b.dataset.filenames, []).length;
          return bCount - aCount;
        }});
      }} else {{
        visibleCards.sort((a, b) => Number(a.dataset.originalIndex) - Number(b.dataset.originalIndex));
      }}

      for (const card of [...visibleCards, ...hiddenCards]) {{
        catalog.appendChild(card);
      }}
    }}

    function downloadJson() {{
      const text = JSON.stringify(buildExportObject(), null, 2);
      const filename = "wardrobe-review-actions-" + new Date().toISOString().replace(/[:.]/g, "-") + ".json";
      const blob = new Blob([text], {{ type: "application/json" }});
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    }}

    async function copyJson() {{
      const text = JSON.stringify(buildExportObject(), null, 2);
      if (!navigator.clipboard) {{
        console.log(text);
        alert("Clipboard API unavailable. JSON was logged to the console instead.");
        return;
      }}
      await navigator.clipboard.writeText(text);
      alert("Review JSON copied to clipboard.");
    }}

    function logJson() {{
      console.log("wardrobeReviewActions", buildExportObject());
      alert("Review JSON logged to the browser console.");
    }}

    function mergeImportedFile(data) {{
      const imported = normalizeImportedState(data);
      reviewState.invalid_items = {{
        ...reviewState.invalid_items,
        ...imported.invalid_items,
      }};
      reviewState.detached_images = {{
        ...reviewState.detached_images,
        ...imported.detached_images,
      }};

      for (const itemId of Object.keys(reviewState.invalid_items)) {{
        for (const key of Object.keys(reviewState.detached_images)) {{
          if (key.startsWith(itemId + "::")) {{
            delete reviewState.detached_images[key];
          }}
        }}
      }}

      persistState();
    }}

    catalog.addEventListener("click", (event) => {{
      const itemButton = event.target.closest(".item-action-btn");
      if (itemButton) {{
        const itemCard = itemButton.closest(".item-card");
        if (itemCard) {{
          toggleItemInvalid(itemCard);
        }}
        return;
      }}

      const imageButton = event.target.closest(".image-action-btn");
      if (imageButton) {{
        const imageCard = imageButton.closest(".image-card");
        if (imageCard) {{
          toggleImageDetached(imageCard);
        }}
      }}
    }});

    queueList.addEventListener("click", (event) => {{
      const undoItemButton = event.target.closest(".queue-undo-item");
      if (undoItemButton) {{
        const itemId = undoItemButton.dataset.itemId;
        delete reviewState.invalid_items[itemId];
        persistState();
        return;
      }}

      const undoImageButton = event.target.closest(".queue-undo-image");
      if (undoImageButton) {{
        const key = imageActionKey(undoImageButton.dataset.itemId, undoImageButton.dataset.filename);
        delete reviewState.detached_images[key];
        persistState();
      }}
    }});

    searchInput.addEventListener("input", applyFilters);
    categorySelect.addEventListener("change", applyFilters);
    multiOnly.addEventListener("change", applyFilters);
    sortSelect.addEventListener("change", applySort);
    jumpSelect.addEventListener("change", () => {{
      const itemId = jumpSelect.value;
      if (!itemId) {{
        return;
      }}
      const target = itemCards.find((card) => card.dataset.itemId === itemId);
      if (target) {{
        target.scrollIntoView({{ behavior: "smooth", block: "start" }});
      }}
    }});

    downloadJsonButton.addEventListener("click", downloadJson);
    copyJsonButton.addEventListener("click", () => {{
      copyJson().catch((error) => {{
        console.error(error);
        alert("Could not copy JSON. Check the console for details.");
      }});
    }});
    logJsonButton.addEventListener("click", logJson);
    importJsonButton.addEventListener("click", () => importJsonInput.click());
    importJsonInput.addEventListener("change", async () => {{
      const file = importJsonInput.files && importJsonInput.files[0];
      if (!file) {{
        return;
      }}
      try {{
        const text = await file.text();
        const data = JSON.parse(text);
        mergeImportedFile(data);
        alert("Imported review JSON into local state.");
      }} catch (error) {{
        console.error(error);
        alert("Could not import that JSON file.");
      }} finally {{
        importJsonInput.value = "";
      }}
    }});
    clearReviewButton.addEventListener("click", () => {{
      if (!confirm("Clear all locally stored review actions for this page?")) {{
        return;
      }}
      reviewState = freshState();
      persistState();
    }});

    renderReviewState();
  </script>
</body>
</html>
"""


def main() -> None:
    args = parse_args()
    output_path = args.output.resolve() if not args.output.is_absolute() else args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)

    catalog_rows = read_csv(CATALOG)
    ref_rows = read_csv(REF_MAP)

    html_text = render_html(catalog_rows, ref_rows, output_path)
    output_path.write_text(html_text, encoding="utf-8")

    print(f"Generated {output_path}")
    print(f"Catalog items: {len(catalog_rows)}")
    print(f"Image references: {len(ref_rows)}")


if __name__ == "__main__":
    main()
