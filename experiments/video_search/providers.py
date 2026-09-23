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

from experiments.video_search.plan import matches


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
        if error.code == 429 or blocked(detail):
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
    return rows


def archive_search(query: str, limit: int) -> list[dict]:
    # Escape user/model syntax rather than allowing arbitrary Lucene expressions.
    terms = re.findall(r"[^\W_]+", query, re.UNICODE)
    search = "mediatype:movies AND (" + " AND ".join(f'"{t}"' for t in terms) + ")"
    params = [("q", search), ("rows", str(limit)), ("output", "json")]
    params += [("fl[]", f) for f in ("identifier", "title", "description", "creator", "licenseurl", "rights")]
    data = request_json("https://archive.org/advancedsearch.php?" + urllib.parse.urlencode(params))
    return [candidate("archive", v["identifier"], v.get("title"), v.get("description"),
                      v.get("creator"), v.get("licenseurl") or v.get("rights"), query)
            for v in data.get("response", {}).get("docs", [])]


def discover(plan, sources: list[str], per_query=15) -> tuple[list[dict], list[dict]]:
    candidates, attempts, stopped = {}, [], set()
    # Explicit events first; every query is retained even when a provider fails.
    tasks = []
    for topic in [*plan.events, plan.theme]:
        for source in sources:
            # Archive ANDs every term: Google's natural-language query ("Enron
            # collapse scandal video") over-constrains it. Use the plan's core
            # matching groups; semantic assessment still rejects incidental hits.
            queries = topic.queries if source == "youtube" else [" ".join(g) for g in topic.match_groups[:2]]
            tasks.extend((source, query) for query in queries)
    for source, query in dict.fromkeys(tasks):
        row = {"source": source, "query": query}
        if source in stopped:
            attempts.append({**row, "status": "skipped_provider_blocked"})
            continue
        try:
            results = {"youtube": youtube_search, "archive": archive_search}[source](query, per_query)
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
        item["score"] = 100 * len(item["events"]) + 10 * sum(matches(e, item["title"]) for e in plan.events)
        item["score"] += 5 * matches(plan.theme, item["title"])
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
    return url, {"id": item["id"], "title": clean_text(metadata.get("title")),
                 "creator": clean_text(metadata.get("creator")), "file": filename,
                 "source_size_bytes": int(chosen["size"]),
                 "license": clean_text(metadata.get("licenseurl") or metadata.get("rights")) or "unknown"}
