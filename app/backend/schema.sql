PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS items (
  item_id TEXT PRIMARY KEY,
  category TEXT NOT NULL,
  sub_category TEXT NOT NULL,
  brand TEXT NOT NULL,
  color_primary TEXT NOT NULL,
  color_secondary TEXT NOT NULL,
  pattern TEXT NOT NULL,
  fit TEXT NOT NULL,
  rise TEXT NOT NULL,
  length TEXT NOT NULL,
  silhouette TEXT NOT NULL,
  neckline TEXT NOT NULL,
  drape_notes TEXT NOT NULL,
  fit_source TEXT NOT NULL,
  fabric TEXT NOT NULL,
  weight TEXT NOT NULL,
  stretch TEXT NOT NULL,
  breathability TEXT NOT NULL,
  surface_texture TEXT NOT NULL,
  formality INTEGER,
  vibe_tags TEXT NOT NULL,
  occasion_tags TEXT NOT NULL,
  layering_position TEXT NOT NULL,
  season TEXT NOT NULL,
  max_comfortable_temp_c TEXT NOT NULL,
  condition TEXT NOT NULL,
  wear_frequency_estimate TEXT NOT NULL,
  color_temperature TEXT NOT NULL,
  skin_tone_interaction TEXT NOT NULL,
  skin_tone_caution_flag TEXT NOT NULL,
  contrast_level TEXT NOT NULL,
  versatility_score INTEGER,
  role_in_outfit TEXT NOT NULL,
  volume_visual_weight TEXT NOT NULL,
  shoe_type TEXT NOT NULL,
  sole_profile TEXT NOT NULL,
  aesthetic_range TEXT NOT NULL,
  top_compatibility_note TEXT NOT NULL,
  client_notes TEXT NOT NULL,
  raw_json TEXT NOT NULL,
  deleted_at TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS item_images (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  item_id TEXT NOT NULL REFERENCES items(item_id) ON DELETE CASCADE,
  filename TEXT NOT NULL,
  path TEXT NOT NULL,
  image_reference TEXT NOT NULL,
  is_representative INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_item_images_item_id ON item_images(item_id);

CREATE TABLE IF NOT EXISTS conversations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'error')),
  content TEXT NOT NULL,
  structured_payload_json TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages(conversation_id);

CREATE TABLE IF NOT EXISTS saved_outfits (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  time_of_day TEXT NOT NULL,
  occasion TEXT NOT NULL,
  stylist_notes TEXT NOT NULL,
  why_it_works TEXT NOT NULL DEFAULT '',
  wearing_notes TEXT NOT NULL DEFAULT '',
  cautions TEXT NOT NULL DEFAULT '',
  source_conversation_id INTEGER REFERENCES conversations(id) ON DELETE SET NULL,
  source_message_id INTEGER REFERENCES messages(id) ON DELETE SET NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS saved_outfit_items (
  saved_outfit_id INTEGER NOT NULL REFERENCES saved_outfits(id) ON DELETE CASCADE,
  item_id TEXT NOT NULL REFERENCES items(item_id) ON DELETE CASCADE,
  role TEXT NOT NULL,
  sort_order INTEGER NOT NULL,
  PRIMARY KEY (saved_outfit_id, item_id)
);

CREATE TABLE IF NOT EXISTS import_batches (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  status TEXT NOT NULL CHECK (status IN ('uploaded', 'processing', 'needs_review', 'partially_published', 'published', 'failed')),
  original_file_count INTEGER NOT NULL DEFAULT 0,
  uploaded_file_count INTEGER NOT NULL DEFAULT 0,
  processed_file_count INTEGER NOT NULL DEFAULT 0,
  published_item_count INTEGER NOT NULL DEFAULT 0,
  error_message TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS import_images (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  batch_id INTEGER NOT NULL REFERENCES import_batches(id) ON DELETE CASCADE,
  original_filename TEXT NOT NULL,
  canonical_filename TEXT NOT NULL,
  canonical_path TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('uploaded', 'processing', 'processed', 'failed', 'rejected', 'published')),
  draft_item_id INTEGER REFERENCES draft_items(id) ON DELETE SET NULL,
  error_message TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_import_images_batch_id ON import_images(batch_id);
CREATE INDEX IF NOT EXISTS idx_import_images_draft_item_id ON import_images(draft_item_id);

CREATE TABLE IF NOT EXISTS draft_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  batch_id INTEGER NOT NULL REFERENCES import_batches(id) ON DELETE CASCADE,
  status TEXT NOT NULL CHECK (status IN ('generated', 'needs_review', 'published', 'rejected')),
  proposed_item_id TEXT NOT NULL DEFAULT '',
  category TEXT NOT NULL DEFAULT '',
  sub_category TEXT NOT NULL DEFAULT '',
  brand TEXT NOT NULL DEFAULT '',
  color_primary TEXT NOT NULL DEFAULT '',
  color_secondary TEXT NOT NULL DEFAULT '',
  pattern TEXT NOT NULL DEFAULT '',
  fit TEXT NOT NULL DEFAULT '',
  rise TEXT NOT NULL DEFAULT '',
  length TEXT NOT NULL DEFAULT '',
  silhouette TEXT NOT NULL DEFAULT '',
  neckline TEXT NOT NULL DEFAULT '',
  drape_notes TEXT NOT NULL DEFAULT '',
  fit_source TEXT NOT NULL DEFAULT '',
  fabric TEXT NOT NULL DEFAULT '',
  weight TEXT NOT NULL DEFAULT '',
  stretch TEXT NOT NULL DEFAULT '',
  breathability TEXT NOT NULL DEFAULT '',
  surface_texture TEXT NOT NULL DEFAULT '',
  formality INTEGER,
  vibe_tags TEXT NOT NULL DEFAULT '',
  occasion_tags TEXT NOT NULL DEFAULT '',
  layering_position TEXT NOT NULL DEFAULT '',
  season TEXT NOT NULL DEFAULT '',
  max_comfortable_temp_c TEXT NOT NULL DEFAULT '',
  condition TEXT NOT NULL DEFAULT '',
  wear_frequency_estimate TEXT NOT NULL DEFAULT '',
  color_temperature TEXT NOT NULL DEFAULT '',
  skin_tone_interaction TEXT NOT NULL DEFAULT '',
  skin_tone_caution_flag TEXT NOT NULL DEFAULT '',
  contrast_level TEXT NOT NULL DEFAULT '',
  versatility_score INTEGER,
  role_in_outfit TEXT NOT NULL DEFAULT '',
  volume_visual_weight TEXT NOT NULL DEFAULT '',
  shoe_type TEXT NOT NULL DEFAULT '',
  sole_profile TEXT NOT NULL DEFAULT '',
  aesthetic_range TEXT NOT NULL DEFAULT '',
  top_compatibility_note TEXT NOT NULL DEFAULT '',
  client_notes TEXT NOT NULL DEFAULT '',
  image_reference TEXT NOT NULL DEFAULT '',
  generation_notes TEXT NOT NULL DEFAULT '',
  validation_warnings_json TEXT NOT NULL DEFAULT '[]',
  raw_model_json TEXT NOT NULL DEFAULT '{}',
  published_item_id TEXT REFERENCES items(item_id),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_draft_items_batch_id ON draft_items(batch_id);

CREATE TABLE IF NOT EXISTS draft_item_images (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  draft_item_id INTEGER NOT NULL REFERENCES draft_items(id) ON DELETE CASCADE,
  import_image_id INTEGER NOT NULL REFERENCES import_images(id) ON DELETE CASCADE,
  image_reference TEXT NOT NULL DEFAULT '',
  is_representative INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_draft_item_images_draft_item_id ON draft_item_images(draft_item_id);

CREATE TABLE IF NOT EXISTS draft_observations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  batch_id INTEGER NOT NULL REFERENCES import_batches(id) ON DELETE CASCADE,
  draft_item_id INTEGER REFERENCES draft_items(id) ON DELETE CASCADE,
  category TEXT NOT NULL DEFAULT '',
  observation_type TEXT NOT NULL DEFAULT '',
  detail TEXT NOT NULL DEFAULT '',
  action_needed TEXT NOT NULL DEFAULT ''
);
