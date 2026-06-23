# Wardrobe Stylist App

Local chat-first wardrobe stylist app.

## Setup

1. Copy `.env.example` to `.env` or `.env.local`.
2. Fill in:
   - `OPENAI_API_KEY`
   - `OPENAI_MODEL`, using an OpenAI model ID such as `gpt-5.5` or `gpt-5.4-mini`
3. Import the catalog:

```bash
python3 app/backend/import_catalog.py --reset
```

## Run

Start the backend:

```bash
python3 app/backend/server.py
```

Start the frontend:

```bash
cd app/frontend
npm install
npm run dev -- --port 5173
```

Open:

```text
http://127.0.0.1:5173/
```

## Notes

- The app database lives at `app/data/wardrobe.sqlite` by default.
- `working/wardrobe_catalog.csv` is only used by the one-time importer.
- The model sees catalog metadata only; images are served locally as citations.
- No automated tests are included in v1 by request.
