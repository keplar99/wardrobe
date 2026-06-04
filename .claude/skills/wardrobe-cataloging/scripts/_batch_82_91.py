"""
Per-batch append for Img 82-91 (10 unprocessed files).

Plan:
  - Update existing catalog rows for items that appear in the new images,
    appending new filenames to Item Image Name and Image References.
  - Append one NEW catalog row: TOP-22 (Zara cream linen V-neck shirt).
  - Append 10 entries to image_reference_map.csv (Img 82..91).
  - Append observations.
"""
from __future__ import annotations

import sys
from pathlib import Path
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from append_batch import (  # type: ignore
    CATALOG, REF_MAP, OBS,
    CATALOG_COLS, REF_COLS, OBS_COLS,
    append_catalog, append_reference_map, append_observations,
)

# ---------------------------------------------------------------------------
# 1. Files & image numbers for this batch (alphabetical order from
#    find_unprocessed.py output). Img 82..91.
# ---------------------------------------------------------------------------
BATCH = [
    ("Img 82",  "WhatsApp Image 2026-05-18 at 12.16.16 AM.jpeg"),
    ("Img 83",  "WhatsApp Image 2026-05-18 at 12.16.17 AM.jpeg"),
    ("Img 84",  "WhatsApp Image 2026-05-18 at 12.16.18 AM (1).jpeg"),
    ("Img 85",  "WhatsApp Image 2026-05-18 at 12.16.18 AM.jpeg"),
    ("Img 86",  "WhatsApp Image 2026-05-18 at 12.16.19 AM (1).jpeg"),
    ("Img 87",  "WhatsApp Image 2026-05-18 at 12.16.19 AM.jpeg"),
    ("Img 88",  "WhatsApp Image 2026-05-18 at 12.16.20 AM (1).jpeg"),
    ("Img 89",  "WhatsApp Image 2026-05-18 at 12.16.21 AM (1).jpeg"),
    ("Img 90",  "WhatsApp Image 2026-05-18 at 12.16.25 AM (1).jpeg"),
    ("Img 91",  "WhatsApp Image 2026-05-18 at 12.16.26 AM (1).jpeg"),
]
F = {num: name for num, name in BATCH}

# ---------------------------------------------------------------------------
# 2. Existing-row updates (append filenames + image refs to existing rows).
# ---------------------------------------------------------------------------
# Map: item_id -> list of (filename, image_ref_label) to append.
EXISTING_UPDATES = {
    "TOP-21": [
        (F["Img 82"], "Img 82 (transition/held; tee held in basket, not worn)"),
    ],
    "TOP-13": [
        (F["Img 83"], "Img 83 (worn full-length)"),
        (F["Img 84"], "Img 84 (worn full-length, alt angle)"),
        (F["Img 85"], "Img 85 (worn waist-up close-up)"),
        (F["Img 86"], "Img 86 (worn full-length)"),
    ],
    "TOP-04": [
        (F["Img 87"], "Img 87 (worn full-length) — FIRST worn photo for TOP-04"),
        (F["Img 88"], "Img 88 (worn waist-up close-up)"),
    ],
    "BOT-11": [
        (F["Img 83"], "Img 83 (worn full-length)"),
        (F["Img 84"], "Img 84 (worn full-length, alt angle)"),
        (F["Img 85"], "Img 85 (worn waist-up)"),
        (F["Img 86"], "Img 86 (worn full-length)"),
        (F["Img 87"], "Img 87 (worn full-length)"),
        (F["Img 88"], "Img 88 (worn waist-up)"),
        (F["Img 89"], "Img 89 (worn partial — bottom visible below TOP-22)"),
    ],
    "TOP-11": [
        (F["Img 90"], "Img 90 (worn full-length) — TENTATIVE; possible separate white shirt"),
    ],
    "BOT-10": [
        (F["Img 90"], "Img 90 (worn full-length) — TENTATIVE; bottom identification ambiguous"),
    ],
}


def update_existing_rows():
    df = pd.read_csv(CATALOG)
    for item_id, additions in EXISTING_UPDATES.items():
        mask = df["Item ID"] == item_id
        if mask.sum() != 1:
            raise RuntimeError(f"Expected exactly 1 row for {item_id}, found {mask.sum()}")
        idx = df.index[mask][0]

        existing_names = str(df.at[idx, "Item Image Name"]).strip()
        existing_refs  = str(df.at[idx, "Image References"]).strip()

        new_names = existing_names
        new_refs  = existing_refs
        for fname, ref in additions:
            if fname not in new_names.split(" | "):
                new_names = f"{new_names} | {fname}" if new_names else fname
            # Image References uses comma or pipe historically; use " | "
            new_refs = f"{new_refs} | {ref}" if new_refs else ref

        df.at[idx, "Item Image Name"]  = new_names
        df.at[idx, "Image References"] = new_refs

    df.to_csv(CATALOG, index=False)
    print(f"Updated existing catalog rows: {', '.join(EXISTING_UPDATES.keys())}")


# ---------------------------------------------------------------------------
# 3. NEW catalog row: TOP-22 (Zara cream/off-white linen V-neck shirt).
# ---------------------------------------------------------------------------
TOP_22_ROW = [
    "TOP-22",
    f"{F['Img 89']} | {F['Img 91']}",
    "Img 89 (worn front), Img 91 (flat lay, brand label visible)",
    "Shirt",
    "Short-sleeve open V-neck band-collar linen shirt (boxy/cropped cut)",
    "Zara",
    "Cream / off-white",
    "—",
    "Solid",
    "Relaxed / boxy",
    "",                                   # Rise (top — blank)
    "Short-sleeve",
    "Boxy",
    "V-neck open placket (band neck / no traditional collar)",
    "Worn photo shows boxy drape across shoulders and torso; light linen fabric drapes softly with natural wrinkling; hem sits at/just above the natural waist (slightly cropped silhouette)",
    "Worn photo (Img 89) — ground truth",
    "Linen",
    "Light",
    "No",
    "High",
    "Slubby (linen weave)",
    "2",
    "coastal, minimal, designer-dev, Goa/hippie, artisan, editorial",
    "beach/Goa, brunch, casual hangout, restaurant (casual), date night (casual)",
    "Base / open as outer",
    "Summer, monsoon, all-season warm",
    "38",
    "Good (natural linen wrinkling)",
    "Occasional",
    "Warm",
    "CAUTION - cream/off-white sits close to warm light brown skin tone; risks washing out in soft/warm lighting. Boxy/cropped silhouette also draws attention to the waistline.",
    "YES",
    "Low",
    "3",
    "Both",
    "Low-medium",
    "",  # Shoe Type
    "",  # Sole Profile
    "",  # Aesthetic Range
    "",  # Top Compatibility Note
]


# ---------------------------------------------------------------------------
# 4. image_reference_map.csv rows (Img 82..91).
# ---------------------------------------------------------------------------
REF_ROWS = [
    ["Img 82", F["Img 82"],
     "Top-down POV looking at bare feet on teal/coral patterned rug; legs in slate/charcoal grey full-length trousers visible at top of frame; hand reaching toward a honey-gold garment held in a beige basket below (consistent with TOP-21 tee being held, not worn)",
     "Worn photo",
     "TOP-21",
     "Low-information transition shot taken mid-outfit-change. TOP-21 mapped tentatively based on the held honey-gold garment in the basket. The slate-grey trousers being worn are not confidently identifiable from this angle (possibly an uncataloged grey trouser or jersey pant)."],

    ["Img 83", F["Img 83"],
     "Full-body mirror selfie — cream/off-white crew-neck T-shirt (TOP-13) worn with olive-tan wide-leg pleated trousers (BOT-11); barefoot",
     "Outfit shot",
     "TOP-13, BOT-11",
     "First worn outfit pairing for TOP-13 + BOT-11"],

    ["Img 84", F["Img 84"],
     "Full-body mirror selfie — same TOP-13 + BOT-11 outfit, slightly different angle/lighting",
     "Outfit shot",
     "TOP-13, BOT-11",
     "Duplicate angle of Img 83"],

    ["Img 85", F["Img 85"],
     "Waist-up close-up — same TOP-13 + BOT-11 outfit; clear view of cream tee texture and the front pleating on the olive trousers",
     "Outfit shot",
     "TOP-13, BOT-11",
     "Best detail shot of this outfit pairing"],

    ["Img 86", F["Img 86"],
     "Full-body mirror selfie — same TOP-13 + BOT-11 outfit, another angle",
     "Outfit shot",
     "TOP-13, BOT-11",
     "Duplicate angle of Img 83"],

    ["Img 87", F["Img 87"],
     "Full-body mirror selfie — faded indigo/blue acid-wash graphic tee with chest 'Wild Earth'-style arch/foliage graphic (TOP-04) worn with olive-tan wide-leg pleated trousers (BOT-11); tee fits relaxed/oversized",
     "Outfit shot",
     "TOP-04, BOT-11",
     "FIRST WORN PHOTO for TOP-04 — previously flat-lay only (Img 5). Confirms faded indigo color, oversized/relaxed fit, and the festival-graphic motif."],

    ["Img 88", F["Img 88"],
     "Waist-up close-up — same TOP-04 + BOT-11 outfit; clear view of acid-wash texture and trouser drape at waist",
     "Outfit shot",
     "TOP-04, BOT-11",
     "Detail shot for TOP-04 acid-wash surface and BOT-11 waist pleating"],

    ["Img 89", F["Img 89"],
     "Worn close-up — Zara cream linen short-sleeve open V-neck band-collar shirt (TOP-22, NEW); bottom shows olive/khaki fabric consistent with BOT-11 wide-leg trousers continuing from the same session",
     "Outfit shot",
     "TOP-22, BOT-11",
     "First worn photo for new item TOP-22. Bottom partially visible — mapped to BOT-11 based on session continuity and visible olive fabric drape."],

    ["Img 90", F["Img 90"],
     "Full-body mirror selfie — white long-sleeve button-up shirt with single chest pocket and point/button-down collar worn with full-length black fabric trousers (not denim)",
     "Worn photo",
     "TOP-11, BOT-10",
     "TENTATIVE mappings flagged in observations: shirt resembles TOP-11 (cream long-sleeve button-up) but reads pure-white here, may be a separate shirt; trousers tentatively BOT-10 (black wide-leg) but the silhouette reads slightly less wide than BOT-10's prior worn photos."],

    ["Img 91", F["Img 91"],
     "Flat lay on a floral-printed bedspread of TWO shirts: top is the Zara cream linen short-sleeve open V-neck shirt (TOP-22) with the Zara neck label clearly visible; bottom (partially visible at the lower edge) is a white mandarin/band-collar shirt that is NOT clearly any existing cataloged item",
     "Flat lay",
     "TOP-22",
     "Brand confirmation for TOP-22 (Zara label readable). The partially-visible bottom shirt may be a new uncataloged item — flagged in observations for re-photo."],
]


# ---------------------------------------------------------------------------
# 5. Observations.
# ---------------------------------------------------------------------------
OBS_ROWS = [
    ["TOP-22", "Img 89, Img 91", "Shirt",
     "New item identified — Zara linen V-neck shirt",
     "New TOP-22 added: Zara-branded cream/off-white open V-neck band-collar short-sleeve linen shirt with a boxy/cropped cut. Brand confirmed from neck label visible in Img 91 flat lay. Worn photo (Img 89) shows boxy drape across shoulders and a hem that sits at the natural waist. Skin-tone caution flag set: cream/off-white risks washing out against light brown skin in soft lighting.",
     "No action — flag is for downstream pairing decisions"],

    ["TOP-04", "Img 87, Img 88", "T-Shirt",
     "Worn-photo coverage (RESOLVED)",
     "TOP-04 (faded indigo/blue acid-wash graphic tee with 'Wild Earth'-style arch/foliage chest graphic) now has worn-photo ground truth (Imgs 87-88). Confirms fit reads relaxed/oversized on athletic frame (more relaxed than the flat-lay-only entry implied) and confirms the acid-wash + graphic combination is the focal point. Previously flat-lay only (Img 5).",
     "Fit/silhouette fields in catalog can be promoted from provisional flat-lay reading to ground-truth"],

    ["BOT-11", "Img 83, Img 84, Img 85, Img 86, Img 87, Img 88, Img 89", "Trousers",
     "Additional worn-photo coverage across multiple outfits",
     "BOT-11 (olive-tan wide-leg pleated trousers) appears in 7 additional worn images this batch — paired with TOP-13 (cream crew tee, Imgs 83-86), TOP-04 (acid-wash graphic tee, Imgs 87-88), and TOP-22 (Zara cream linen V-neck, Img 89). All from the same session. Confirms drape and color are consistent across outfits.",
     "No action — additional reference images"],

    ["TOP-13", "Img 83, Img 84, Img 85, Img 86", "T-Shirt",
     "First worn-outfit coverage",
     "TOP-13 (cream/off-white crew tee) now appears as a worn outfit with BOT-11 (olive-tan wide-leg trousers). Four worn images. Confirms fit reads relaxed on athletic frame. Skin-tone caution flag (existing) is borne out — the cream tee + warm olive trouser combination is a low-contrast warm-on-warm block; works in soft lighting but can mute the outfit.",
     "Downstream: when pairing TOP-13, prefer high-contrast bottoms (charcoal, black, indigo) over warm neutrals to avoid the wash-out risk"],

    ["TOP-11", "Img 90", "Shirt",
     "POSSIBLE DUPLICATE or NEW similar shirt",
     "Img 90 shows a white long-sleeve button-up shirt with single chest pocket and point/button-down collar. Tentatively mapped to TOP-11 (cream/off-white long-sleeve button-up with chest pocket). However, the shirt in Img 90 reads as pure white whereas TOP-11 worn photos (Imgs 38-39) read clearly cream. Could be: (a) TOP-11 in different lighting, (b) a separate similar white button-up. Both have a single chest pocket which is a distinctive shared detail.",
     "PHYSICAL CHECK NEEDED — compare TOP-11 shirt directly to the shirt in Img 90. If different, split into a new TOP-XX entry."],

    ["BOT-10", "Img 90", "Trousers",
     "Bottom identification ambiguous",
     "Black full-length fabric trousers (not denim) in Img 90 are tentatively mapped to BOT-10 (black wide-leg trousers). Silhouette in Img 90 reads slightly less wide than BOT-10's prior worn photos (Imgs 22-23) — could be lighting/angle, or could be a separate black fabric trouser not yet cataloged. Not BOT-12 (cropped) since these reach the floor. Not BOT-08 (denim).",
     "PHYSICAL CHECK NEEDED — confirm whether this is BOT-10 or a separate black trouser"],

    ["—", "Img 91", "Shirt",
     "Possible uncataloged white mandarin-collar shirt",
     "Bottom of Img 91 (flat lay) shows a partially-visible WHITE MANDARIN/BAND-COLLAR shirt distinct from TOP-22 (the Zara shirt on top). This bottom shirt does not match TOP-07 (white mandarin collar — but TOP-07 has an indigo dot print, not solid white). It is likely a new uncataloged solid-white mandarin/band-collar shirt. Cannot catalog as a new entry from a partial view.",
     "Re-photograph this bottom shirt fully laid flat to confirm if it is a new uncataloged item"],

    ["—", "Img 82", "—",
     "Low-information transition shot",
     "Img 82 is a top-down POV of bare feet on a patterned rug, taken mid-outfit-change. The honey-gold garment held in the basket below is consistent with TOP-21 (honey gold oversized tee) — mapped on that basis. The slate/charcoal grey full-length trousers visible at the top of the frame are not confidently identifiable from this angle (medium-weight, possibly jersey or chino; could be an uncataloged item or one of the existing dark trousers in difficult lighting).",
     "No action — flag for context only; if more grey trousers appear in later batches, watch for a possible new BOT-XX"],
]


def main() -> None:
    # Step A — update existing rows.
    update_existing_rows()

    # Step B — append the one new catalog row (TOP-22).
    n_cat = append_catalog([TOP_22_ROW])
    print(f"Catalog rows after append: {n_cat}")

    # Step C — append the 10 reference-map rows.
    n_ref = append_reference_map(REF_ROWS)
    print(f"Reference-map rows after append: {n_ref}")

    # Step D — append observations.
    n_obs = append_observations(OBS_ROWS)
    print(f"Observation rows after append: {n_obs}")


if __name__ == "__main__":
    main()
