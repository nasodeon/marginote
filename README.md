# Marginote

Self-hosted book quotes and reading notes. Photograph a page, select the passage, add a note and tags,
and file it under the book. Your notes and photos stay on your own server; the app is reachable only
through your private Tailscale network.

## What is here

- `app/` — the backend: FastAPI, SQLite full-text search, Tesseract text recognition (French and English)
  with shadow removal and straightening of pages that curve toward the spine (Leptonica), page-number
  detection, book details and covers from Open Library (Google Books as fallback)
- `docker-compose.yml` — what you paste into your Docker app: the app plus a Tailscale container that
  gives it a private HTTPS address
- `.github/workflows/image.yml` — on every push, runs the tests and publishes the image to
  `ghcr.io/<owner>/marginote`

## Install

1. In the Tailscale admin console, turn on MagicDNS and HTTPS certificates, and create an auth key.
2. Create two folders on your server: `.../marginote/data` and `.../marginote/tailscale`.
3. Paste `docker-compose.yml` into your Docker app, replace the values marked `CHANGE-ME` (and the
   folder paths if yours differ), and deploy.
4. Open `https://marginote.<your-tailnet>.ts.net` from a device on your tailnet.

The first page is a plain test page; `/docs` lists every API call.

## Update

Pull the new image and recreate the `marginote` container (the compose file sets `pull_policy: always`).
The data folder is never touched.

## Data

Everything lives in the data folder: `marginote.db` (books, quotes, tags), `photos/` (page photos),
`covers/`, and `backups/` (a database snapshot every night at 03:00, last 14 kept).

When a page was curved, the photo kept is the straightened one, since the word positions used to
select a passage refer to it.

## Options

Set in the compose file's `environment` list; all optional.

| Variable | Default | What it does |
| --- | --- | --- |
| `OCR_LANGS` | `fra+eng` | Languages to read |
| `LOOKUPS_ENABLED` | `true` | Look up books and covers online |
| `STRAIGHTEN_PAGES` | `true` | Straighten curved pages before reading (`false` keeps photos exactly as taken) |
| `UNUSED_PHOTO_HOURS` | `24` | Delete photos no quote uses after this many hours |
| `TZ` | `UTC` | Time zone, for the nightly backup hour |

## Privacy

- Nothing leaves your server except book lookups: an ISBN, or a title and author when a cover is
  searched. Set `LOOKUPS_ENABLED=false` to turn them off.
- The app listens only inside the Tailscale container: it is not reachable from your local network
  or the internet, only from your own tailnet devices.
- Page photos are stored without any metadata (no location, camera or date). The test page also
  shrinks photos on the phone before sending them.
- No access log: your searches and the pages you open are not written to the Docker logs.
- The password lives only in your compose file; it is never written to the database. Changing it
  logs every device out.

## Resources

Measured: about 100 MB of memory at rest, under 300 MB at most while reading a page (one page at a
time), 2 to 4 seconds per page. Tesseract uses a single core.

## Tests

```bash
cd app
pip install -r requirements-dev.txt
pytest
```

Tesseract with the `fra` and `eng` language packs must be installed (Leptonica comes with it; the
straightening tests are skipped if it cannot be found).
