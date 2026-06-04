"""
example_batch_append.py
-----------------------
Reference template for a per-batch append script. Copy this file, fill
in the row arrays with metadata gathered while reviewing images, and
run it once per batch.

The agent (Claude) typically fills this file inline rather than copying
it around — the file exists so the row schemas (column ORDER and FIELD
COUNT) are documented in one place.

Required column order is enforced by append_batch.py. If any row has
the wrong number of fields, the helper raises ValueError with the
offending row index.

Conventions:
- Use "" (empty string) for "field does not apply" (e.g., Rise on a tee,
  Layering Position on trousers, shoe-only fields on a top). Do NOT use
  "N/A" — the CSVs use blank for inapplicable.
- Use "Cannot determine from photo" ONLY when the data genuinely cannot
  be assessed from the image (e.g., exact fabric blend percentage,
  hidden stretch properties, brand on an unreadable tag).
- Use "—" (em dash) for a deliberately-empty pattern/color-secondary
  on solid-color pieces, to distinguish "solid" from "unknown".
- When merging multiple images into one catalog row, pipe-separate the
  filenames in "Item Image Name": "fileA.jpeg | fileB.jpeg".
"""
import sys
from pathlib import Path

# Make sibling modules importable when this script is invoked by path.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from append_batch import (
    append_catalog,
    append_reference_map,
    append_observations,
)

# ----- 1) Wardrobe catalog rows -----
# Order matches CATALOG_COLS in append_batch.py (40 columns).
catalog_rows = [
    # [
    #     "TOP-09",                                # Item ID
    #     "filename.jpeg",                          # Item Image Name
    #     "Img 21 (flat)",                          # Image References
    #     "T-Shirt",                                # Category
    #     "Crew neck T-shirt",                      # Sub-Category
    #     "Unidentified",                           # Brand
    #     "Bright white", "—", "Solid",             # Color (Primary), (Secondary), Pattern
    #     "Relaxed", "", "Short-sleeve",            # Fit, Rise, Length
    #     "Relaxed", "Crew",                        # Silhouette, Neckline
    #     "No worn photo available",                # Drape Notes
    #     "Flat lay only",                          # Fit Source
    #     "Cotton jersey", "Mid", "Slight",         # Fabric, Weight, Stretch
    #     "High", "Smooth",                         # Breathability, Surface Texture
    #     "2",                                      # Formality (1-5)
    #     "clean, minimal",                         # Vibe Tags
    #     "casual hangout, brunch",                 # Occasion Tags
    #     "Base",                                   # Layering Position
    #     "All-season", "35",                       # Season, Max Comfortable Temp (C)
    #     "Good", "Regular",                        # Condition, Wear Frequency Estimate
    #     "Cool/neutral",                           # Color Temperature
    #     "High contrast against warm skin",        # Skin Tone Interaction
    #     "No",                                     # Skin Tone Caution Flag
    #     "High",                                   # Contrast Level
    #     "5", "Supporting", "Low",                 # Versatility, Role, Volume
    #     "", "", "", "",                           # Shoe-only fields (blank for non-shoes)
    # ],
]

# ----- 2) Image reference map rows -----
# Order matches REF_COLS (6 columns).
ref_rows = [
    # ["Img 21", "filename.jpeg", "White crew tee, flat lay", "Flat lay", "TOP-09", ""],
]

# ----- 3) Observations & open questions rows -----
# Order matches OBS_COLS (6 columns).
obs_rows = [
    # ["TOP-09", "Img 21", "T-Shirt", "Fit verification",
    #  "No worn photo available.", "Worn photo would resolve fit ambiguity"],
]


if __name__ == "__main__":
    n1 = append_catalog(catalog_rows)
    n2 = append_reference_map(ref_rows)
    n3 = append_observations(obs_rows)
    print(f"wardrobe_catalog.csv: {n1} rows")
    print(f"image_reference_map.csv: {n2} rows")
    print(f"observations_open_questions.csv: {n3} rows")
