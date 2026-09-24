"""Bounded public discovery; results never provide executable commands or arbitrary hosts."""
from __future__ import annotations

import html
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

from experiments.video_search.plan import matches, normalize


class ProviderBlocked(RuntimeError):
    pass


def safe_error(error) -> str:
    text = str(error)
    for name in ("OPENAI_API_KEY", "YOUTUBE_API_KEY"):
        value = os.environ.get(name)
        if value:
            text = text.replace(value, "[redacted]")
    return re.sub(r"https?://\S+", "[remote-url]", text)[-800:]


def blocked(text: str) -> bool:
    return any(term in text.casefold() for term in (
        "not a bot", "confirm you're", "confirm you’re", "http error 429",
        "too many requests", "quotaexceeded", "dailylimitexceeded"))


def request_json(url: str, *, body=None, headers=None, timeout=40) -> dict:
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(url, data=data, headers={
        "User-Agent": "AI-News-Daily-video-experiment/1.0",
        "Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(8 * 1024 * 1024 + 1)
        if len(raw) > 8 * 1024 * 1024:
            raise RuntimeError("Oversized API response")
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise ValueError("API returned a non-object")
        return result
    except urllib.error.HTTPError as error:
        # Never persist response bodies or signed/credential-bearing URLs.
        detail = error.read(4096).decode(errors="replace")
        if error.code in (401, 403, 429) or blocked(detail):
            raise ProviderBlocked(f"Provider quota/rate limit (HTTP {error.code})") from None
        raise RuntimeError(f"Provider HTTP {error.code}") from None


def clean_text(value) -> str:
    if isinstance(value, list):
        value = " ".join(str(v) for v in value)
    return html.unescape(re.sub(r"<[^>]*>", " ", str(value or "")))[:6000]


def candidate(source, ident, title, description, creator, license_label, query):
    pattern = r"[A-Za-z0-9_-]{11}" if source == "youtube" else r"[A-Za-z0-9][A-Za-z0-9_.-]{0,199}"
    if not re.fullmatch(pattern, ident):
        raise ValueError("Invalid provider identifier")
    url = (f"https://www.youtube.com/watch?v={ident}" if source == "youtube"
           else f"https://archive.org/details/{ident}")
    return {"key": f"{source}:{ident}", "source": source, "id": ident, "url": url,
            "title": clean_text(title), "description": clean_text(description),
            "creator": clean_text(creator), "license": clean_text(license_label) or "unknown",
            "queries": [query], "events": []}


def duration_seconds(value):
    """Provider duration strings: seconds, HH:MM:SS, or ISO 8601 PT."""
    try:
        text = str(value or "").strip()
        match = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?", text)
        if match:
            result = sum(float(v or 0) * unit for v, unit in zip(match.groups(), (3600, 60, 1)))
        elif ":" in text:
            parts = text.split(":")
            if not 2 <= len(parts) <= 3:
                return None
            result = sum(float(v) * 60 ** i for i, v in enumerate(reversed(parts)))
        else:
            result = float(text)
        return result if 0 < result < float("inf") else None
    except (ValueError, TypeError):
        return None


def youtube_search(query: str, limit: int) -> list[dict]:
    key = os.environ.get("YOUTUBE_API_KEY", "")
    if key:
        params = {"part": "snippet", "type": "video", "q": query, "maxResults": limit,
                  "order": "relevance", "key": key}
        data = request_json("https://www.googleapis.com/youtube/v3/search?" + urllib.parse.urlencode(params))
        ids = ",".join(v["id"]["videoId"] for v in data.get("items", []))
        if not ids:
            return []
        details = request_json("https://www.googleapis.com/youtube/v3/videos?" + urllib.parse.urlencode({
            "part": "snippet,status,contentDetails", "id": ids, "key": key}))
        rows = []
        for item in details.get("items", []):
            snippet, status = item["snippet"], item["status"]
            if status.get("privacyStatus") != "public" or snippet.get("liveBroadcastContent") != "none":
                continue
            rows.append(candidate("youtube", item["id"], snippet["title"], snippet.get("description"),
                                  snippet.get("channelTitle"), status.get("license"), query))
            rows[-1]["duration_seconds"] = duration_seconds(item.get("contentDetails", {}).get("duration"))
        return rows
    result = subprocess.run([sys.executable, "-m", "yt_dlp", "--ignore-config", "--flat-playlist",
                             "--dump-single-json", "--no-warnings", "--retries", "0",
                             "--socket-timeout", "20", f"ytsearch{limit}:{query}"],
                            capture_output=True, text=True, timeout=90)
    if result.returncode:
        if blocked(result.stderr):
            raise ProviderBlocked("YouTube requested human verification or rate limited discovery")
        raise RuntimeError(safe_error(result.stderr))
    rows = []
    for item in json.loads(result.stdout).get("entries", []):
        if not item or item.get("live_status") not in (None, "not_live"):
            continue
        rows.append(candidate("youtube", item["id"], item.get("title"), item.get("description"),
                              item.get("channel"), "unknown", query))
        rows[-1]["duration_seconds"] = duration_seconds(item.get("duration"))
    return rows


def archive_search(query: str, limit: int) -> list[dict]:
    # Escape user/model syntax rather than allowing arbitrary Lucene expressions.
    terms = re.findall(r"[^\W_]+", query, re.UNICODE)
    phrase = '"' + " ".join(terms) + '"'
    # Title results must not be crowded out by popular, hour-long programmes
    # carrying the topic only as one subject tag. Broaden only for sparse titles.
    docs = {}
    budget = min(30, limit * 2)
    for field in ("title", "subject"):
        search = f"mediatype:movies AND NOT access-restricted-item:true AND {field}:{phrase}"
        params = [("q", search), ("rows", str(budget)), ("output", "json"), ("sort[]", "downloads desc")]
        params += [("fl[]", f) for f in ("identifier", "title", "description", "creator", "licenseurl", "rights", "length")]
        data = request_json("https://archive.org/advancedsearch.php?" + urllib.parse.urlencode(params))
        for item in data.get("response", {}).get("docs", []):
            docs.setdefault(item["identifier"], item)
        if len(docs) >= limit:
            break
    return [dict(candidate("archive", v["identifier"], v.get("title"), v.get("description"),
                      v.get("creator"), v.get("licenseurl") or v.get("rights"), query),
                 duration_seconds=duration_seconds(v.get("length")))
            for v in list(docs.values())[:budget]]


def discover(plan, sources: list[str], per_query=15) -> tuple[list[dict], list[dict]]:
    from experiments.video_search.alternatives import PROVIDERS as alternatives
    providers = {"youtube": youtube_search, "archive": archive_search, **alternatives}
    candidates, attempts, stopped = {}, [], set()
    # Explicit events first; every query is retained even when a provider fails.
    tasks = []
    for topic in [*plan.events, plan.theme]:
        for source in sources:
            # Title/subject discovery avoids incidental mentions in long transcripts.
            queries = topic.queries if source == "youtube" else topic.archive_terms
            tasks.extend((source, query) for query in queries)
    for source, query in dict.fromkeys(tasks):
        row = {"source": source, "query": query}
        if source in stopped:
            attempts.append({**row, "status": "skipped_provider_blocked"})
            continue
        try:
            results = providers[source](query, per_query)
            attempts.append({**row, "status": "ok", "count": len(results)})
            for item in results:
                if item["key"] in candidates:
                    candidates[item["key"]]["queries"] = list(dict.fromkeys(
                        candidates[item["key"]]["queries"] + item["queries"]))
                else:
                    candidates[item["key"]] = item
        except Exception as error:
            if isinstance(error, ProviderBlocked):
                stopped.add(source)
            attempts.append({**row, "status": "blocked" if source in stopped else "error",
                             "error": safe_error(error)})
    for item in candidates.values():
        text = item["title"] + " " + item["description"]
        item["events"] = [event.mention for event in plan.events if matches(event, text)]
        item["relevant"] = bool(item["events"] or matches(plan.theme, text))
        item["score"] = 10 * len(item["events"]) + 100 * sum(matches(e, item["title"]) for e in plan.events)
        # Keep event titles in the semantic pool even when the planner omitted a
        # synonym from its AND groups (e.g. "caída" versus "bankruptcy"). This
        # affects discovery priority only; the semantic judge still owns relevance.
        title = f" {normalize(item['title'])} "
        item["score"] += 75 * sum(any(f" {normalize(term)} " in title for term in e.archive_terms)
                                  for e in plan.events)
        item["score"] += 50 * matches(plan.theme, item["title"])
        item["relation"] = "event_metadata_match" if item["events"] else "topic_context"
    ordered = sorted(candidates.values(), key=lambda v: (-v["score"], v["source"] != "youtube", v["key"]))
    return ordered, attempts


def archive_media(item: dict) -> tuple[str, dict]:
    payload = request_json(f"https://archive.org/metadata/{item['id']}")
    metadata = payload.get("metadata", {})
    if payload.get("is_dark") or str(metadata.get("access-restricted-item", "")).lower() == "true":
        raise RuntimeError("Archive item is restricted")
    files = [f for f in payload.get("files", []) if not f.get("private")
             and str(f.get("name", "")).lower().endswith(".mp4")
             and 0 < int(f.get("size", 0) or 0) <= 1024 * 1024 * 1024
             and not str(f.get("name", "")).lower().endswith(".thumbs.mp4")]
    if not files:
        raise RuntimeError("Archive item has no public MP4 derivative under 1 GiB")
    chosen = min(files, key=lambda v: int(v["size"]))
    filename = str(chosen["name"])
    if ".." in filename.split("/") or filename.startswith("/"):
        raise ValueError("Invalid archive filename")
    url = f"https://archive.org/download/{item['id']}/" + urllib.parse.quote(filename, safe="/")
    stem = filename.removesuffix(".mp4").removesuffix(".ia")
    captions = []
    for file in payload.get("files", []):
        name = str(file.get("name", ""))
        ext = name.rsplit(".", 1)[-1].lower()
        if file.get("private") or ext not in {"vtt", "srt"} or ".." in name.split("/") or name.startswith("/"):
            continue
        if not name.startswith(stem) and len(files) != 1:
            continue
        captions.append({"url": f"https://archive.org/download/{item['id']}/" + urllib.parse.quote(name, safe="/"), "ext": ext})
    return url, {"id": item["id"], "title": clean_text(metadata.get("title")),
                 "creator": clean_text(metadata.get("creator")), "file": filename,
                 "source_size_bytes": int(chosen["size"]),
                 "license": clean_text(metadata.get("licenseurl") or metadata.get("rights")) or "unknown",
                 "_captions": captions}
