# Marginote

Self-hosted quotes and notes on what you read, watch, listen to and study: books, ebooks, articles, videos,
podcasts, classes, talks. Photograph a page or share a link, keep the passage or write a note, say whom and
what it is about, and find it again by source, by person or by topic. Your notes and photos stay on your own server;
the app is reachable only through your private Tailscale network.

## How it is organised

- **Quotes**: passages, each with your comment if you want one. Taken from a source, or words someone said
  with no source to point to (a talk heard, a radio interview): then just who said it, and where or when.
- **Notes**: your own writing. A note can be on sources (a book, a video, a class: with the page or the
  session), on people and on topics, all optional; it shows on each of their pages.
- **Sources**: anything you quote from or write about. A book (page photos, ISBN, cover), an ebook
  (screenshots), an article (its link opens the page at the passage you kept), a video or podcast (a link,
  mostly your notes on it), a class (its teacher and school; notes for each session, and quotes), a talk,
  or anything else.
- **People**: who made a source (author, translator, editor, speaker, teacher) and whom it is about. Each
  person has a page: your notes on them, their works, what they said, their words quoted elsewhere, and what
  is about them, each work with its quotes and your notes on it. A passage by Lordon about Spinoza is stored
  once and shows on both pages.
- **Topics**: each with a page: your notes, the people who appear in it, topics often found with it, its
  quotes grouped by person, source or date.

Every section and group of a page folds away with its − button (+ shows it again); each device remembers
what you folded.

A quote takes its source's people and topics; untick one when a passage is not about it. Its words are its
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
  `ghcr.io/<owner>/marginote`, tagged `latest` and with its version (`0.7.1`)

## Install

1. In the Tailscale admin console, turn on MagicDNS and HTTPS certificates, and create an auth key.
2. Create two folders on your server: `.../marginote/data` and `.../marginote/tailscale`.
3. Paste `docker-compose.yml` into your Docker app, replace the values marked `CHANGE-ME` (and the
   folder paths if yours differ), and deploy.
4. Open `https://marginote.<your-tailnet>.ts.net` from a device on your tailnet and log in: name `admin`
   (or leave the name empty), password `MARGINOTE_PASSWORD`. On iPhone, Safari's Share → Add to Home
   Screen opens it like an app.

`/docs` lists every API call.

## Accounts and languages

You are the owner: your password is `MARGINOTE_PASSWORD`, and your library is `data/users/owner/`.
Your name starts as `admin`; change it in Settings.

Settings › People with access adds someone: a name, a password (8 characters at least) and a language.
Each person gets a library of their own, in `data/users/<id>/` (database, photos, covers, backups), and
nothing in the app reads one library from another: not the lists, not the search, not the photos, not the
backups or the download. Not even the owner can see another person's library in the app (as owner of the
NAS, you can still open their files there). Each person changes their own password in Settings; the owner
can set a new one for someone who forgot theirs. Removing someone stops their logins and sets their
library aside in `data/users/removed/`.

The app is still reachable only through your tailnet. To let someone in without giving them your whole
network, share only the `marginote` machine with them: in the Tailscale admin console, Machines › the
`marginote` row › ⋯ › Share. They accept with their own Tailscale account and reach the app at the same
address, and nothing else of yours.

Each person picks French or English in Settings; the login page follows the browser, and its link at the
bottom switches. The French screens (`static/app.fr.js`) are made from the English ones (`static/app.js`)
by `tools/translate_fr.py`: after changing `app.js`, run it, and add the French of any new text to its
table (a test fails until the French file is up to date).

## Update

Stop the project and deploy it again: the compose file sets `pull_policy: always`, so the newest image is
downloaded. The data folder is kept.

When an update changes the shape of the database, the app first writes a copy of the database as it was to
the library's `backups/before-<version>-<date>.zip`. Nothing is lost in the change: ids, quotes, notes, pages,
photos and covers all stay.

- 0.5.0: books become sources, authors become people, tags become topics.
- 0.6.0: comments become notes on their source, about the same people and topics (with their page, and
  your note on the comment added below its text); a note that referred to a comment now refers to its
  source. Quotes can have no source, notes can be on sources, and classes are a new kind of source.
- 0.7.1: accounts. On its first start, your library (until then the top of the data folder:
  `marginote.db`, `photos/`, `covers/`, `backups/`) moves into `data/users/owner/`, after a copy of the
  database to `before-0.7.1-<date>.zip`. Each item is renamed on the same disk, so it is instant; nothing is
  overwritten (if both places hold files, the app stops and says so). The database itself is unchanged,
  and devices already logged in stay logged in.

Do not use a one-click "update" or "recreate" button on the `marginote` container (UGOS, Portainer…): it
shares the Tailscale container's network, and those buttons cannot rebuild such a container (Docker
answers "conflicting options: hostname and the network mode"), which leaves it deleted.

### Going back to an earlier version

| Back to | Copy to restore | Image |
| --- | --- | --- |
| 0.6.1 | none: the database is the same | `marginote:0.6.1` |
| 0.5.1 | `before-0.6.0-<date>.zip` | `marginote:0.5.1` |
| 0.4.0 | `before-0.5.0-<date>.zip` | `marginote:0.4.0` |

1. Stop the project.
2. Versions before 0.7.1 keep your library at the top of `data/`: move `marginote.db` (with
   `marginote.db-wal` and `marginote.db-shm` if present), `photos/`, `covers/` and `backups/` from
   `data/users/owner/` up into `data/`. The other people's libraries stay in `data/users/`, unused by
   those versions.
3. For 0.5.1 or 0.4.0: move `data/marginote.db` aside, unzip the copy from `data/backups/` and put its
   `marginote.db` in `data/`.
4. In the compose file, replace `marginote:latest` with the image above, and deploy.

Photos and covers stay where they are, and the older version finds them (with 0.4.0, a cover replaced
since shows blank until you look it up again). What you captured since the upgrade is not in the old
database. The code of each version is on its branch: `release-0.4`, `release-0.5`, `release-0.6`.

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

Every night (03:00 in the container's time zone, `TZ`) the app writes a consistent copy of each library's
database to its `backups/` folder (`data/users/owner/backups/marginote-<date>.zip` for yours). It keeps the
last 14 days and the first copy of each of the last 6 months; copies made before an upgrade are never
removed. Settings shows the copies and the space used, makes
a copy on demand, and downloads everything as one zip (database, photos, covers).

These copies sit next to the database. Also back up the whole `data` folder from the NAS: snapshots of the
shared folder, and a scheduled copy to another disk, run after the nightly copy.

To restore one library: stop the project; in its folder (`data/users/<id>/`), move `marginote.db` (and any
`marginote.db-wal`, `marginote.db-shm`) aside, unzip a copy from its `backups/` and put the `marginote.db`
in its place; deploy again. The other libraries are not touched. A copy of the whole `data` folder holds
every library and the accounts; when restoring from a file copy (rather than a snapshot), use the zips in
`backups/`, since a copy made while the app writes may catch the database half-written.

## Data

Everything lives in the data folder:

```
data/
  accounts.json                 the accounts: names, languages, scrambled passwords (scrypt)
  secret_key                    signs the login cookies
  users/
    owner/                      your library
      marginote.db              sources, people, topics, quotes, notes (one file)
      photos/inbox/             pages sent to be sorted later
      photos/<Title> (<id>)/    a source's page photos, named after their page: p168 - 1a2b3c4d.webp
      covers/<id>.webp          covers and video pictures
      backups/                  database copies (zips)
    <id>/                       another person's library, laid out the same way
    removed/                    libraries of removed accounts, set aside
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
- Your password lives only in your compose file; it is never written to the database. Changing it
  logs every device out. The other accounts' passwords are kept scrambled (scrypt) in
  `data/accounts.json`, never as typed; a new password logs that person out everywhere.

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
