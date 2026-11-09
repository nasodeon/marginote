# Marginote

Self-hosted quotes and notes on what you read, watch, listen to and study: books, ebooks, articles, scientific
papers, videos, podcasts, classes, talks. Photograph a page, import a PDF, share a link or send a passage
from your PDF reader; keep the passage or write a note, say whom and what it is about, and find it again
by source, by person or by topic. Your notes and photos stay on your own server;
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

**Adding** (Ajouter) starts from one place for anything: paste a passage, a link, a DOI, an arXiv number or an
ISBN; take a photo; choose or drop photos, screenshots and PDFs. Below it: what waits in À trier, and what you
are reading, with where you were. A passage chosen on a photo or a PDF page is kept at once with its page
(« Garder ce passage »); the next screen offers the rest (comment, who it is about, topics, whose words),
saved as you type, then « Passage suivant » goes back to the same page, which marks in its margin what was
already kept.

**Scientific papers**: a DOI or an arXiv number (pasted, or printed on a PDF's first page, or in a journal
page's citation tags) brings the title, every author, the journal, volume, issue, pages and date, from
Crossref, DataCite or arXiv. Every author is kept; lists show « Marceau et al. » beyond three.

**PDFs** are imported once and kept with their source. Each page is read on the server (its text with the
place of every word; a scanned page with Tesseract, like a photo) and then works like a page photo: choose
a passage on it, see a quote highlighted on its page, open the PDF itself at that page. Page numbers are
the ones printed (or counted from the article's first page in its journal).

**Reading in your own PDF reader**: copy a passage and send it (Ctrl+Alt+M on Windows, Partager on a phone):
Marginote finds it in the PDFs it keeps, starting with the one you are reading, and keeps it with its source
and page, in the PDF's own clean words. It is compared letter by letter, so a line broken in the middle of
a word, a ligature, a footnote number glued to a word, a footnote or running head caught in the selection,
or a passage running onto the next page make no difference. A passage found nowhere, or in two places,
waits in À trier with its best guess, to confirm in one tap.

**À trier** (the inbox) is one list, by source: PDFs to recognise, page photos sent to be sorted later,
passages and links sent from elsewhere.

**Export** (Settings › Export): your quotes and notes as a PDF or a Word file, organised by author, by topic
or by source, for the ones you tick or all of them. Page 1 has a table of contents you can tap. In each
chapter, sources come by author then year, quotes in page order, each with its reference (« Auteur, *Titre*,
p. 42 »), then your notes; a bibliography of every source cited closes the file. The Word file uses named
styles (Citation, Référence, Note…) so one change in Word restyles them all. The file is made on your NAS
and kept in memory for 15 minutes, never on disk; on an iPhone it opens in Safari, to share or save.

A quote takes its source's people and topics; untick one when a passage is not about it. Its words are its
source author's unless you name someone else (a quote within a quote).

## What is here

- `app/` — the app: FastAPI, SQLite with full-text search, Tesseract text recognition (French and English)
  with shadow removal and straightening of pages that curve toward the spine (Leptonica), page-number
  detection, book details from Open Library, Google Books and the BnF catalogue, the ISBN read from a photo
  of the back cover, page details read from a link, articles from Crossref, DataCite and arXiv, PDFs read
  with PDFium (`pdfs.py`, `documents.py`), copied passages found in them (`matching.py`), and an inbox of
  what waits to be sorted
- `app/marginote/static/marginote-windows.ps1` — the Windows installer that Settings fills in with your
  address and a sending key
- `app/marginote/static/` — the screens, for phone and computer, set like a LaTeX document. Plain
  JavaScript; the fonts (Computer Modern Unicode, SIL Open Font License, Latin subset) are served by the app
- `docker-compose.yml` — what you paste into your Docker app: the app plus a Tailscale container that
  gives it a private HTTPS address
- `.github/workflows/image.yml` — on every push, runs the tests and checks the image starts; on `main`
  only, publishes it to `ghcr.io/<owner>/marginote`, tagged `latest` and with its version (`0.9.0`)

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
- 0.7.2: Android's Share menu, and the French tab names fit narrow phones. Nothing changes in the data.
- 0.8.0: export to PDF and Word. Nothing changes in the data; the image is about 90 MB bigger (the
  typesetting program that makes the PDFs).
- 0.9.0: PDFs, scientific papers, sending keys, one Ajouter screen. The database gains the article fields
  of a source (DOI, arXiv, journal, volume, issue, pages), PDFs and their pages, passages waiting to be
  sorted, and what you are reading; a copy is made first, to `before-0.9.0-<date>.zip`. Nothing already
  there changes. A `pdfs/` folder appears in each library.

Do not use a one-click "update" or "recreate" button on the `marginote` container (UGOS, Portainer…): it
shares the Tailscale container's network, and those buttons cannot rebuild such a container (Docker
answers "conflicting options: hostname and the network mode"), which leaves it deleted.

### Going back to an earlier version

| Back to | Copy to restore | Image |
| --- | --- | --- |
| 0.8.0 | `before-0.9.0-<date>.zip` | `marginote:0.8.0` |
| 0.7.2 | `before-0.9.0-<date>.zip` | `marginote:0.7.2` |
| 0.7.1 | none: nothing changed in the data | `marginote:0.7.1` |
| 0.6.1 | none: the database is the same | `marginote:0.6.1` |
| 0.5.1 | `before-0.6.0-<date>.zip` | `marginote:0.5.1` |
| 0.4.0 | `before-0.5.0-<date>.zip` | `marginote:0.4.0` |

1. Stop the project.
2. Versions before 0.7.1 keep your library at the top of `data/`: move `marginote.db` (with
   `marginote.db-wal` and `marginote.db-shm` if present), `photos/`, `covers/` and `backups/` from
   `data/users/owner/` up into `data/`. The other people's libraries stay in `data/users/`, unused by
   those versions.
3. For 0.8.0 and 0.7.2: in `data/users/owner/` (and each person's folder), move `marginote.db` aside, unzip
   `before-0.9.0-<date>.zip` from its `backups/` and put its `marginote.db` in its place. Their `pdfs/`
   folders are not used by those versions; keep them for when you upgrade again.
   For 0.5.1 or 0.4.0: move `data/marginote.db` aside, unzip the copy from `data/backups/` and put its
   `marginote.db` in `data/`.
4. In the compose file, replace `marginote:latest` with the image above, and deploy.

Photos and covers stay where they are, and the older version finds them (with 0.4.0, a cover replaced
since shows blank until you look it up again). What you captured since the upgrade is not in the old
database. The code of each version is on its branch: `release-0.4`, `release-0.5`, `release-0.6`, `release-0.7`,
`release-0.8`.

## Sending from other apps

- **On a computer**: Settings has a «→ Marginote» button to drag to your bookmarks bar. Select text on any
  page and click it: Marginote opens with the passage, the link and the title filled in.
- **On the iPhone**: an Apple Shortcut, made once, puts «Marginote» in the Share menu of every app. Select
  text anywhere (Safari, Notes, Mail, Books, a PDF…), tap Share › Marginote: the app opens with the passage
  and asks where it is from. Apple Books' "Excerpt from" line is read (the book is found in your library, or
  made in one tap); from Safari, the page's link comes along; a link shared alone (YouTube, Podcasts) opens
  its form. Settings lists the six steps (four actions: Text, URL Encode, URL, Open URLs). The shortcut
  holds no password: it opens Marginote in Safari, where you are signed in.
- **On Android** (Samsung and others): nothing to make. Install the app from Chrome (⋮ › Install app) and
  Android lists «Marginote» in its Share menu: select text in any app, tap Share › Marginote, and the app
  opens with the passage, as on the iPhone. A shared page brings its link and title. Install from Chrome,
  not Samsung Internet; an icon with a small Chrome logo is a plain shortcut, which is not in the Share menu.
- **From an app without Share in its menu** (Kindle): copy the passage, then Ajouter › Coller.
- **Without opening the app, with a sending key**: Settings › Sending keys makes a key for one device. A key
  can only add to your library (a passage, a PDF, a photo), never read it; only its SHA-256 is kept, in
  `data/accounts.json`, and deleting it stops it at once.
  - **Windows**: Settings fills in an installer with your address and the key; run it once in PowerShell
    (the exact line is shown), no administrator rights needed. Then in any app (a PDF reader, a browser,
    Word), copy a passage and press **Ctrl+Alt+M**: a notification says where it was kept (« Gardé · *La
    mémoire trie*, p. 45 ») or that it waits in À trier. **Ctrl+Alt+N** asks for a comment first.
    Right-click a PDF or an image › Envoyer vers › Marginote sends the file. The installer writes a small
    script and the key to `%LOCALAPPDATA%\Marginote`, two shortcuts to the Start menu and one to Envoyer
    vers, then deletes itself.
  - **iPhone**: a second shortcut, « Marginote · envoyer », sends what you select in Fichiers or Livres to
    `/api/send/passage` and shows the answer as a notification, without leaving the PDF. Settings lists
    its steps, with the key filled in.

The shortcut opens `https://<your address>/#/capture?share=` followed by what was shared, URL-encoded. On
Android the manifest's `share_target` sends it to `/share`, which hands it on to the same address; nothing
is kept or logged on the way.

## Disk space

- Each update leaves the previous image on disk, unused (a few hundred MB each time). Delete unused images
  in your Docker app now and then; nothing of yours is in them.
- Page photos are stored as WebP, about 200-350 KB each. Photos no quote uses are deleted after a day;
  photos in the inbox stay until you sort them.
- PDFs are kept as sent. Their pages are drawn as pictures only when looked at, never stored; the words
  of each page (for choosing a passage and finding one sent from a reader) take about 20 KB of the
  database per page.
- Covers and video pictures: WebP, at most 600 px, about 30 KB.
- The database holds text: a few MB even for thousands of quotes. The words read on each photo (kept so a
  passage can be chosen again) are stored compressed, about a tenth of their plain size.
- Database copies are zips, about a third of the database: 14 daily and 6 monthly at most.

## Backups

Every night (03:00 in the container's time zone, `TZ`) the app writes a consistent copy of each library's
database to its `backups/` folder (`data/users/owner/backups/marginote-<date>.zip` for yours). It keeps the
last 14 days and the first copy of each of the last 6 months; copies made before an upgrade are never
removed. Settings shows the copies and the space used, makes
a copy on demand, and downloads everything as one zip (database, photos, covers, PDFs).

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
  accounts.json                 the accounts: names, languages, scrambled passwords (scrypt), sending keys (SHA-256)
  secret_key                    signs the login cookies
  users/
    owner/                      your library
      marginote.db              sources, people, topics, quotes, notes (one file)
      photos/inbox/             pages sent to be sorted later
      photos/<Title> (<id>)/    a source's page photos, named after their page: p168 - 1a2b3c4d.webp
      covers/<id>.webp          covers and video pictures
      pdfs/inbox/               PDFs not yet given their source
      pdfs/<Title> (<id>)/      a source's PDFs, under the name they were sent with
      backups/                  database copies (zips)
    <id>/                       another person's library, laid out the same way
    removed/                    libraries of removed accounts, set aside
```

A source's folders are renamed with it, and empty folders are removed. Deleting a source deletes its PDFs;
quotes taken from a deleted PDF keep their text and page. When a page was curved, the photo kept
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
  YouTube, Vimeo, Dailymotion, Spotify); a DOI or an arXiv number (Crossref, then DataCite; arXiv), never
  the PDF or a passage. `LOOKUPS_ENABLED=false` turns all of them off. A photo of a back
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
- A PDF opens in the browser from a link signed for your library and valid for a few hours (so the iPhone
  app can hand it to Safari, whose login is separate); the link opens that PDF only.
- Your password lives only in your compose file; it is never written to the database. Changing it
  logs every device out. The other accounts' passwords are kept scrambled (scrypt) in
  `data/accounts.json`, never as typed; a new password logs that person out everywhere.

## Resources

Measured on real page photos: about 65 MB of memory at rest, about 180 MB at most while reading a page
(one page at a time; Tesseract itself about 70 MB, at another moment), 3 to 5 seconds per page, one core.
An export is made one at a time, never while a page is being read: a PDF of 3,000 quotes takes about
2 seconds and 280 MB more memory, a Word file about 3 seconds. A PDF with text is read in the background at
about 70 ms a page (a scanned page, like a photo: 3 to 5 seconds) with about 70 MB more memory; drawing a
page to look at it takes about 0.2 s. Finding a passage sent from a reader takes 10 to 70 ms. The compose file caps the app at 512 MB.

## Tests

```bash
cd app
pip install -r requirements-dev.txt
pytest
```

Tesseract with the `fra` and `eng` language packs must be installed (Leptonica comes with it; the
straightening tests are skipped if it cannot be found).
