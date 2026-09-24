"""Small, bounded adapters for public institutional image catalogues."""
from __future__ import annotations

import html
import json
import os
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request


USER_AGENT = "AI-News-Daily-image-research/1.0 (https://github.com/jcval94/AI-News-Daily)"
MEDIA_HOSTS = {"commons": ("upload.wikimedia.org", "thumb.wikimedia.org"), "met": ("images.metmuseum.org",),
               "artic": ("www.artic.edu",), "loc": ("loc.gov",),
               "wikipedia": ("upload.wikimedia.org", "thumb.wikimedia.org"),
               "openverse": ("upload.wikimedia.org", "staticflickr.com", "images.metmuseum.org", "loc.gov")}
API_HOSTS = ("commons.wikimedia.org", "www.wikidata.org", "collectionapi.metmuseum.org",
             "api.artic.edu", "www.loc.gov", "api.openai.com", "en.wikipedia.org", "es.wikipedia.org",
             "api.openverse.org")


def normalize(text):
    text = unicodedata.normalize("NFKD", str(text).casefold())
    return " ".join(re.findall(r"[^\W_]+", "".join(c for c in text if not unicodedata.combining(c))))


def clean(value, limit=4000):
    if isinstance(value, (list, dict)):
        value = json.dumps(value, ensure_ascii=False)
    return html.unescape(re.sub(r"<[^>]*>", " ", str(value or "")))[:limit]


def safe_error(error):
    text = str(error)
    for name in ("OPENAI_API_KEY",):
        if os.environ.get(name):
            text = text.replace(os.environ[name], "[redacted]")
    return re.sub(r"https?://\S+", "[remote-url]", text)[-600:]


class Blocked(RuntimeError):
    pass


def validate_url(url, domains):
    p = urllib.parse.urlsplit(url)
    if p.scheme != "https" or p.username or p.password or p.port not in (None, 443):
        raise ValueError("Only HTTPS source URLs without credentials are allowed")
    host = p.hostname or ""
    if not any(host == d or host.endswith("." + d) for d in domains):
        raise ValueError("URL is outside the provider host allowlist")


class Redirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, domains):
        self.domains = domains

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl, self.domains)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url, *, domains, max_bytes, timeout=30, body=None, headers=None):
    validate_url(url, domains)
    request = urllib.request.Request(url, data=None if body is None else json.dumps(body).encode(),
                                     headers={"User-Agent": USER_AGENT,
                                              **({"Content-Type": "application/json"} if body is not None else {}),
                                              **(headers or {})})
    try:
        with urllib.request.build_opener(Redirect(domains)).open(request, timeout=timeout) as response:
            if int(response.headers.get("Content-Length", 0)) > max_bytes:
                raise ValueError("Remote file exceeds size budget")
            data = response.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise ValueError("Remote file exceeds size budget")
        return data
    except urllib.error.HTTPError as error:
        if error.code in (401, 403, 429):
            raise Blocked(f"Provider denied access or rate limited (HTTP {error.code})") from None
        raise RuntimeError(f"Provider HTTP {error.code}") from None


def request_json(url, **kwargs):
    data = json.loads(fetch(url, domains=API_HOSTS, max_bytes=8 * 1024 * 1024, **kwargs))
    if not isinstance(data, dict):
        raise ValueError("API returned a non-object")
    if data.get("error"):
        raise RuntimeError("Provider returned an API error")
    return data


def api(base, **params):
    return request_json(base + "?" + urllib.parse.urlencode(params))


def resolve_entity(plan):
    base = "https://www.wikidata.org/w/api.php"
    results = api(base, action="wbsearchentities", search=plan.subject, language="en", limit=7, format="json")
    exact = [r for r in results.get("search", [])
             if any(normalize(name) == normalize(plan.subject)
                    for name in [r.get("label", ""), *r.get("aliases", []), r.get("match", {}).get("text", "")])]
    exact = [r for r in exact if re.fullmatch(r"Q\d+", r.get("id", ""))]
    if not exact:
        return {"status": "unresolved", "reason": "No unique exact canonical entity label"}
    data = api(base, action="wbgetentities", ids="|".join(r['id'] for r in exact),
               props="labels|descriptions|claims", languages="en|es", format="json")
    entities = data.get("entities", {})
    if plan.kind == "person":
        exact = [r for r in exact if any(c.get("mainsnak", {}).get("datavalue", {}).get("value", {}).get("id") == "Q5"
                 and c.get("rank") != "deprecated" for c in entities.get(r['id'], {}).get("claims", {}).get("P31", []))]
    if len(exact) != 1:
        return {"status": "unresolved", "reason": "No unique canonical entity of the requested kind"}
    ident = exact[0]["id"]
    entity = entities.get(ident, {})
    claims = entity.get("claims", {})
    values = lambda prop: [c.get("mainsnak", {}).get("datavalue", {}).get("value") for c in claims.get(prop, [])
                           if c.get("rank") != "deprecated"]
    if plan.kind == "person" and not any(isinstance(v, dict) and v.get("id") == "Q5" for v in values("P31")):
        return {"status": "unresolved", "reason": "Canonical entity is not catalogued as a human"}
    return {"status": "resolved", "id": ident, "label": exact[0]["label"],
            "description": exact[0].get("description", ""), "url": f"https://www.wikidata.org/wiki/{ident}",
            "images": [v for v in values("P18") if isinstance(v, str)][:2]}


def candidate(source, ident, url, image_url, metadata, **extra):
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,160}", str(ident)):
        raise ValueError("Unsafe catalogue identifier")
    validate_url(image_url, MEDIA_HOSTS[source])
    validate_url(url, {"commons": ("commons.wikimedia.org",), "met": ("metmuseum.org",),
                       "artic": ("artic.edu",), "loc": ("loc.gov",),
                       "wikipedia": ("wikipedia.org", "commons.wikimedia.org"),
                       "openverse": ("openverse.org",)}[source])
    return {"key": f"{source}:{ident}", "source": source, "id": str(ident), "url": url,
            "image_url": image_url, "metadata": {k: clean(v) for k, v in metadata.items()}, **extra}


def commons(plan, entity):
    base = "https://commons.wikimedia.org/w/api.php"
    pages = {}
    common = dict(action="query", format="json", formatversion=2, prop="imageinfo",
                  iiprop="url|size|mime|extmetadata", iiurlwidth=1600, iiextmetadatalanguage="en")
    if entity.get("status") == "resolved" and entity.get("images"):
        data = api(base, titles="|".join("File:" + name for name in entity["images"]), **common)
        for row in data.get("query", {}).get("pages", []):
            row["entity_anchor"] = True
            pages[row.get("pageid")] = row
    # Search terms are an AND of escaped literal words. Quoting the entire
    # generated phrase incorrectly required dates/places to be adjacent.
    queries = [' '.join('"' + word + '"' for word in re.findall(r'[^\W_]+', q, re.UNICODE))
               + ' filetype:bitmap' for q in plan.queries]
    if entity.get("status") == "resolved":
        queries.insert(0, f"haswbstatement:P180={entity['id']} filetype:bitmap")
    for query in queries[:3]:
        data = api(base, generator="search", gsrsearch=query, gsrnamespace=6, gsrlimit=15, **common)
        for row in data.get("query", {}).get("pages", []):
            pages.setdefault(row.get("pageid"), row)
    rows = []
    for row in pages.values():
        infos = row.get("imageinfo") or []
        if not infos or infos[0].get("mime") not in {"image/jpeg", "image/png", "image/webp"}:
            continue
        info = infos[0]
        ext = {k: v.get("value", "") for k, v in info.get("extmetadata", {}).items()}
        metadata = {"title": row["title"], "description": ext.get("ImageDescription", ""),
                    "date": ext.get("DateTimeOriginal", ""), "creator": ext.get("Artist", ""),
                    "categories": ext.get("Categories", ""), "license": ext.get("LicenseShortName", "unknown"),
                    "license_url": ext.get("LicenseUrl", ""), "credit": ext.get("Credit", ""),
                    "restrictions": ext.get("Restrictions", "")}
        rows.append(candidate("commons", row["pageid"], info["descriptionurl"],
                              info.get("thumburl") or info["url"], metadata,
                              original_url=info["url"], entity_anchor=row.get("entity_anchor", False),
                              variant="provider_derivative" if info.get("thumburl") else "original"))
    return rows[:20]


def met(plan, entity):
    base = "https://collectionapi.metmuseum.org/public/collection/"
    params = {"q": plan.museum_query, "hasImages": "true", "limit": 20, "isHighlight": "true"}
    if plan.date_start is not None:
        params.update(dateBegin=plan.date_start, dateEnd=plan.date_end)
    data = api(base + "v1.1/search", **params)
    ids = data.get("objectIDs") or []
    if not ids:
        params.pop("isHighlight")
        ids = api(base + "v1.1/search", **params).get("objectIDs") or []
    rows = []
    for ident in ids[:20]:
        if not isinstance(ident, int):
            continue
        try:
            d = request_json(base + f"v1/objects/{ident}")
        except Blocked:
            raise
        except RuntimeError:
            # Search indexes can reference retired object records.
            continue
        if d.get("isPublicDomain") is not True or not d.get("primaryImage"):
            continue
        metadata = {"title": d.get("title"), "culture": d.get("culture"), "period": d.get("period"),
                    "date": d.get("objectDate"), "description": d.get("objectName"),
                    "medium": d.get("medium"), "creator": d.get("artistDisplayName"),
                    "country": d.get("country"), "tags": d.get("tags"), "credit": d.get("creditLine"),
                    "license": "CC0", "license_url": "https://creativecommons.org/publicdomain/zero/1.0/"}
        rows.append(candidate("met", ident, d["objectURL"], d["primaryImage"], metadata,
                              object_start=d.get("objectBeginDate"), object_end=d.get("objectEndDate"),
                              variant="original"))
    return rows


def artic(plan, entity):
    fields = "id,title,image_id,artist_display,date_display,date_start,date_end,description,place_of_origin,style_titles,classification_titles,medium_display,credit_line,is_public_domain"
    d = api("https://api.artic.edu/api/v1/artworks/search", q=plan.museum_query, limit=20,
            fields=fields, **{"query[term][is_public_domain]": "true"})
    rows = []
    for row in d.get("data", []):
        if row.get("is_public_domain") is not True or not re.fullmatch(r"[a-f0-9-]+", row.get("image_id") or ""):
            continue
        metadata = {"title": row.get("title"), "description": row.get("description"),
                    "culture": row.get("artist_display"), "period": row.get("style_titles"),
                    "date": row.get("date_display"), "country": row.get("place_of_origin"),
                    "medium": row.get("medium_display"), "credit": row.get("credit_line"),
                    "license": "CC0", "license_url": "https://creativecommons.org/publicdomain/zero/1.0/"}
        rows.append(candidate("artic", row["id"], f"https://www.artic.edu/artworks/{row['id']}",
                              f"https://www.artic.edu/iiif/2/{row['image_id']}/full/843,/0/default.jpg", metadata,
                              object_start=row.get("date_start"), object_end=row.get("date_end"), variant="provider_derivative"))
    return rows


def loc(plan, entity):
    rows = {}
    for query in plan.queries:
        data = api("https://www.loc.gov/photos/", fo="json", q=query, c=15)
        for item in data.get("results", []):
            ident = (item.get("id") or "").rstrip("/").split("/")[-1]
            images = item.get("image_url") or []
            if not ident or not images or not re.fullmatch(r"[A-Za-z0-9_.-]{1,160}", ident):
                continue
            image = images[-1]
            if image.startswith("//"):
                image = "https:" + image
            if image.startswith("http://"):
                image = "https://" + image[7:]
            meta = {"title": item.get("title"), "description": item.get("description"),
                    "subjects": item.get("subject"), "date": item.get("date"),
                    "creator": item.get("contributor"), "rights": item.get("rights"),
                    "license": "consult_source_rights", "credit": "Library of Congress"}
            try:
                rows.setdefault(ident, candidate("loc", ident, item["id"], image, meta, variant="provider_derivative"))
            except ValueError:
                continue
        time.sleep(1)
    return list(rows.values())[:20]


PROVIDERS = {"commons": commons, "met": met, "artic": artic, "loc": loc}


def discover(plan, providers, entity):
    from experiments.image_search.alternatives import PROVIDERS as alternatives
    registry = {**PROVIDERS, **alternatives}
    candidates, diagnostics = [], []
    for name in providers:
        try:
            rows = registry[name](plan, entity)
            candidates.extend(rows)
            diagnostics.append({"source": name, "status": "ok", "count": len(rows)})
        except Exception as error:
            diagnostics.append({"source": name, "status": "blocked" if isinstance(error, Blocked) else "failed",
                                "error": safe_error(error)})
    unique = {c["key"]: c for c in candidates}
    # Bound the semantic call without letting large catalogues crowd out others.
    grouped = [[c for c in unique.values() if c["source"] == p] for p in providers]
    balanced = [g[i] for i in range(max(map(len, grouped), default=0)) for g in grouped if i < len(g)]
    return balanced[:80], diagnostics
