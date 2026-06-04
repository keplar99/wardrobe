#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import html
import json
import os
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
DEFAULT_OUTPUT = WORKING / "wardrobe_catalog_table.html"
LOCAL_STORAGE_KEY = "wardrobe-catalog-table-edits.v1"
EXPORT_SCHEMA_VERSION = 1

SUMMARY_COLUMNS = [
    "Preview",
    "Item ID",
    "Category",
    "Sub-Category",
    "Brand",
    "Color",
    "Pattern",
    "More",
]

EDITABLE_FIELDS = [
    "Category",
    "Sub-Category",
    "Brand",
    "Color (Primary)",
    "Color (Secondary)",
    "Pattern",
    "Fit",
    "Rise",
    "Length",
    "Silhouette",
    "Neckline",
    "Drape Notes",
    "Fit Source",
    "Fabric",
    "Weight",
    "Stretch",
    "Breathability",
    "Surface Texture",
    "Formality (1-5)",
    "Vibe Tags",
    "Occasion Tags",
    "Layering Position",
    "Season",
    "Max Comfortable Temp (C)",
    "Condition",
    "Wear Frequency Estimate",
    "Color Temperature",
    "Skin Tone Interaction",
    "Skin Tone Caution Flag",
    "Contrast Level",
    "Versatility Score (1-5)",
    "Role in Outfit",
    "Volume/Visual Weight",
    "Shoe Type",
    "Sole Profile",
    "Aesthetic Range",
    "Top Compatibility Note",
    "Client notes",
    "Status",
]

TEXTAREA_FIELDS = {
    "Drape Notes",
    "Fit Source",
    "Vibe Tags",
    "Occasion Tags",
    "Skin Tone Interaction",
    "Aesthetic Range",
    "Top Compatibility Note",
    "Client notes",
    "Status",
}

SUMMARY_SOURCE_FIELDS = {
    "Category": "Category",
    "Sub-Category": "Sub-Category",
    "Brand": "Brand",
    "Pattern": "Pattern",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a static HTML table view of wardrobe_catalog.csv with "
            "expandable detail rows, local edits, JSON export, and an image modal."
        )
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output HTML file path (default: {DEFAULT_OUTPUT})",
    )
    return parser.parse_args()


def read_catalog(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        rows = list(reader)
    return fieldnames, rows


def split_pipe_field(value: str) -> list[str]:
    text = (value or "").strip()
    if not text:
        return []
    return [part.strip() for part in text.split("|") if part.strip()]


def rel_url(from_dir: Path, target: Path) -> str:
    relative = Path(os.path.relpath(target, from_dir))
    return quote(relative.as_posix(), safe="/")


def file_mtime(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")


def item_sort_key(row: dict[str, str]) -> tuple[int, int, str]:
    item_id = (row.get("Item ID") or "").strip()
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


def format_value(value: str) -> str:
    text = (value or "").strip()
    return text if text else "-"


def format_color_values(primary: str, secondary: str) -> str:
    primary_text = (primary or "").strip()
    secondary_text = (secondary or "").strip()
    if secondary_text and secondary_text != "—":
        return f"{primary_text} / {secondary_text}"
    return primary_text or "-"


def format_color(row: dict[str, str]) -> str:
    return format_color_values(row.get("Color (Primary)", ""), row.get("Color (Secondary)", ""))


def build_image_markup(output_path: Path, filename: str) -> tuple[str, bool]:
    raw_path = RAW_IMAGES / filename
    exists = raw_path.is_file()
    if not exists:
        return ('<div class="thumb-placeholder">Missing</div>', False)

    image_href = rel_url(output_path.parent, raw_path)
    markup = (
        f'<button type="button" class="thumb-button" '
        f'data-image-src="{html.escape(image_href, quote=True)}" '
        f'data-image-alt="{html.escape(filename, quote=True)}" '
        f'data-image-caption="{html.escape(filename, quote=True)}">'
        f'<img class="thumb-image" src="{html.escape(image_href, quote=True)}" '
        f'alt="{html.escape(filename, quote=True)}"></button>'
    )
    return markup, True


def render_filename_list(output_path: Path, filenames: list[str]) -> str:
    items: list[str] = []
    for filename in filenames:
        raw_path = RAW_IMAGES / filename
        if raw_path.is_file():
            href = rel_url(output_path.parent, raw_path)
            content = (
                f'<a class="file-pill" href="{html.escape(href, quote=True)}" '
                f'target="_blank" rel="noopener noreferrer">{html.escape(filename)}</a>'
            )
        else:
            content = f'<span class="file-pill file-pill-missing">{html.escape(filename)} (missing)</span>'
        items.append(content)
    return "".join(items) if items else '<span class="empty-value">-</span>'


def render_editable_control(item_id: str, fieldname: str, value: str) -> str:
    common_attrs = (
        f'data-item-id="{html.escape(item_id, quote=True)}" '
        f'data-field-name="{html.escape(fieldname, quote=True)}" '
        f'data-original-value="{html.escape(value, quote=True)}"'
    )
    if fieldname in TEXTAREA_FIELDS:
        return (
            f'<textarea class="edit-control edit-control-textarea" {common_attrs} '
            'rows="4" spellcheck="false">'
            f'{html.escape(value)}'
            '</textarea>'
        )
    return (
        f'<input class="edit-control" type="text" {common_attrs} '
        f'value="{html.escape(value, quote=True)}" spellcheck="false">'
    )


def render_detail_value(output_path: Path, item_id: str, fieldname: str, value: str) -> str:
    if fieldname == "Item Image Name":
        return render_filename_list(output_path, split_pipe_field(value))
    if fieldname in EDITABLE_FIELDS:
        return render_editable_control(item_id, fieldname, value)
    return html.escape(format_value(value))


def render_detail_field(output_path: Path, item_id: str, fieldname: str, value: str) -> str:
    is_editable = fieldname in EDITABLE_FIELDS
    field_classes = "detail-field is-editable" if is_editable else "detail-field"
    return (
        f'<div class="{field_classes}" '
        f'data-item-id="{html.escape(item_id, quote=True)}" '
        f'data-field-name="{html.escape(fieldname, quote=True)}">'
        '<div class="detail-field-top">'
        f'<div class="detail-label">{html.escape(fieldname)}</div>'
        + (
            '<div class="field-tools">'
            '<span class="field-status" hidden>Edited</span>'
            '<button type="button" class="reset-field-button" hidden>Reset</button>'
            '</div>'
            if is_editable
            else ""
        )
        + '</div>'
        f'<div class="detail-value">{render_detail_value(output_path, item_id, fieldname, value)}</div>'
        '</div>'
    )


def render_html(headers: list[str], rows: list[dict[str, str]], output_path: Path) -> str:
    sorted_rows = sorted(rows, key=item_sort_key)
    categories = sorted(
        {(row.get("Category") or "").strip() for row in sorted_rows if (row.get("Category") or "").strip()}
    )
    total_multi_image = sum(
        1 for row in sorted_rows if len(split_pipe_field(row.get("Item Image Name", ""))) > 1
    )
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    export_meta = {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "local_storage_key": LOCAL_STORAGE_KEY,
        "wardrobe_root": str(WARDROBE),
        "catalog_csv": str(CATALOG),
        "catalog_csv_mtime": file_mtime(CATALOG),
        "page_generated_at": generated_at,
        "editable_fields": EDITABLE_FIELDS,
        "headers": headers,
        "row_count": len(sorted_rows),
    }

    category_options = "".join(
        f'<option value="{html.escape(category)}">{html.escape(category)}</option>'
        for category in categories
    )

    table_rows: list[str] = []
    summary_column_count = len(SUMMARY_COLUMNS)

    for index, row in enumerate(sorted_rows):
        item_id = (row.get("Item ID") or "").strip()
        item_id_display = format_value(item_id)
        filenames = split_pipe_field(row.get("Item Image Name", ""))
        preview_name = filenames[0] if filenames else ""
        preview_markup, has_image = (
            build_image_markup(output_path, preview_name)
            if preview_name
            else ('<div class="thumb-placeholder">No image</div>', False)
        )
        detail_id = f"detail-row-{index}"
        search_blob = " ".join(
            [
                row.get("Item ID", ""),
                row.get("Category", ""),
                row.get("Sub-Category", ""),
                row.get("Brand", ""),
                row.get("Color (Primary)", ""),
                row.get("Color (Secondary)", ""),
                row.get("Pattern", ""),
                row.get("Vibe Tags", ""),
                row.get("Occasion Tags", ""),
                row.get("Client notes", ""),
                row.get("Status", ""),
            ]
        ).lower()
        base_search_blob = " ".join(
            [
                row.get("Item ID", ""),
                row.get("Item Image Name", ""),
                row.get("Image References", ""),
            ]
        ).lower()

        detail_cells = [
            render_detail_field(output_path, item_id, fieldname, row.get(fieldname, ""))
            for fieldname in headers
        ]

        editable_count = sum(1 for fieldname in headers if fieldname in EDITABLE_FIELDS)
        image_meta = (
            f'<div class="detail-chip">{len(filenames)} image{"s" if len(filenames) != 1 else ""}</div>'
            if filenames
            else '<div class="detail-chip">No linked images</div>'
        )
        if has_image and preview_name:
            preview_note = f'<div class="detail-chip">Primary preview: {html.escape(preview_name)}</div>'
        elif preview_name:
            preview_note = (
                f'<div class="detail-chip detail-chip-warn">{html.escape(preview_name)} missing on disk</div>'
            )
        else:
            preview_note = '<div class="detail-chip detail-chip-warn">No preview image listed</div>'

        multi_badge = ""
        if len(filenames) > 1:
            multi_badge = f'<span class="thumb-count">+{len(filenames) - 1}</span>'

        table_rows.append(
            f'<tr class="summary-row" '
            f'data-item-id="{html.escape(item_id, quote=True)}" '
            f'data-category="{html.escape((row.get("Category") or "").strip(), quote=True)}" '
            f'data-base-search="{html.escape(base_search_blob, quote=True)}" '
            f'data-search="{html.escape(search_blob, quote=True)}">'
            '<td class="preview-cell">'
            '<div class="thumb-stack">'
            f'{preview_markup}'
            f'{multi_badge}'
            '</div>'
            '</td>'
            f'<td class="id-cell">{html.escape(item_id_display)}</td>'
            f'<td data-summary-field="Category">{html.escape(format_value(row.get("Category", "")))}</td>'
            f'<td data-summary-field="Sub-Category">{html.escape(format_value(row.get("Sub-Category", "")))}</td>'
            f'<td data-summary-field="Brand">{html.escape(format_value(row.get("Brand", "")))}</td>'
            f'<td data-summary-field="Color">{html.escape(format_color(row))}</td>'
            f'<td data-summary-field="Pattern">{html.escape(format_value(row.get("Pattern", "")))}</td>'
            '<td class="toggle-cell">'
            f'<button type="button" class="toggle-button" data-target="{detail_id}" aria-expanded="false">Show more</button>'
            '</td>'
            '</tr>'
            f'<tr class="detail-row" id="{detail_id}" data-item-id="{html.escape(item_id, quote=True)}" hidden>'
            f'<td colspan="{summary_column_count}">'
            '<div class="detail-panel">'
            '<div class="detail-panel-top">'
            '<div>'
            f'<h3>{html.escape(item_id_display)}</h3>'
            '<p>Full CSV row in live column order. Editable fields stay local until you export a patch JSON and apply it with the companion script.</p>'
            '</div>'
            '<div class="detail-chip-row">'
            f'{image_meta}'
            f'{preview_note}'
            f'<div class="detail-chip">{editable_count} editable fields</div>'
            '<div class="detail-chip detail-chip-edit-count" data-edit-count-for="'
            f'{html.escape(item_id, quote=True)}">0 pending edits</div>'
            '</div>'
            '</div>'
            '<div class="detail-grid">'
            f'{"".join(detail_cells)}'
            '</div>'
            '</div>'
            '</td>'
            '</tr>'
        )

    export_meta_json = html.escape(json.dumps(export_meta, ensure_ascii=True), quote=False)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Wardrobe Catalog Table</title>
  <style>
    :root {{
      --bg: #f4efe7;
      --panel: rgba(255, 251, 246, 0.94);
      --panel-strong: #fffdfa;
      --ink: #17212b;
      --muted: #5f6c78;
      --line: #d7cbbd;
      --accent: #8f3f2b;
      --accent-soft: rgba(143, 63, 43, 0.12);
      --accent-strong: #244d61;
      --success: #1f6b57;
      --success-soft: rgba(31, 107, 87, 0.12);
      --shadow: 0 18px 42px rgba(23, 33, 43, 0.1);
      --radius: 22px;
    }}
    * {{
      box-sizing: border-box;
    }}
    html {{
      scroll-behavior: smooth;
    }}
    body {{
      margin: 0;
      color: var(--ink);
      font-family: "Avenir Next", "Helvetica Neue", Helvetica, Arial, sans-serif;
      background:
        linear-gradient(140deg, rgba(36, 77, 97, 0.08), transparent 35%),
        radial-gradient(circle at top right, rgba(143, 63, 43, 0.12), transparent 28%),
        linear-gradient(180deg, #f7f2ea 0%, var(--bg) 100%);
    }}
    button,
    input,
    select,
    textarea {{
      font: inherit;
    }}
    button {{
      cursor: pointer;
    }}
    .page {{
      width: min(1600px, calc(100vw - 28px));
      margin: 0 auto;
      padding: 24px 0 56px;
    }}
    .hero,
    .controls,
    .table-shell {{
      background: var(--panel);
      border: 1px solid rgba(215, 203, 189, 0.9);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
      backdrop-filter: blur(14px);
    }}
    .hero {{
      padding: 28px;
      overflow: hidden;
      position: relative;
    }}
    .hero::after {{
      content: "";
      position: absolute;
      inset: auto -4% -48% auto;
      width: 360px;
      height: 360px;
      border-radius: 50%;
      background: radial-gradient(circle, rgba(36, 77, 97, 0.12), transparent 66%);
      pointer-events: none;
    }}
    .hero h1 {{
      margin: 0;
      max-width: 13ch;
      font-family: "Baskerville", "Iowan Old Style", "Palatino Linotype", serif;
      font-size: clamp(2.3rem, 5vw, 4.8rem);
      line-height: 0.93;
      letter-spacing: -0.05em;
    }}
    .hero p {{
      margin: 16px 0 0;
      max-width: 74ch;
      color: var(--muted);
      line-height: 1.55;
      font-size: 1rem;
    }}
    .hero-meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 18px;
    }}
    .hero-chip {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 9px 12px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.7);
      border: 1px solid rgba(215, 203, 189, 0.9);
      color: var(--muted);
      font-size: 0.92rem;
    }}
    .stats {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
      gap: 14px;
      margin-top: 22px;
    }}
    .stat {{
      padding: 18px;
      border-radius: 18px;
      background: rgba(255, 255, 255, 0.72);
      border: 1px solid rgba(215, 203, 189, 0.9);
    }}
    .stat-label {{
      display: block;
      color: var(--muted);
      font-size: 0.78rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }}
    .stat-value {{
      display: block;
      margin-top: 8px;
      font-size: clamp(1.8rem, 3vw, 2.4rem);
      line-height: 1;
    }}
    .controls {{
      margin-top: 20px;
      padding: 18px 20px;
    }}
    .controls-grid {{
      display: grid;
      grid-template-columns: minmax(220px, 1.6fr) minmax(180px, 0.7fr) auto;
      gap: 12px;
      align-items: end;
    }}
    .control {{
      display: grid;
      gap: 6px;
      color: var(--muted);
      font-size: 0.92rem;
    }}
    .control input,
    .control select {{
      width: 100%;
      padding: 11px 13px;
      border-radius: 14px;
      border: 1px solid var(--line);
      background: var(--panel-strong);
      color: var(--ink);
    }}
    .control-actions {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }}
    .action-button,
    .toggle-button,
    .reset-field-button {{
      border: 0;
      border-radius: 999px;
      transition: transform 0.16s ease, background 0.16s ease, color 0.16s ease;
    }}
    .action-button {{
      padding: 12px 16px;
      background: var(--accent-strong);
      color: #fff;
    }}
    .action-button.secondary {{
      background: rgba(36, 77, 97, 0.1);
      color: var(--accent-strong);
    }}
    .action-button.export {{
      background: var(--success);
    }}
    .action-button:hover,
    .toggle-button:hover,
    .thumb-button:hover,
    .reset-field-button:hover {{
      transform: translateY(-1px);
    }}
    .status-bar {{
      margin-top: 14px;
      color: var(--muted);
      font-size: 0.94rem;
      line-height: 1.45;
    }}
    .table-shell {{
      margin-top: 20px;
      overflow: hidden;
    }}
    .table-wrap {{
      overflow-x: auto;
    }}
    table {{
      width: 100%;
      min-width: 1160px;
      border-collapse: separate;
      border-spacing: 0;
    }}
    thead th {{
      position: sticky;
      top: 0;
      z-index: 2;
      background: rgba(247, 242, 234, 0.96);
      padding: 14px 16px;
      text-align: left;
      font-size: 0.8rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--muted);
      border-bottom: 1px solid var(--line);
    }}
    tbody td {{
      padding: 14px 16px;
      border-bottom: 1px solid rgba(215, 203, 189, 0.8);
      vertical-align: middle;
      background: rgba(255, 255, 255, 0.4);
    }}
    tbody tr.summary-row:hover td {{
      background: rgba(255, 255, 255, 0.72);
    }}
    .summary-row.has-pending-edits td {{
      background: rgba(31, 107, 87, 0.06);
    }}
    .preview-cell {{
      width: 98px;
    }}
    .thumb-stack {{
      position: relative;
      display: inline-flex;
    }}
    .thumb-button {{
      padding: 0;
      border: 1px solid rgba(215, 203, 189, 0.96);
      border-radius: 18px;
      background: #e9ded0;
      overflow: hidden;
      box-shadow: 0 12px 28px rgba(23, 33, 43, 0.12);
    }}
    .thumb-image {{
      display: block;
      width: 72px;
      height: 92px;
      object-fit: cover;
    }}
    .thumb-image-large {{
      width: 100%;
      height: auto;
      max-height: 82vh;
      object-fit: contain;
      background: #f1e7da;
    }}
    .thumb-placeholder {{
      display: grid;
      place-items: center;
      width: 72px;
      height: 92px;
      padding: 8px;
      text-align: center;
      font-size: 0.78rem;
      color: var(--muted);
      background: #ece4d8;
    }}
    .thumb-count {{
      position: absolute;
      right: -6px;
      bottom: -6px;
      min-width: 30px;
      padding: 5px 8px;
      border-radius: 999px;
      background: var(--accent);
      color: #fff;
      font-size: 0.78rem;
      text-align: center;
      box-shadow: 0 10px 18px rgba(143, 63, 43, 0.24);
    }}
    .id-cell {{
      font-weight: 700;
      letter-spacing: 0.03em;
    }}
    .toggle-cell {{
      width: 128px;
    }}
    .toggle-button {{
      width: 100%;
      padding: 10px 14px;
      background: rgba(143, 63, 43, 0.12);
      color: var(--accent);
    }}
    .toggle-button[aria-expanded="true"] {{
      background: rgba(36, 77, 97, 0.12);
      color: var(--accent-strong);
    }}
    .detail-row td {{
      padding: 0;
      background: rgba(245, 239, 231, 0.92);
    }}
    .detail-panel {{
      padding: 22px;
    }}
    .detail-panel-top {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: start;
      margin-bottom: 18px;
    }}
    .detail-panel-top h3 {{
      margin: 0;
      font-size: 1.25rem;
    }}
    .detail-panel-top p {{
      margin: 6px 0 0;
      color: var(--muted);
      max-width: 70ch;
    }}
    .detail-chip-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      justify-content: flex-end;
    }}
    .detail-chip {{
      padding: 8px 12px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.8);
      border: 1px solid rgba(215, 203, 189, 0.9);
      color: var(--muted);
      font-size: 0.88rem;
    }}
    .detail-chip-warn {{
      color: var(--accent);
    }}
    .detail-chip-edit-count.has-edits {{
      background: var(--success-soft);
      border-color: rgba(31, 107, 87, 0.28);
      color: var(--success);
    }}
    .detail-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 12px;
    }}
    .detail-field {{
      min-height: 100%;
      padding: 14px;
      border-radius: 16px;
      background: rgba(255, 255, 255, 0.78);
      border: 1px solid rgba(215, 203, 189, 0.86);
    }}
    .detail-field.is-editable {{
      border-style: solid;
    }}
    .detail-field.is-edited {{
      border-color: rgba(31, 107, 87, 0.4);
      background: rgba(31, 107, 87, 0.06);
    }}
    .detail-field-top {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: start;
    }}
    .detail-label {{
      color: var(--muted);
      font-size: 0.76rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }}
    .detail-value {{
      margin-top: 8px;
      line-height: 1.45;
      white-space: pre-wrap;
      word-break: break-word;
    }}
    .field-tools {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }}
    .field-status {{
      color: var(--success);
      font-size: 0.8rem;
    }}
    .reset-field-button {{
      padding: 6px 10px;
      background: rgba(23, 33, 43, 0.08);
      color: var(--ink);
      font-size: 0.82rem;
    }}
    .edit-control {{
      width: 100%;
      padding: 10px 12px;
      border-radius: 12px;
      border: 1px solid rgba(215, 203, 189, 0.96);
      background: rgba(255, 255, 255, 0.96);
      color: var(--ink);
    }}
    .edit-control:focus {{
      outline: 2px solid rgba(36, 77, 97, 0.18);
      border-color: rgba(36, 77, 97, 0.5);
    }}
    .edit-control-textarea {{
      resize: vertical;
      min-height: 110px;
    }}
    .file-pill {{
      display: inline-flex;
      align-items: center;
      margin: 0 8px 8px 0;
      padding: 8px 10px;
      border-radius: 999px;
      background: rgba(36, 77, 97, 0.1);
      color: var(--accent-strong);
      text-decoration: none;
    }}
    .file-pill:hover {{
      background: rgba(36, 77, 97, 0.18);
    }}
    .file-pill-missing {{
      background: rgba(143, 63, 43, 0.12);
      color: var(--accent);
    }}
    .empty-value {{
      color: var(--muted);
    }}
    .modal[hidden] {{
      display: none;
    }}
    .modal {{
      position: fixed;
      inset: 0;
      z-index: 30;
      display: grid;
      place-items: center;
      padding: 28px;
      background: rgba(10, 16, 22, 0.72);
      backdrop-filter: blur(4px);
    }}
    .modal-panel {{
      width: min(900px, 100%);
      max-height: calc(100vh - 56px);
      overflow: auto;
      padding: 20px;
      border-radius: 26px;
      background: rgba(255, 251, 246, 0.98);
      box-shadow: 0 24px 60px rgba(10, 16, 22, 0.32);
    }}
    .modal-top {{
      display: flex;
      justify-content: space-between;
      align-items: start;
      gap: 16px;
      margin-bottom: 16px;
    }}
    .modal-top h2 {{
      margin: 0;
      font-size: 1.1rem;
    }}
    .modal-top p {{
      margin: 6px 0 0;
      color: var(--muted);
    }}
    .modal-close {{
      border: 0;
      border-radius: 999px;
      padding: 10px 14px;
      background: rgba(23, 33, 43, 0.08);
      color: var(--ink);
    }}
    .modal-image-wrap {{
      border-radius: 20px;
      overflow: hidden;
      background: linear-gradient(180deg, #f6eee3 0%, #ede3d4 100%);
    }}
    .empty-state {{
      padding: 56px 24px;
      text-align: center;
      color: var(--muted);
    }}
    @media (max-width: 980px) {{
      .controls-grid {{
        grid-template-columns: 1fr;
      }}
      .control-actions {{
        justify-content: flex-start;
      }}
      .detail-panel-top {{
        flex-direction: column;
      }}
      .detail-chip-row {{
        justify-content: flex-start;
      }}
      .modal {{
        padding: 16px;
      }}
    }}
  </style>
</head>
<body>
  <div class="page">
    <section class="hero">
      <h1>Wardrobe Catalog Table</h1>
      <p>This is a separate, edit-capable viewer for <code>working/wardrobe_catalog.csv</code>. The row stays compact for scanning, the detail row preserves the full live header order, and edits stay local until you export a patch JSON for the companion apply script.</p>
      <div class="hero-meta">
        <span class="hero-chip">Generated: {html.escape(generated_at)}</span>
        <span class="hero-chip">Catalog CSV mtime: {html.escape(export_meta["catalog_csv_mtime"])}</span>
        <span class="hero-chip">Editable fields: {len(EDITABLE_FIELDS)}</span>
      </div>
      <div class="stats">
        <div class="stat">
          <span class="stat-label">Items</span>
          <span class="stat-value">{len(sorted_rows)}</span>
        </div>
        <div class="stat">
          <span class="stat-label">Categories</span>
          <span class="stat-value">{len(categories)}</span>
        </div>
        <div class="stat">
          <span class="stat-label">Columns</span>
          <span class="stat-value">{len(headers)}</span>
        </div>
        <div class="stat">
          <span class="stat-label">Multi-image items</span>
          <span class="stat-value">{total_multi_image}</span>
        </div>
      </div>
    </section>

    <section class="controls">
      <div class="controls-grid">
        <label class="control">
          <span>Search items</span>
          <input id="searchInput" type="search" placeholder="Search item ID, category, brand, color, vibe, occasion, notes">
        </label>
        <label class="control">
          <span>Category</span>
          <select id="categoryFilter">
            <option value="">All categories</option>
            {category_options}
          </select>
        </label>
        <div class="control-actions">
          <button id="expandAllButton" type="button" class="action-button">Expand all</button>
          <button id="collapseAllButton" type="button" class="action-button secondary">Collapse all</button>
          <button id="clearEditsButton" type="button" class="action-button secondary">Clear edits</button>
          <button id="exportEditsButton" type="button" class="action-button export">Export edits</button>
        </div>
      </div>
      <div id="statusBar" class="status-bar"></div>
    </section>

    <section class="table-shell">
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Preview</th>
              <th>Item ID</th>
              <th>Category</th>
              <th>Sub-Category</th>
              <th>Brand</th>
              <th>Color</th>
              <th>Pattern</th>
              <th>More</th>
            </tr>
          </thead>
          <tbody id="catalogTableBody">
            {"".join(table_rows) if table_rows else f'<tr><td colspan="{summary_column_count}" class="empty-state">No catalog rows found.</td></tr>'}
          </tbody>
        </table>
      </div>
    </section>
  </div>

  <div id="imageModal" class="modal" hidden>
    <div class="modal-panel" role="dialog" aria-modal="true" aria-labelledby="modalTitle">
      <div class="modal-top">
        <div>
          <h2 id="modalTitle">Image preview</h2>
          <p id="modalCaption"></p>
        </div>
        <button id="modalCloseButton" type="button" class="modal-close">Close</button>
      </div>
      <div class="modal-image-wrap">
        <img id="modalImage" class="thumb-image-large" alt="">
      </div>
    </div>
  </div>

  <script>
    const EXPORT_META = {export_meta_json};
    const SUMMARY_SOURCE_FIELDS = {json.dumps(SUMMARY_SOURCE_FIELDS, ensure_ascii=True)};
    const searchInput = document.getElementById("searchInput");
    const categoryFilter = document.getElementById("categoryFilter");
    const statusBar = document.getElementById("statusBar");
    const expandAllButton = document.getElementById("expandAllButton");
    const collapseAllButton = document.getElementById("collapseAllButton");
    const clearEditsButton = document.getElementById("clearEditsButton");
    const exportEditsButton = document.getElementById("exportEditsButton");
    const modal = document.getElementById("imageModal");
    const modalImage = document.getElementById("modalImage");
    const modalCaption = document.getElementById("modalCaption");
    const modalCloseButton = document.getElementById("modalCloseButton");
    const summaryRows = Array.from(document.querySelectorAll(".summary-row"));
    const editControls = Array.from(document.querySelectorAll(".edit-control"));
    const pendingEdits = {{}};

    function getDetailRow(summaryRow) {{
      const toggleButton = summaryRow.querySelector(".toggle-button");
      if (!toggleButton) {{
        return null;
      }}
      return document.getElementById(toggleButton.dataset.target);
    }}

    function getControlValue(control) {{
      return control.value;
    }}

    function setExpanded(summaryRow, shouldExpand) {{
      const toggleButton = summaryRow.querySelector(".toggle-button");
      const detailRow = getDetailRow(summaryRow);
      if (!toggleButton || !detailRow) {{
        return;
      }}

      const rowVisible = summaryRow.style.display !== "none";
      const nextExpanded = shouldExpand && rowVisible;
      toggleButton.setAttribute("aria-expanded", nextExpanded ? "true" : "false");
      toggleButton.textContent = nextExpanded ? "Hide details" : "Show more";
      detailRow.hidden = !nextExpanded;
    }}

    function visibleSummaryRows() {{
      return summaryRows.filter((row) => row.style.display !== "none");
    }}

    function getItemControls(itemId) {{
      return editControls.filter((control) => control.dataset.itemId === itemId);
    }}

    function ensureItemBucket(itemId) {{
      if (!pendingEdits[itemId]) {{
        pendingEdits[itemId] = {{}};
      }}
      return pendingEdits[itemId];
    }}

    function summarizePendingEditCount() {{
      let items = 0;
      let fields = 0;
      Object.values(pendingEdits).forEach((itemChanges) => {{
        const fieldNames = Object.keys(itemChanges);
        if (!fieldNames.length) {{
          return;
        }}
        items += 1;
        fields += fieldNames.length;
      }});
      return {{ items, fields }};
    }}

    function computeColorForItem(itemId) {{
      const primaryControl = getItemControls(itemId).find((control) => control.dataset.fieldName === "Color (Primary)");
      const secondaryControl = getItemControls(itemId).find((control) => control.dataset.fieldName === "Color (Secondary)");
      const primary = primaryControl ? primaryControl.value.trim() : "";
      const secondary = secondaryControl ? secondaryControl.value.trim() : "";
      if (secondary && secondary !== "—") {{
        return `${{primary}} / ${{secondary}}`;
      }}
      return primary || "-";
    }}

    function updateSummaryRow(itemId) {{
      const row = summaryRows.find((entry) => entry.dataset.itemId === itemId);
      if (!row) {{
        return;
      }}

      Object.entries(SUMMARY_SOURCE_FIELDS).forEach(([summaryField, sourceField]) => {{
        const cell = row.querySelector(`[data-summary-field="${{summaryField}}"]`);
        const control = getItemControls(itemId).find((entry) => entry.dataset.fieldName === sourceField);
        if (!cell || !control) {{
          return;
        }}
        const nextValue = control.value.trim() || "-";
        cell.textContent = nextValue;
      }});

      const colorCell = row.querySelector('[data-summary-field="Color"]');
      if (colorCell) {{
        colorCell.textContent = computeColorForItem(itemId);
      }}

      const nextCategory = getItemControls(itemId).find((entry) => entry.dataset.fieldName === "Category");
      if (nextCategory) {{
        row.dataset.category = nextCategory.value.trim();
      }}
    }}

    function updateSearchIndex(itemId) {{
      const row = summaryRows.find((entry) => entry.dataset.itemId === itemId);
      if (!row) {{
        return;
      }}
      const editableSearch = getItemControls(itemId)
        .map((control) => control.value)
        .join(" ")
        .toLowerCase();
      row.dataset.search = `${{row.dataset.baseSearch}} ${{editableSearch}}`.trim();
    }}

    function persistPendingEdits() {{
      localStorage.setItem(EXPORT_META.local_storage_key, JSON.stringify(pendingEdits));
    }}

    function clearPendingEditsState() {{
      Object.keys(pendingEdits).forEach((itemId) => delete pendingEdits[itemId]);
      localStorage.removeItem(EXPORT_META.local_storage_key);
    }}

    function updateFieldUi(control, isEdited) {{
      const field = control.closest(".detail-field");
      if (!field) {{
        return;
      }}
      field.classList.toggle("is-edited", isEdited);
      const fieldStatus = field.querySelector(".field-status");
      const resetButton = field.querySelector(".reset-field-button");
      if (fieldStatus) {{
        fieldStatus.hidden = !isEdited;
      }}
      if (resetButton) {{
        resetButton.hidden = !isEdited;
      }}
    }}

    function updateItemUi(itemId) {{
      const itemChanges = pendingEdits[itemId] || {{}};
      const fieldCount = Object.keys(itemChanges).length;
      const summaryRow = summaryRows.find((entry) => entry.dataset.itemId === itemId);
      if (summaryRow) {{
        summaryRow.classList.toggle("has-pending-edits", fieldCount > 0);
      }}
      const editCountChip = document.querySelector(`[data-edit-count-for="${{CSS.escape(itemId)}}"]`);
      if (editCountChip) {{
        editCountChip.textContent = `${{fieldCount}} pending edit${{fieldCount === 1 ? "" : "s"}}`;
        editCountChip.classList.toggle("has-edits", fieldCount > 0);
      }}
      updateSummaryRow(itemId);
    }}

    function applyControlState(control) {{
      const itemId = control.dataset.itemId;
      const fieldName = control.dataset.fieldName;
      const originalValue = control.dataset.originalValue;
      const currentValue = getControlValue(control);
      const hasChanged = currentValue !== originalValue;

      if (hasChanged) {{
        const bucket = ensureItemBucket(itemId);
        bucket[fieldName] = {{
          old_value: originalValue,
          new_value: currentValue,
        }};
      }} else if (pendingEdits[itemId]) {{
        delete pendingEdits[itemId][fieldName];
        if (!Object.keys(pendingEdits[itemId]).length) {{
          delete pendingEdits[itemId];
        }}
      }}

      updateFieldUi(control, hasChanged);
      updateItemUi(itemId);
      updateSearchIndex(itemId);
      updateStatusBar();
      persistPendingEdits();
    }}

    function applyFilters() {{
      const query = searchInput.value.trim().toLowerCase();
      const category = categoryFilter.value.trim();

      summaryRows.forEach((summaryRow) => {{
        const matchesSearch = !query || summaryRow.dataset.search.includes(query);
        const matchesCategory = !category || summaryRow.dataset.category === category;
        const shouldShow = matchesSearch && matchesCategory;
        const detailRow = getDetailRow(summaryRow);

        summaryRow.style.display = shouldShow ? "" : "none";
        if (!shouldShow) {{
          setExpanded(summaryRow, false);
        }}
        if (detailRow) {{
          detailRow.style.display = shouldShow ? "" : "none";
        }}
      }});

      updateStatusBar();
    }}

    function buildExportPayload() {{
      const edits = Object.entries(pendingEdits)
        .filter(([, changes]) => Object.keys(changes).length)
        .map(([itemId, changes]) => ({{
          item_id: itemId,
          changes,
        }}));

      return {{
        schema_version: EXPORT_META.schema_version,
        exported_at: new Date().toISOString(),
        source: {{
          wardrobe_root: EXPORT_META.wardrobe_root,
          catalog_csv: EXPORT_META.catalog_csv,
          catalog_csv_mtime: EXPORT_META.catalog_csv_mtime,
          page_generated_at: EXPORT_META.page_generated_at,
          row_count: EXPORT_META.row_count,
        }},
        editable_fields: EXPORT_META.editable_fields,
        edits,
      }};
    }}

    function exportEdits() {{
      const payload = buildExportPayload();
      if (!payload.edits.length) {{
        updateStatusBar("No pending edits to export.");
        return;
      }}

      const stamp = new Date().toISOString().replace(/[:.]/g, "-");
      const filename = `wardrobe-catalog-edits-${{stamp}}.json`;
      const blob = new Blob([JSON.stringify(payload, null, 2)], {{ type: "application/json" }});
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      updateStatusBar(`Exported ${{payload.edits.length}} edited item patch${{payload.edits.length === 1 ? "" : "es"}} to ${{filename}}.`);
    }}

    function resetControl(control) {{
      control.value = control.dataset.originalValue;
      applyControlState(control);
    }}

    function clearAllEdits() {{
      editControls.forEach((control) => {{
        control.value = control.dataset.originalValue;
        updateFieldUi(control, false);
      }});
      clearPendingEditsState();
      summaryRows.forEach((row) => {{
        row.classList.remove("has-pending-edits");
        updateSummaryRow(row.dataset.itemId);
        updateSearchIndex(row.dataset.itemId);
      }});
      document.querySelectorAll(".detail-chip-edit-count").forEach((chip) => {{
        chip.textContent = "0 pending edits";
        chip.classList.remove("has-edits");
      }});
      updateStatusBar("Cleared all local edits.");
    }}

    function updateStatusBar(message = "") {{
      const visibleCount = visibleSummaryRows().length;
      const totalCount = summaryRows.length;
      const expandedCount = visibleSummaryRows().filter((row) => {{
        const toggleButton = row.querySelector(".toggle-button");
        return toggleButton && toggleButton.getAttribute("aria-expanded") === "true";
      }}).length;
      const editSummary = summarizePendingEditCount();
      const base = `${{visibleCount}} of ${{totalCount}} items visible. ${{expandedCount}} expanded. ${{editSummary.fields}} pending field edit${{editSummary.fields === 1 ? "" : "s"}} across ${{editSummary.items}} item${{editSummary.items === 1 ? "" : "s"}}.`;
      statusBar.textContent = message ? `${{base}} ${{message}}` : base;
    }}

    function restorePendingEdits() {{
      const raw = localStorage.getItem(EXPORT_META.local_storage_key);
      if (!raw) {{
        return;
      }}

      try {{
        const parsed = JSON.parse(raw);
        if (!parsed || typeof parsed !== "object") {{
          return;
        }}

        Object.entries(parsed).forEach(([itemId, fields]) => {{
          if (!fields || typeof fields !== "object") {{
            return;
          }}

          Object.entries(fields).forEach(([fieldName, change]) => {{
            const control = editControls.find(
              (entry) => entry.dataset.itemId === itemId && entry.dataset.fieldName === fieldName
            );
            if (!control || !change || typeof change !== "object") {{
              return;
            }}
            const nextValue = typeof change.new_value === "string" ? change.new_value : control.dataset.originalValue;
            control.value = nextValue;
            applyControlState(control);
          }});
        }});
      }} catch (error) {{
        console.error("Failed to restore local edits", error);
      }}
    }}

    function closeModal() {{
      modal.hidden = true;
      modalImage.removeAttribute("src");
      modalImage.alt = "";
      modalCaption.textContent = "";
      document.body.style.overflow = "";
    }}

    document.addEventListener("click", (event) => {{
      const toggleButton = event.target.closest(".toggle-button");
      if (toggleButton) {{
        const summaryRow = toggleButton.closest(".summary-row");
        const isExpanded = toggleButton.getAttribute("aria-expanded") === "true";
        setExpanded(summaryRow, !isExpanded);
        updateStatusBar();
        return;
      }}

      const thumbButton = event.target.closest(".thumb-button");
      if (thumbButton) {{
        modalImage.src = thumbButton.dataset.imageSrc;
        modalImage.alt = thumbButton.dataset.imageAlt;
        modalCaption.textContent = thumbButton.dataset.imageCaption;
        modal.hidden = false;
        document.body.style.overflow = "hidden";
        return;
      }}

      const resetButton = event.target.closest(".reset-field-button");
      if (resetButton) {{
        const field = resetButton.closest(".detail-field");
        const control = field ? field.querySelector(".edit-control") : null;
        if (control) {{
          resetControl(control);
        }}
        return;
      }}

      if (event.target === modal) {{
        closeModal();
      }}
    }});

    editControls.forEach((control) => {{
      control.addEventListener("input", () => applyControlState(control));
      control.addEventListener("change", () => applyControlState(control));
    }});

    modalCloseButton.addEventListener("click", closeModal);

    document.addEventListener("keydown", (event) => {{
      if (event.key === "Escape") {{
        if (!modal.hidden) {{
          closeModal();
          return;
        }}
        summaryRows.forEach((row) => setExpanded(row, false));
        updateStatusBar();
      }}
    }});

    expandAllButton.addEventListener("click", () => {{
      visibleSummaryRows().forEach((row) => setExpanded(row, true));
      updateStatusBar();
    }});

    collapseAllButton.addEventListener("click", () => {{
      summaryRows.forEach((row) => setExpanded(row, false));
      updateStatusBar();
    }});

    clearEditsButton.addEventListener("click", clearAllEdits);
    exportEditsButton.addEventListener("click", exportEdits);
    searchInput.addEventListener("input", applyFilters);
    categoryFilter.addEventListener("change", applyFilters);

    restorePendingEdits();
    applyFilters();
  </script>
</body>
</html>
"""


def main() -> None:
    args = parse_args()
    output_path = args.output.resolve()
    headers, rows = read_catalog(CATALOG)
    rendered = render_html(headers, rows, output_path)
    output_path.write_text(rendered, encoding="utf-8")
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
