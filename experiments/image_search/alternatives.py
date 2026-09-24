"""Article-to-file discovery and anonymous Openverse image search.

Article association is only discovery, never proof of depicted identity/event.
The existing source-quote, identity, historical and visual gates still apply.
"""
from __future__ import annotations

import re

from experiments.image_search.sources import api, candidate, normalize


def wikipedia(plan, entity):
    rows, seen = [], set()
    for language in ("en", "es"):
        base = f"https://{language}.wikipedia.org/w/api.php"
        common = dict(action="query", format="json", formatversion=2, redirects=1,
                      prop="pageimages|images|pageprops", piprop="name", pilicense="any", imlimit=12)
        data = api(base, titles="|".join(dict.fromkeys([plan.subject, *plan.queries])), **common)
        pages = [p for p in data.get("query", {}).get("pages", []) if "missing" not in p]
        if not pages:
            data = api(base, generator="search", gsrsearch=plan.subject, gsrnamespace=0, gsrlimit=3, **common)
            pages = data.get("query", {}).get("pages", [])
        for page in pages[:3]:
            # Disambiguation pages have no defensible entity/file relationship.
            props = page.get("pageprops", {})
            if "disambiguation" in props:
                continue
            files = (["File:" + page["pageimage"]] if page.get("pageimage") else [])
            files += [im["title"] for im in page.get("images", [])]
            files = list(dict.fromkeys(f for f in files if re.search(r"\.(jpe?g|png|webp)$", f, re.I)))[:12]
            if not files:
                continue
            anchored = set(entity.get("images", [])) if entity.get("status") == "resolved" else set()
            qid = props.get("wikibase_item", "")
            # Recover transliterated P18 file attribution through the article's
            # actual Wikidata item, exact canonical label and human type.
            if plan.kind == "person" and re.fullmatch(r"Q\d+", qid):
                record = api("https://www.wikidata.org/w/api.php", action="wbgetentities", ids=qid,
                             props="labels|claims", languages="en|es", format="json").get("entities", {}).get(qid, {})
                claims = record.get("claims", {})
                labels = [v.get("value", "") for v in record.get("labels", {}).values()]
                human = any(c.get("mainsnak", {}).get("datavalue", {}).get("value", {}).get("id") == "Q5"
                            for c in claims.get("P31", []) if c.get("rank") != "deprecated")
                if human and any(normalize(v) == normalize(plan.subject) for v in labels):
                    anchored.update(c.get("mainsnak", {}).get("datavalue", {}).get("value")
                                    for c in claims.get("P18", []) if c.get("rank") != "deprecated")
            detail = api(base, action="query", format="json", formatversion=2, titles="|".join(files),
                         prop="imageinfo", iiprop="url|size|mime|extmetadata", iiurlwidth=1600,
                         iiextmetadatalanguage="en")
            for file in detail.get("query", {}).get("pages", []):
                info = (file.get("imageinfo") or [{}])[0]
                original = info.get("url", "")
                if not original or original in seen or info.get("mime") not in {"image/jpeg", "image/png", "image/webp"}:
                    continue
                seen.add(original)
                ext = {k: v.get("value", "") for k, v in info.get("extmetadata", {}).items()}
                # Deterministic ID: shared files have no local Wikipedia pageid.
                import hashlib
                ident = language + "-" + hashlib.sha256(original.encode()).hexdigest()[:20]
                metadata = dict(title=file["title"], description=ext.get("ImageDescription", ""),
                                date=ext.get("DateTimeOriginal", ""), creator=ext.get("Artist", ""),
                                license=ext.get("LicenseShortName", "unknown"), license_url=ext.get("LicenseUrl", ""),
                                restrictions=ext.get("Restrictions", ""), credit=ext.get("Credit", ""))
                rows.append(candidate("wikipedia", ident, info["descriptionurl"], info.get("thumburl") or original,
                                      metadata, original_url=original, entity_anchor=file["title"].split(":", 1)[-1] in anchored,
                                      discovery_article=page["title"], discovery_wikidata=qid,
                                      variant="provider_derivative" if info.get("thumburl") else "original"))
    return rows[:24]


def openverse(plan, entity):
    # Anonymous public API. No signup, key or paid endpoint. Stop on 403/429.
    # Restrict downloads to documented catalogue/CDN hosts already supported;
    # Openverse includes many other hosts which are deliberately not fetched.
    rows = []
    data = api("https://api.openverse.org/v1/images/", q=plan.subject, page_size=20)
    for item in data.get("results", []):
        ident = item.get("id", "")
        if not re.fullmatch(r"[a-f0-9-]{36}", ident):
            continue
        metadata = dict(title=item.get("title", ""), description=item.get("description", ""),
                        tags=item.get("tags", []), creator=item.get("creator", ""),
                        license=str(item.get("license", "")) + " " + str(item.get("license_version", "")),
                        license_url=item.get("license_url", ""), credit=item.get("attribution", ""))
        try:
            rows.append(candidate("openverse", ident, f"https://openverse.org/image/{ident}", item["url"],
                                  metadata, foreign_landing_url=item.get("foreign_landing_url"), variant="provider_original"))
        except (ValueError, KeyError):
            continue
    return rows


PROVIDERS = {"wikipedia": wikipedia, "openverse": openverse}
