"""Bounded, unauthenticated publisher-page evidence for selected news.

This is a supplementary excerpt, not a full-document download or independent
fact verdict. Original digests and identifiers remain immutable.
"""
from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256
from html.parser import HTMLParser
import json
import re
from time import monotonic
from typing import Any
from urllib.parse import urlsplit

import requests

# Exact hosts AND article paths, never arbitrary model-/digest-supplied hosts,
# redirectors, APIs with user parameters, file URLs, or credentials.
ARTICLE_PATHS = {
    "www.nature.com": r"/articles/[a-zA-Z0-9._-]+/?",
    "arxiv.org": r"/abs/[A-Za-z0-9./-]+",
    "openai.com": r"/(?:index|research)/[A-Za-z0-9/_-]+/?",
    "www.anthropic.com": r"/(?:research|news|engineering)/[A-Za-z0-9/_-]+/?",
    "blog.google": r"/(?:innovation-and-ai|technology|products)/[A-Za-z0-9/_-]+/?",
    "research.google": r"/blog/[A-Za-z0-9/_-]+/?",
    "news.mit.edu": r"/\d{4}/[A-Za-z0-9_-]+/?",
    "www.gov.uk": r"/government/(?:news|publications|speeches)/[A-Za-z0-9/_-]+/?",
    "www.federalreserve.gov": r"/(?:newsevents|publications)/[A-Za-z0-9/_.-]+",
    "www.fda.gov": r"/[A-Za-z0-9/_-]+/[A-Za-z0-9/_-]+/?",
    "www.microsoft.com": r"/(?:en-us/)?(?:research|ai|blog)/[A-Za-z0-9/_-]+/?",
}
MAX_ITEMS = 8
MAX_BYTES = 2_000_000
MAX_EXCERPT_CHARS = 1500
MAX_SECONDS = 12
MIN_EXCERPT_CHARS = 120


def allowed_url(url: str) -> bool:
    if re.search(r"[\x00-\x20\x7f\\]", url):
        return False
    try:
        parsed = urlsplit(url)
        pattern = ARTICLE_PATHS.get(parsed.hostname or "")
        return bool(
            parsed.scheme == "https" and pattern and parsed.netloc == parsed.hostname and not parsed.username
            and not parsed.password and parsed.port is None
            and not parsed.query and not parsed.fragment
            and not any(x in {".", ".."} for x in parsed.path.split("/"))
            and re.fullmatch(pattern, parsed.path)
        )
    except ValueError:
        return False


class _ArticleText(HTMLParser):
    """Only visible abstract/article/main paragraphs; never arbitrary metadata."""
    VOID = frozenset("area base br col embed hr img input link meta param source track wbr".split())
    OMIT = frozenset("script style nav header footer aside form noscript svg template".split())

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, bool, bool, bool]] = []
        self.capture: tuple[int, str, list[str]] | None = None
        self.abstract: list[str] = []
        self.article: list[str] = []
        self.title_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.VOID:
            return
        a = dict(attrs)
        marker = f"{a.get('id') or ''} {a.get('class') or ''}".lower()
        parent = self.stack[-1] if self.stack else ("", False, False, False)
        abstract = parent[1] or bool(re.search(r"(?:^|[ _-])abstract(?:$|[ _-])", marker))
        article = parent[2] or tag in {"article", "main"} or a.get("role") == "main"
        hidden = parent[3] or tag in self.OMIT or "hidden" in a or a.get("aria-hidden") == "true"
        self.stack.append((tag, abstract, article, hidden))
        if not hidden and self.capture is None:
            # arXiv uses blockquote.abstract; Nature typically uses section > p.
            if tag == "p" and (abstract or article) or tag == "blockquote" and abstract:
                self.capture = (len(self.stack), "abstract" if abstract else "article", [])

    def handle_endtag(self, tag: str) -> None:
        idx = next((i for i in range(len(self.stack) - 1, -1, -1) if self.stack[i][0] == tag), None)
        if idx is None:
            return
        if self.capture and idx < self.capture[0]:
            _, kind, parts = self.capture
            paragraph = " ".join("".join(parts).split())
            if len(paragraph) >= 60:
                # Skip obvious access/challenge prompts, not silently call them articles.
                if not re.search(r"(?i)enable javascript|accept cookies|verify (?:that )?you are human|sign in to continue|access denied|subscribe to read", paragraph):
                    (self.abstract if kind == "abstract" else self.article).append(paragraph)
            self.capture = None
        del self.stack[idx:]

    def handle_data(self, data: str) -> None:
        if self.stack and not self.stack[-1][3]:
            if self.capture:
                self.capture[2].append(data)
            if self.stack[-1][0] == "title":
                self.title_parts.append(data)


def extract_excerpt(html: str) -> tuple[str, str, str]:
    parsed = _ArticleText()
    parsed.feed(html)
    title = " ".join("".join(parsed.title_parts).split())[:300]
    if re.search(r"(?i)access denied|just a moment|captcha|verify you are human|page not found", title):
        return "", "", title
    paragraphs = parsed.abstract or parsed.article
    kind = "abstract_excerpt" if parsed.abstract else "article_excerpt"
    excerpt = "\n\n".join(dict.fromkeys(paragraphs))[:MAX_EXCERPT_CHARS].strip()
    return (excerpt, kind, title) if len(excerpt) >= MIN_EXCERPT_CHARS else ("", "", title)


def fetch_item(item: dict[str, Any], *, session: Any = None) -> dict[str, Any]:
    url = str(item.get("url") or "")
    row: dict[str, Any] = {
        "news_id": item["news_id"], "selected_news_index": item["selected_news_index"],
        "url": url, "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "unsupported_url",
    }
    if item.get("url_quality") != "article" or not allowed_url(url):
        return row
    own = session is None
    client = requests.Session() if own else session
    if own:
        # No ambient proxy auth or netrc credentials; no cookies shared across publishers.
        client.trust_env = False
    try:
        start = monotonic()
        with client.get(url, headers={"User-Agent": "AI-News-Daily evidence reader/1.0", "Accept": "text/html"},
                        stream=True, allow_redirects=False, timeout=(4, 5)) as response:
            row["http_status"] = response.status_code
            if response.status_code != 200:
                row["status"] = "redirect_not_followed" if 300 <= response.status_code < 400 else "http_unavailable"
                return row
            if response.headers.get("Content-Type", "").split(";")[0].lower() not in {"text/html", "application/xhtml+xml"}:
                row["status"] = "unsupported_content_type"
                return row
            chunks = bytearray()
            for part in response.iter_content(chunk_size=16384):
                if monotonic() - start > MAX_SECONDS or len(chunks) + len(part) > MAX_BYTES:
                    row["status"] = "response_budget_exceeded"
                    return row
                chunks.extend(part)
            row["response_bytes"] = len(chunks)
            row["response_sha256"] = sha256(chunks).hexdigest()
            row["final_url"] = url  # redirects explicitly disabled
            excerpt, kind, title = extract_excerpt(chunks.decode("utf-8", errors="replace"))
            row["page_title"] = title
            if not excerpt:
                row["status"] = "no_usable_excerpt"
                return row
            # Retrieval is not proof that the article corroborates the digest.
            row.update(status="excerpt_retrieved", excerpt_kind=kind, excerpt=excerpt,
                       excerpt_chars=len(excerpt), excerpt_sha256=sha256(excerpt.encode()).hexdigest())
            return row
    except (requests.RequestException, ValueError) as exc:
        row.update(status="retrieval_unavailable", error_type=type(exc).__name__)
        return row
    finally:
        if own:
            client.close()


def collect_evidence(items: list[dict[str, Any]], *, enabled: bool) -> list[dict[str, Any]]:
    if len(items) > MAX_ITEMS:
        raise ValueError("Source evidence exceeded selected-story budget")
    if not enabled:
        return [{"news_id": item["news_id"], "selected_news_index": item["selected_news_index"],
                 "url": item.get("url", ""), "status": "disabled"} for item in items]
    with ThreadPoolExecutor(max_workers=4) as pool:
        return list(pool.map(fetch_item, items))


def manifest(rows: list[dict[str, Any]]) -> dict[str, Any]:
    # Do not republish publisher text; preserve identity, scope, hashes and outcome.
    return {
        "schema_version": 1, "selected_count": len(rows),
        "status_counts": dict(Counter(row["status"] for row in rows)),
        "retrieval_is_not_fact_verification": True,
        "items": [{k: v for k, v in row.items() if k != "excerpt"} for row in rows],
    }


def context_json(rows: list[dict[str, Any]], selected_indices: set[int] | None = None) -> str:
    items = [row for row in rows if selected_indices is None or row["selected_news_index"] in selected_indices]
    return json.dumps({"scope": "bounded publisher excerpts; not full documents or independent verification",
                       "items": items}, ensure_ascii=False, separators=(",", ":"))
