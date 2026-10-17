"""Public Commons, Sepia/PeerTube and NASA APIs; no paid services or keys."""
from __future__ import annotations

import re
import json
import hashlib
from urllib.parse import urlencode, urlsplit, quote

from pipeline.media_sources import public_media
from pipeline.media_sources.video_search.providers import clean_text, duration_seconds, ProviderBlocked
from pipeline.media_sources.video_search.plan import normalize


def api(base, **params):
    from pipeline.media_sources.image_search.sources import fetch, Blocked
    from pipeline.media_http import public_json
    from urllib.error import HTTPError
    url = base + ("?" + urlencode(params) if params else "")
    fixed = ("commons.wikimedia.org", "search.joinpeertube.org", "images-api.nasa.gov")
    try:
        data = (public_json(url, lambda: fetch(url, domains=fixed, max_bytes=8 * 1024 * 1024, raw_errors=True))
                if urlsplit(base).hostname in fixed else public_media.json_get(url))
    except HTTPError as error:
        if error.code in (401, 403, 429):
            raise ProviderBlocked(f"Provider HTTP {error.code}") from None
        raise RuntimeError(f"Provider HTTP {error.code}") from None
    except (public_media.AccessDenied, Blocked) as error:
        raise ProviderBlocked(str(error)) from None
    if not isinstance(data, dict) or data.get("error"):
        raise ValueError("Invalid public video API response")
    return data


def row(source, ident, url, title, description, creator, rights, query, duration=None, **extra):
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,160}", str(ident)):
        raise ValueError("Unsafe video identifier")
    public_media.validate_url(url)
    return dict(key=f"{source}:{ident}", source=source, id=str(ident), url=url,
                title=clean_text(title), description=clean_text(description), creator=clean_text(creator),
                license=clean_text(rights) or "unknown", queries=[query], events=[],
                duration_seconds=duration_seconds(duration), **extra)


def commons_search(query, limit):
    words = re.findall(r"[^\W_]+", query, re.UNICODE)
    data = api("https://commons.wikimedia.org/w/api.php", action="query", format="json", formatversion=2,
               generator="search", gsrsearch=" ".join('"' + w + '"' for w in words) + " filetype:video",
               gsrnamespace=6, gsrlimit=min(limit, 15), prop="videoinfo", viprop="url|size|mime|extmetadata|derivatives")
    rows = []
    for page in data.get("query", {}).get("pages", []):
        info = (page.get("videoinfo") or [{}])[0]
        if not str(info.get("mime", "")).startswith("video/"):
            continue
        ext = {k: v.get("value", "") for k, v in info.get("extmetadata", {}).items()}
        rows.append(row("commons", page["pageid"], info["descriptionurl"], page["title"],
                        ext.get("ImageDescription"), ext.get("Artist"), ext.get("LicenseShortName"), query,
                        info.get("duration"), file_title=page["title"]))
    return rows


def peertube_search(query, limit):
    # Sepia broad queries OR words; quoting prevents unrelated partial-name hits.
    phrase = " ".join(re.findall(r"[^\W_]+", query, re.UNICODE))
    data = api("https://search.joinpeertube.org/api/v1/search/videos", search='"' + phrase + '"',
               count=min(limit, 15), nsfw="false", isLive="false")
    items = data.get("data", [])
    if not items:
        # Names/events can be split by connecting words in the catalogue text.
        # Sepia broadens with OR; enforce ALL query words ourselves before the
        # semantic judge. A bounded fallback must not admit partial-name hits.
        data = api("https://search.joinpeertube.org/api/v1/search/videos", search=phrase,
                   count=30, nsfw="false", isLive="false")
        required = set(normalize(phrase).split())
        items = [v for v in data.get("data", []) if required and required.issubset(set(normalize(
            str(v.get("name") or "") + " " + str(v.get("description") or v.get("truncatedDescription") or "")
        ).split()))][:min(limit, 15)]
    rows = []
    for item in items:
        if item.get("privacy", {}).get("id") != 1 or item.get("isLive") or item.get("nsfw"):
            continue
        ident = item.get("uuid", "")
        if not re.fullmatch(r"[a-f0-9-]{36}", ident):
            continue
        rows.append(row("peertube", ident, item["url"], item.get("name"),
                        item.get("description") or item.get("truncatedDescription"),
                        item.get("channel", {}).get("displayName"), item.get("licence", {}).get("label"),
                        query, item.get("duration")))
    return rows


NASA_EDITORIAL_LICENSE = "NASA media usage guidelines (editorial use)"
NASA_POLICY_URL = "https://www.nasa.gov/nasa-brand-center/images-and-media/"


def nasa_rights(metadata):
    # NASA permits factual editorial use; third-party media are explicitly excluded.
    # Require a government NASA centre and retain the complete source record as evidence.
    if metadata.get('center') not in {'HQ', 'JSC', 'KSC', 'GSFC', 'MSFC', 'ARC', 'GRC', 'LARC', 'AFRC', 'SSC'}:
        return 'unknown'
    text = json.dumps(metadata, ensure_ascii=False)
    if re.search(r'©|copyright|courtesy|all rights|third.party|Getty|Reuters|Associated Press|ESA/|SpaceX|Caltech|JPL', text, re.I):
        return 'unknown'
    creator = str(metadata.get('secondary_creator') or metadata.get('photographer') or '')
    if creator and not creator.upper().startswith('NASA'):
        return 'unknown'
    return NASA_EDITORIAL_LICENSE


def peertube_rights(item):
    host = public_media.validate_url(item['url']).hostname
    detail = api(f"https://{host}/api/v1/videos/{item['id']}")
    if detail.get('uuid') != item['id'] or detail.get('privacy', {}).get('id') != 1 or detail.get('downloadEnabled') is not True:
        raise ValueError('PeerTube item is not the selected public downloadable recording')
    return (detail.get('licence') or detail.get('license') or {}).get('label', 'unknown')


def nasa_search(query, limit):
    data = api("https://images-api.nasa.gov/search", q=query, media_type="video", page_size=min(limit, 15))
    rows = []
    for item in data.get("collection", {}).get("items", []):
        d = (item.get("data") or [{}])[0]
        ident = d.get("nasa_id", "")
        if not isinstance(ident, str) or not ident or len(ident) > 512 or any(ord(c) < 32 for c in ident):
            continue
        # NASA catalogue IDs legitimately contain spaces. Keep them out of local paths;
        # the raw ID is encoded only into the fixed official API URL.
        local_id = ident if re.fullmatch(r"[A-Za-z0-9_.-]{1,160}", ident) else 'nasa-' + hashlib.sha256(ident.encode()).hexdigest()[:32]
        rows.append(row("nasa", local_id, "https://images.nasa.gov/details/" + quote(ident, safe=''), d.get("title"),
                        d.get("description"), d.get("center"), nasa_rights(d), query,
                        nasa_id=ident,
                        rights_evidence={"policy_url": NASA_POLICY_URL, "catalogue": d}))
    return rows


def direct_media(item):
    """Re-check authoritative metadata immediately before downloading."""
    source = item["source"]
    metadata = {k: item[k] for k in ("id", "title", "creator", "license")}
    if source == "peertube":
        p = public_media.validate_url(item["url"])
        d = api(f"https://{p.hostname}/api/v1/videos/{item['id']}")
        if d.get("uuid") != item["id"] or d.get("privacy", {}).get("id") != 1 or d.get("isLive"):
            raise ValueError("PeerTube video is not the selected public recording")
        if d.get("downloadEnabled") is not True:
            raise ValueError("PeerTube owner has not enabled downloads")
        # Progressive or self-contained fragmented MP4 with explicit audio.
        # These are whole files, not playlists: never follow HLS manifests/P2P.
        available = list(d.get("files", []))
        available += [f for p in d.get("streamingPlaylists", []) for f in p.get("files", [])
                      if f.get("hasAudio") is True]
        files = [f for f in available if str(f.get("fileUrl", "")).split("?")[0].endswith(".mp4")
                 and 0 < int(f.get("size") or 0) <= 256 * 1024 * 1024
                 and f.get("hasAudio") is not False]
        if not files:
            raise ValueError("No public self-contained MP4 under 256 MiB; HLS/P2P is not downloaded")
        chosen = min(files, key=lambda f: (f.get("resolution", {}).get("id", 9999) > 360, int(f["size"])))
        metadata["license"] = (d.get("licence") or d.get("license") or {}).get("label", "unknown")
        metadata.update(source_duration_seconds=d.get("duration"), source_size_bytes=chosen["size"],
                        source_has_audio=chosen.get("hasAudio"))
        return chosen["fileUrl"], metadata, None
    if source == "commons":
        d = api("https://commons.wikimedia.org/w/api.php", action="query", format="json", formatversion=2,
                pageids=item["id"], prop="videoinfo", viprop="url|size|mime|derivatives")
        info = d["query"]["pages"][0]["videoinfo"][0]
        files = [f for f in info.get("derivatives", []) if str(f.get("type", "")).startswith("video/")]
        chosen = min(files, key=lambda f: (int(f.get("height") or 9999) > 360, -int(f.get("height") or 0))) if files else {"src": info["url"]}
        metadata["source_duration_seconds"] = info.get("duration")
        return chosen["src"], metadata, ("upload.wikimedia.org",)
    if source == "nasa":
        d = api("https://images-api.nasa.gov/asset/" + quote(item.get("nasa_id") or item["id"], safe=''))
        files = [x["href"] for x in d.get("collection", {}).get("items", [])
                 if str(x.get("href", "")).lower().endswith(".mp4")]
        if not files:
            raise ValueError("NASA record has no MP4")
        files.sort(key=lambda u: ("~small.mp4" not in u, "~medium.mp4" not in u, u))
        url = files[0]
        # NASA's asset manifest still emits http URLs for its HTTPS CDN.
        # Upgrade only the known official host, never an arbitrary manifest URL.
        if urlsplit(url).scheme == "http" and urlsplit(url).hostname == "images-assets.nasa.gov":
            url = "https:" + url[5:]
        public_media.validate_url(url, ("images-assets.nasa.gov",))
        return url, metadata, ("images-assets.nasa.gov",)
    raise ValueError("Unknown direct video provider")


PROVIDERS = {"commons": commons_search, "peertube": peertube_search, "nasa": nasa_search}
