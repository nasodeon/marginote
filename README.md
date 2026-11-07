# Marginote

Self-hosted quotes and notes on what you read, watch and listen to: books, ebooks, articles, videos,
podcasts, talks. Photograph a page or share a link, keep the passage or a comment, say whom and what it is
about, and find it again by source, by person or by topic. Your notes and photos stay on your own server;
the app is reachable only through your private Tailscale network.

## How it is organised

- **Sources**: anything you quote from or comment on. A book (page photos, ISBN, cover), an ebook
  (screenshots), an article (its link opens the page at the passage you kept), a video or podcast (a link
  and comments on the whole), a talk or class, or anything else.
- **People**: who made a source (author, translator, editor, speaker) and whom it is about. Each person has
  a page with four sections: your notes on them, their works, their words quoted elsewhere, and what is
  about them. A passage by Lordon about Spinoza is stored once and shows on both pages.
- **Topics**: today's tags, each with a page: your notes, the people who appear in it, topics often found
  with it, its entries grouped by person, source or date.
- **Notes**: your own writing on people and topics, shown at the top of their pages.

An entry takes its source's people and topics; untick one when a passage is not about it. Its words are its
source author's unless you name someone else (a quote within a quote).

## What is here

- `app/` — the app: FastAPI, SQLite with full-text search, Tesseract text recognition (French and English)
  with shadow removal and straightening of pages that curve toward the spine (Leptonica), page-number
  detection, book details from Open Library, Google Books and the BnF catalogue, the ISBN read from a photo
  of the back cover, page details read from a link, and an inbox of photos sent to be sorted later
- `app/marginote/static/` — the screens, for phone and computer, set like a LaTeX document. Plain
  JavaScript; the fonts (Computer Modern Unicode, SIL Open Font License, Latin subset) are served by the app
- `docker-compose.yml` — what you paste into your Docker app: the app plus a Tailscale container that
  gives it a private HTTPS address
- `.github/workflows/image.yml` — on every push, runs the tests and publishes the image to
  `ghcr.io/<owner>/marginote`, tagged `latest` and with its version (`0.5.1`)

## Install

1. In the Tailscale admin console, turn on MagicDNS and HTTPS certificates, and create an auth key.
2. Create two folders on your server: `.../marginote/data` and `.../marginote/tailscale`.
3. Paste `docker-compose.yml` into your Docker app, replace the values marked `CHANGE-ME` (and the
   folder paths if yours differ), and deploy.
4. Open `https://marginote.<your-tailnet>.ts.net` from a device on your tailnet. On iPhone, Safari's
   Share → Add to Home Screen opens it like an app.

`/docs` lists every API call.

## Update

Stop the project and deploy it again: the compose file sets `pull_policy: always`, so the newest image is
downloaded. The data folder is kept.

When an update changes the shape of the database (0.5.0 does: books become sources, authors become people,
tags become topics), the app first writes a copy of the database as it was to
`data/backups/before-0.5.0-<date>.zip`. Nothing is lost in the change: ids, quotes, comments, notes, pages,
photos and covers all stay.

Do not use a one-click "update" or "recreate" button on the `marginote` container (UGOS, Portainer…): it
shares the Tailscale container's network, and those buttons cannot rebuild such a container (Docker
answers "conflicting options: hostname and the network mode"), which leaves it deleted.

### Going back to version 0.4.0

1. Stop the project.
2. In `data/`, move `marginote.db` aside (and `marginote.db-wal`, `marginote.db-shm` if present).
3. Unzip `data/backups/before-0.5.0-<date>.zip` and put its `marginote.db` in `data/`.
4. In the compose file, replace `marginote:latest` with `marginote:0.4.0`, and deploy.

Photos and covers stay where they are, and 0.4.0 finds them (a cover replaced with 0.5.0 shows blank until
you look it up again). Quotes captured with 0.5.0 are not in the old database. The code of 0.4.0 is on the
`release-0.4` branch.

## Sending from other apps

- **On a computer**: Settings has a «→ Marginote» button to drag to your bookmarks bar. Select text on any
  page and click it: Marginote opens with the passage, the link and the title filled in.
- **On the iPhone**: an Apple Shortcut, made once, puts «Marginote» in the Share menu of every app. Select
  text anywhere (Safari, Notes, Mail, Books, a PDF…), tap Share › Marginote: the app opens with the passage
  and asks where it is from. Apple Books' "Excerpt from" line is read (the book is found in your library, or
  made in one tap); from Safari, the page's link comes along; a link shared alone (YouTube, Podcasts) opens
  its form. Settings lists the six steps (four actions: Text, URL Encode, URL, Open URLs). The shortcut
  holds no password: it opens Marginote in Safari, where you are signed in.
- **From an app without Share in its menu** (Kindle): copy the passage, then Capture › Paste what you
  copied.

The shortcut opens `https://<your address>/#/capture?share=` followed by what was shared, URL-encoded.

## Disk space

- Each update leaves the previous image on disk, unused (a few hundred MB each time). Delete unused images
  in your Docker app now and then; nothing of yours is in them.
- Page photos are stored as WebP, about 200-350 KB each. Photos no quote uses are deleted after a day;
  photos in the inbox stay until you sort them.
- Covers and video pictures: WebP, at most 600 px, about 30 KB.
- The database holds text: a few MB even for thousands of quotes. The words read on each photo (kept so a
  passage can be chosen again) are stored compressed, about a tenth of their plain size.
- Database copies are zips, about a third of the database: 14 daily and 6 monthly at most.

## Backups

Every night (03:00 in the container's time zone, `TZ`) the app writes a consistent copy of the database to
`data/backups/marginote-<date>.zip`. It keeps the last 14 days and the first copy of each of the last 6
months; copies made before an upgrade are never removed. Settings shows the copies and the space used, makes
a copy on demand, and downloads everything as one zip (database, photos, covers).

These copies sit next to the database. Also back up the whole `data` folder from the NAS: snapshots of the
shared folder, and a scheduled copy to another disk, run after the nightly copy.

To restore: stop the project, move `marginote.db` (and any `marginote.db-wal`, `marginote.db-shm`) aside,
unzip a copy from `backups/` and put its `marginote.db` in `data/`, deploy again.

## Data

Everything lives in the data folder:

```
data/
  marginote.db                  sources, people, topics, quotes, comments, notes (one file)
  photos/inbox/                 pages sent to be sorted later
  photos/<Title> (<id>)/        a source's page photos, named after their page: p168 - 1a2b3c4d.webp
  covers/<id>.webp              covers and video pictures
  backups/                      database copies (zips)
  secret_key                    signs the login cookie
```

A source's folder is renamed with it, and empty folders are removed. When a page was curved, the photo kept
is the straightened one, since the word positions used to select a passage refer to it.

## Options

Set in the compose file's `environment` list; all optional.

| Variable | Default | What it does |
| --- | --- | --- |
| `OCR_LANGS` | `fra+eng` | Languages to read |
| `LOOKUPS_ENABLED` | `true` | Look up books, covers and links online |
| `STRAIGHTEN_PAGES` | `true` | Straighten curved pages before reading (`false` keeps photos exactly as taken) |
| `UNUSED_PHOTO_HOURS` | `24` | Delete photos no quote uses after this many hours |
| `BACKUPS_KEPT` | `14` | Daily database copies kept |
| `BACKUPS_MONTHLY` | `6` | Monthly copies kept as well |
| `TZ` | `UTC` | Time zone, for the nightly backup hour |

## Privacy

- Nothing leaves your server except lookups you ask for: an ISBN, or a title and author when a cover is
  searched (Open Library, Google Books, the BnF; covers also from Amazon's image server, by ISBN); and the
  link you give when its details are read (the page itself, or for a video its platform's oEmbed service:
  YouTube, Vimeo, Dailymotion, Spotify). `LOOKUPS_ENABLED=false` turns all of them off. A photo of a back
  cover is read on your server and not kept.
- Links to addresses inside your own network (the NAS, the router, your Tailscale devices) are never
  fetched.
- The app listens only inside the Tailscale container: it is not reachable from your local network
  or the internet, only from your own tailnet devices.
- Page photos are stored without any metadata (no location, camera or date). The app also shrinks photos
  on the phone before sending them.
- No access log: your searches and the pages you open are not written to the Docker logs.
- The app's pages load nothing from outside (no web fonts, scripts or trackers from other sites); a
  Content-Security-Policy header enforces it. Only `/docs` loads its viewer from a public CDN.
- The password lives only in your compose file; it is never written to the database. Changing it
  logs every device out.

## Resources

Measured on real page photos: about 65 MB of memory at rest, about 180 MB at most while reading a page
(one page at a time; Tesseract itself about 70 MB, at another moment), 3 to 5 seconds per page, one core.
The compose file caps the app at 512 MB.

## Tests

```bash
cd app
pip install -r requirements-dev.txt
pytest
```

Tesseract with the `fra` and `eng` language packs must be installed (Leptonica comes with it; the
straightening tests are skipped if it cannot be found).
