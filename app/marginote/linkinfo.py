"""Details of a web page or a video from its link: title, site or channel, author, date, picture.

Read from what the page says about itself for sharing (OpenGraph tags, schema.org data), or for videos from
the platform's oEmbed answer. Only the link you give leaves the server. Addresses inside your own network
(the NAS, the router, your Tailscale devices) are refused, so a link can never make the server look at them.
"""

import ipaddress
import json
import logging
import re
import socket
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

log = logging.getLogger("marginote")

MAX_PAGE = 1_500_000            # read at most this much of a page
VIDEO_HOSTS = ("youtube.com", "youtu.be", "vimeo.com", "dailymotion.com", "dai.ly")
PODCAST_HOSTS = ("podcasts.apple.com", "open.spotify.com", "deezer.com", "podcasts.google.com", "radiofrance.fr/podcasts")
OEMBED = {
    "youtube.com": "https://www.youtube.com/oembed",
    "youtu.be": "https://www.youtube.com/oembed",
    "vimeo.com": "https://vimeo.com/api/oembed.json",
    "dailymotion.com": "https://www.dailymotion.com/services/oembed",
    "dai.ly": "https://www.dailymotion.com/services/oembed",
    "open.spotify.com": "https://open.spotify.com/oembed",
}
TRACKING = re.compile(r"^(utm_.*|fbclid|gclid|mc_[a-z]+|igshid|si|feature|pp|ref|ref_src|xtor|at_medium|at_campaign)$", re.I)


class LinkError(Exception):
    pass


def clean_url(url: str) -> str:
    """The link without its tracking parameters and #fragment; youtu.be links in their long form."""
    url = url.strip()
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if not host or "." not in host:
        raise LinkError("This does not look like a web address")
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not TRACKING.match(k)]
    if host in ("youtu.be", "www.youtu.be") and parts.path.strip("/"):
        return f"https://www.youtube.com/watch?v={parts.path.strip('/')}"
    if host.endswith("youtube.com"):
        query = [(k, v) for k, v in query if k in ("v", "list")]
        host = "www.youtube.com" if host in ("youtube.com", "m.youtube.com") else host
    netloc = host + (f":{parts.port}" if parts.port else "")
    return urlunsplit((parts.scheme.lower(), netloc, parts.path or "/", urlencode(query), ""))


def _host_matches(host: str, names: tuple[str, ...]) -> str | None:
    for name in names:
        domain = name.split("/")[0]
        if host == domain or host.endswith("." + domain):
            return name
    return None


def check_public(url: str) -> None:
    """Refuse addresses that are not on the public internet."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise LinkError("Only http and https links can be read")
    try:
        infos = socket.getaddrinfo(parts.hostname, parts.port or (443 if parts.scheme == "https" else 80),
                                   proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise LinkError("This site could not be found") from None
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if not ip.is_global or ip in ipaddress.ip_network("100.64.0.0/10"):
            raise LinkError("Addresses inside your own network are not read")


def _get(client, url: str, *, accept: str, limit: int = MAX_PAGE) -> tuple[str, bytes, str]:
    """GET with redirects followed one at a time, each one checked. Returns (final url, body, content type)."""
    for _ in range(6):
        check_public(url)
        with client.stream("GET", url, headers={"Accept": accept}) as r:
            if r.is_redirect and "location" in r.headers:
                url = urljoin(url, r.headers["location"])
                continue
            if r.status_code != 200:
                raise LinkError(f"The site answered {r.status_code}")
            chunks, size = [], 0
            for chunk in r.iter_bytes():
                chunks.append(chunk)
                size += len(chunk)
                if size >= limit:
                    break
            return url, b"".join(chunks), r.headers.get("content-type", "")
    raise LinkError("Too many redirections")


class _Head(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.title = ""
        self.lang = ""
        self.ld: list[str] = []
        self._in_title = False
        self._in_ld = False
        self._buf: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "html" and a.get("lang"):
            self.lang = a["lang"]
        elif tag == "meta":
            key = (a.get("property") or a.get("name") or a.get("itemprop") or "").lower()
            if key and a.get("content") and key not in self.meta:
                self.meta[key] = a["content"].strip()
        elif tag == "title" and not self.title:
            self._in_title, self._buf = True, []
        elif tag == "script" and "ld+json" in a.get("type", ""):
            self._in_ld, self._buf = True, []

    def handle_endtag(self, tag):
        if tag == "title" and self._in_title:
            self.title, self._in_title = "".join(self._buf).strip(), False
        elif tag == "script" and self._in_ld:
            self.ld.append("".join(self._buf))
            self._in_ld = False

    def handle_data(self, data):
        if self._in_title or self._in_ld:
            self._buf.append(data)


def _ld_items(blobs: list[str]) -> list[dict]:
    items: list[dict] = []

    def walk(node):
        if isinstance(node, list):
            for n in node:
                walk(n)
        elif isinstance(node, dict):
            if "@graph" in node:
                walk(node["@graph"])
            items.append(node)

    for blob in blobs:
        try:
            walk(json.loads(blob))
        except ValueError:
            continue
    return items


def _names(value) -> list[str]:
    """Author names from schema.org data or a meta tag (never a link to a profile)."""
    out: list[str] = []
    for v in value if isinstance(value, list) else [value]:
        name = v.get("name") if isinstance(v, dict) else v
        if isinstance(name, str):
            for part in re.split(r"\s*(?:,|;| et | and | & )\s*", name.strip()):
                if part and not re.match(r"^https?://", part) and len(part) < 80 and part not in out:
                    out.append(part)
    return out


def _date(value: str | None) -> str | None:
    m = re.match(r"(\d{4}-\d{2}-\d{2})", value or "")
    return m.group(1) if m else None


def _strip_site(title: str, site: str | None) -> str:
    """'Le titre - Le Site' -> 'Le titre' when the site's name is repeated in the page title."""
    if site:
        for sep in (" | ", " - ", " — ", " – ", " · ", " : "):
            if title.endswith(sep + site):
                return title[: -len(sep + site)].strip()
    return title


def parse_page(url: str, html: str) -> dict:
    head = _Head()
    try:
        head.feed(html)
    except Exception:  # broken markup: keep what was read so far
        pass
    m = head.meta
    ld = _ld_items(head.ld)
    article = next((i for i in ld if str(i.get("@type", "")).lower() in
                    ("article", "newsarticle", "blogposting", "reportagenewsarticle", "videoobject", "podcastepisode")), {})
    publisher = article.get("publisher")
    site = m.get("og:site_name") or (publisher.get("name") if isinstance(publisher, dict) else None)
    title = m.get("og:title") or article.get("headline") or m.get("twitter:title") or head.title
    people = _names(article.get("author")) or _names(m.get("author")) or _names(m.get("article:author"))
    image = m.get("og:image") or m.get("og:image:url") or m.get("twitter:image")
    if isinstance(article.get("image"), (str, dict)) and not image:
        image = article["image"] if isinstance(article["image"], str) else article["image"].get("url")
    og_type = m.get("og:type", "").lower()
    return {
        "title": _strip_site(re.sub(r"\s+", " ", title or "").strip(), site) or None,
        "site": site or None,
        "people": people,
        "date": _date(m.get("article:published_time") or article.get("datePublished") or m.get("date")
                      or m.get("og:published_time") or m.get("datepublished")),
        "language": (head.lang or m.get("og:locale") or "").split("-")[0].split("_")[0].lower() or None,
        "image_url": urljoin(url, image) if image else None,
        "og_type": og_type,
    }


def _client():
    import httpx  # loaded only when a link is read
    return httpx.Client(timeout=httpx.Timeout(10.0, connect=5.0), follow_redirects=False, headers={
        "User-Agent": "Mozilla/5.0 (compatible; Marginote/0.5; self-hosted reading notes)",
        "Accept-Language": "fr,en;q=0.8",
    })


def read(url: str, client_factory=None) -> dict:
    """Everything known about a link. Raises LinkError with a message for the person."""
    import httpx
    try:
        return _read(url, client_factory or _client)
    except httpx.HTTPError as err:
        raise LinkError(f"The site could not be reached ({type(err).__name__})") from None


def _read(url: str, client_factory) -> dict:
    url = clean_url(url)
    host = (urlsplit(url).hostname or "").lower()
    video = _host_matches(host, VIDEO_HOSTS)
    podcast = _host_matches(host, PODCAST_HOSTS)
    oembed = _host_matches(host, tuple(OEMBED))
    info: dict = {"url": url, "kind": "video" if video else "podcast" if podcast else "article",
                  "title": None, "site": None, "people": [], "date": None, "language": None, "image_url": None}
    with client_factory() as client:
        if oembed:
            try:
                endpoint = f"{OEMBED[oembed]}?{urlencode({'url': url, 'format': 'json'})}"
                _, body, _ = _get(client, endpoint, accept="application/json", limit=200_000)
                data = json.loads(body)
                info.update(title=data.get("title"), site=data.get("author_name") or data.get("provider_name"),
                            image_url=data.get("thumbnail_url"))
                if oembed in ("youtube.com", "youtu.be", "vimeo.com", "dailymotion.com", "dai.ly"):
                    info["site"] = data.get("author_name")        # the channel
                    info["platform"] = data.get("provider_name")
                return info
            except (LinkError, ValueError) as err:
                log.info("Video details not found (%s); reading the page instead", err)
        final, body, ctype = _get(client, url, accept="text/html,application/xhtml+xml")
        if "html" not in ctype and not body.lstrip()[:200].lower().startswith((b"<!doctype", b"<html")):
            raise LinkError("This link is not a web page")
        charset = re.search(r"charset=([\w-]+)", ctype)
        text = body.decode(charset.group(1) if charset else "utf-8", errors="replace")
        page = parse_page(final, text)
        info.update({k: v for k, v in page.items() if k != "og_type" and v})
        if page["og_type"].startswith("video") and info["kind"] == "article":
            info["kind"] = "video"
        if not info["site"]:
            info["site"] = re.sub(r"^www\.", "", urlsplit(final).hostname or "")
    return info
