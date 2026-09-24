"""Description → evidence-backed catalogue images → isolated Actions artifact."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import time
import warnings

from PIL import Image, ImageOps

from experiments.image_search import model, sources


ROOT = Path(__file__).resolve().parents[2]
MAX_BYTES = 25 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 40_000_000
EVIDENCE_FIELDS = {"title", "description", "culture", "period", "subjects", "tags", "date", "country"}
SYNTHETIC = re.compile(r"\b(ai.generated|midjourney|dall.e|stable diffusion|computer.generated|3d render)\b", re.I)


def metadata_gate(plan, item, decision):
    if not decision or decision["relevance"] != "direct":
        return "No direct, supported relevance assessment"
    field, quote = decision["evidence_field"], decision["evidence_quote"]
    if field not in EVIDENCE_FIELDS or len(quote.strip()) < 3 or quote not in item["metadata"].get(field, ""):
        return "Evidence quote is absent or not from a subject field"
    if decision["depiction"] not in plan.allowed_types:
        return "Depiction type does not satisfy the requested medium"
    if SYNTHETIC.search(" ".join(item["metadata"].values())):
        return "Metadata indicates synthetic content"
    if plan.kind == "person":
        # Identity comes from catalogue attribution, never face recognition.
        tokens = sources.normalize(plan.subject).split()
        fields = [item["metadata"].get(k, "") for k in ("title", "description", "subjects")]
        explicit_name = any(all(f" {word} " in f" {sources.normalize(value)} " for word in tokens)
                            for value in fields)
        if not explicit_name and not item.get("entity_anchor"):
            return "Full canonical person name absent from depiction metadata"
        if not item.get("entity_anchor") and not all(f" {word} " in f" {sources.normalize(quote)} " for word in tokens):
            return "Person attribution must be explicit in the evidence quote"
        if re.search(r"\b(named after|impersonator|lookalike|costume|memorial|monument|caricature)\b",
                     item["metadata"].get("title", "") + " " + quote, re.I):
            return "Person is referenced indirectly rather than photographically depicted"
    if plan.date_start is not None and item.get("object_start") is not None and item.get("object_end") is not None:
        start, end = item["object_start"], item["object_end"]
        if not isinstance(start, int) or not isinstance(end, int) or start > end:
            return "Invalid catalogue object dates"
        if end < plan.date_start or start > plan.date_end:
            return "Object originates outside requested historical period"
    return None


def inspect_file(path):
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(path) as im:
            fmt = im.format
            if fmt not in {"JPEG", "PNG", "WEBP"} or getattr(im, "n_frames", 1) != 1:
                raise ValueError("Unsupported or animated image")
            im.verify()
        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            im.load()
            if min(im.size) < 200 or max(im.size) < 600:
                raise ValueError("Image below minimum useful resolution (200/600 px)")
            grey = im.convert("L").resize((9, 8))
            pixels = list(grey.get_flattened_data())
            bits = [pixels[y * 9 + x] > pixels[y * 9 + x + 1] for y in range(8) for x in range(8)]
            dhash = sum(int(b) << i for i, b in enumerate(bits))
            return {"format": fmt, "width": im.width, "height": im.height,
                    "size_bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "pixel_sha256": hashlib.sha256(str(im.size).encode() + im.tobytes()).hexdigest(),
                    "dhash": f"{dhash:016x}"}


def catalogue_family(item):
    if item['source'] != 'commons':
        return None
    title = item['metadata'].get('title', '')
    title = re.sub(r'^File:', '', title, flags=re.I)
    title = re.sub(r'\.(jpg|jpeg|png|webp)$', '', title, flags=re.I)
    title = re.sub(r'\b(cleaned|restored|restoration|cropped|crop|retouched|colorized|colourised|colorised)\b',
                   '', title, flags=re.I)
    normalized = sources.normalize(title)
    return 'commons:' + normalized if len(normalized.split()) >= 3 else None


def is_duplicate(media, previous):
    return any((media.get('catalogue_family') and media['catalogue_family'] == p.get('catalogue_family')) or
               media["sha256"] == p["sha256"] or media["pixel_sha256"] == p["pixel_sha256"] or
               (int(media["dhash"], 16) ^ int(p["dhash"], 16)).bit_count() <= 3 for p in previous)


def visual_gate(plan, decision, visual):
    if not visual["usable"] or visual["obvious_synthetic_or_meme"]:
        return "Visual inspection rejected usability/synthetic content"
    # The visual classifier labels ANY photograph containing people person_photo.
    # A catalogued historical scene can therefore be a site/object photograph
    # semantically while containing participants. Its subject still needs the
    # preceding literal source-evidence gate; portraits and synthetic art do not
    # gain this exception for person requests.
    if (plan.kind == "historical" and visual["kind"] == "person_photo"
            and decision["depiction"] in {"site_photo", "object_photo"}
            and decision["depiction"] in plan.allowed_types):
        return None
    if visual["kind"] not in plan.allowed_types:
        return "Visible medium does not match requested medium"
    if visual["kind"] != decision["depiction"]:
        return "Catalogue assessment and visible medium disagree"
    return None


def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def report(output, manifest):
    accepted = [r for r in manifest["items"] if r["status"] == "downloaded"]
    manifest["summary"] = {"requested": manifest["count"], "downloaded": len(accepted),
                           "gate_passed": len(accepted) == manifest["count"] and not manifest.get("fatal_error"),
                           "by_source": {p: sum(r["source"] == p for r in accepted) for p in manifest["sources"]},
                           "precision_measured": False,
                           "note": "Accepted by evidence and medium gates; no universal accuracy claim."}
    save_json(output / "manifest.json", manifest)
    esc = lambda v: html.escape(str(v), quote=True)
    cards, attribution = [], ["# Source attribution", "", "Provider rights statements are preserved per image.", ""]
    for row in accepted:
        title = row["metadata"].get("title", row["id"])
        cards.append(f'<article><a href="{esc(row["path"])}"><img loading="lazy" src="{esc(row["path"])}" alt="{esc(title)}"></a>'
                     f'<h2>{esc(title)}</h2><p>{esc(row["source"])} · {esc(row["assessment"]["depiction"])}</p>'
                     f'<p>{esc(row["assessment"]["reason"])}</p><blockquote>{esc(row["assessment"]["evidence_quote"])}</blockquote>'
                     f'<p>{esc(row["metadata"].get("date", ""))} · {esc(row["metadata"].get("license", "unknown"))}</p>'
                     f'<a href="{esc(row["url"])}" rel="noreferrer">Ficha original</a></article>')
        attribution.append(f'- {esc(title).replace(chr(10), " ")} — {row["url"]}; {esc(row["metadata"].get("license", "unknown"))}')
    page = '<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
    page += '<title>Imágenes recuperadas</title><style>body{font:16px system-ui;background:#f5f4f0;color:#20251f;margin:3vw}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:24px}article{background:white;padding:20px;border-radius:12px}img{width:100%;height:320px;object-fit:contain}h2{font-size:18px}blockquote{margin:12px 0;border-left:3px solid #819a76;padding-left:12px}p{line-height:1.5}</style>'
    page += f'<h1>{esc(manifest["description"])}</h1><p>{len(accepted)}/{manifest["count"]} imágenes descargadas. Fotografías y objetos catalogados; no se generaron imágenes.</p>'
    page += '<p>La atribución de personas proviene de las fichas, no de reconocimiento facial. La fecha del objeto puede diferir de la fecha de su fotografía.</p><main>' + ''.join(cards) + '</main></html>'
    (output / "gallery.html").write_text(page, encoding="utf-8")
    (output / "ATTRIBUTION.md").write_text("\n".join(attribution) + "\n", encoding="utf-8")
    lines = ["# Image retrieval experiment", "", f"Accepted downloads: {len(accepted)}/{manifest['count']}",
             f"Gate passed: {manifest['summary']['gate_passed']}", "",
             "Open gallery.html for images and catalogue evidence. See manifest.json for rejected candidates and source failures.",
             "No images generated. Source bytes are preserved. Precision is not a calibrated percentage."]
    if manifest.get("fatal_error"):
        lines += ["", "Error: " + esc(manifest["fatal_error"])]
    (output / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    files = sorted(p for p in output.rglob("*") if p.is_file() and p.name != "SHA256SUMS")
    (output / "SHA256SUMS").write_text("".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(output)}\n" for p in files))
    return manifest["summary"]["gate_passed"]


def execute(args, output):
    started = time.monotonic()
    manifest = {"schema_version": 1, "description": args.description, "count": args.count,
                "sources": args.sources.split(","), "items": [], "discovery": [],
                "github": {k: os.environ.get(k) for k in ("GITHUB_SHA", "GITHUB_RUN_ID")}}
    report(output, manifest)
    try:
        plan, manifest["planning"] = model.make_plan(args.description, sources.request_json)
        manifest["plan"] = plan.model_dump()
        save_json(output / "plan.json", plan.model_dump())
        try:
            entity = sources.resolve_entity(plan)
        except Exception as error:
            entity = {"status": "unavailable", "reason": sources.safe_error(error)}
        manifest["entity"] = entity
        candidates, manifest["discovery"] = sources.discover(plan, manifest["sources"], entity)
        save_json(output / "candidates.json", candidates)
        decisions, manifest["assessment_call"] = model.assess(plan, candidates, entity, sources.request_json)
        save_json(output / "assessments.json", decisions)
        eligible = []
        for item in candidates:
            assessment = decisions.get(item["key"])
            reason = metadata_gate(plan, item, assessment)
            if reason:
                manifest["items"].append({**item, "status": "rejected_metadata", "reason": reason, "assessment": assessment})
            else:
                eligible.append({**item, "assessment": assessment})
        # Round-robin providers for variety; precision gates remain identical.
        grouped = [[c for c in eligible if c["source"] == source] for source in manifest["sources"]]
        ordered = [group[i] for i in range(max([len(g) for g in grouped], default=0)) for group in grouped if i < len(group)]
        previous, blocked = [], set()
        for item in ordered[:min(max(args.count * 4, 12), 40)]:
            if len(previous) >= args.count or time.monotonic() - started > 900:
                break
            if item["source"] in blocked:
                continue
            row = dict(item)
            print(f"Inspecting {item['key']}", flush=True)
            try:
                with tempfile.TemporaryDirectory(prefix="image-candidate-", dir=output.parent) as temporary:
                    folder = Path(temporary)
                    path = folder / "source.img"
                    if item["source"] == "artic":
                        time.sleep(1)
                    path.write_bytes(sources.fetch(item["image_url"], domains=sources.MEDIA_HOSTS[item["source"]], max_bytes=MAX_BYTES))
                    media = inspect_file(path)
                    media['catalogue_family'] = catalogue_family(item)
                    if is_duplicate(media, previous):
                        raise ValueError("Duplicate or near-duplicate image")
                    visual, call = model.inspect_visual(path, sources.request_json)
                    reason = visual_gate(plan, item["assessment"], visual)
                    row.update(visual=visual, visual_call=call)
                    if reason:
                        raise ValueError(reason)
                    ext = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}[media["format"]]
                    filename = "source." + ext
                    path.rename(folder / filename)
                    save_json(folder / "metadata.json", item)
                    save_json(folder / "verification.json", {"media": media, "visual": visual, "assessment": item["assessment"]})
                    destination = output / "images" / (item["source"] + "_" + item["id"])
                    destination.parent.mkdir(exist_ok=True)
                    shutil.move(str(folder), str(destination))
                    row.update(status="downloaded", path=str((destination / filename).relative_to(output)), media=media)
                    previous.append(media)
            except Exception as error:
                row.update(status="rejected_download_or_visual", reason=sources.safe_error(error))
                if isinstance(error, sources.Blocked):
                    blocked.add(item["source"])
            manifest["items"].append(row)
            report(output, manifest)
    except Exception as error:
        manifest["fatal_error"] = sources.safe_error(error)
    manifest["elapsed_seconds"] = round(time.monotonic() - started, 2)
    passed = report(output, manifest)
    print(json.dumps(manifest["summary"], ensure_ascii=False), flush=True)
    if manifest.get("fatal_error"):
        print(manifest["fatal_error"], flush=True)
    return passed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--description", default=os.environ.get("IMAGE_DESCRIPTION", ""))
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--sources", default="commons,met,artic,loc")
    parser.add_argument("--output", default="image-search-output/run")
    args = parser.parse_args()
    providers = args.sources.split(",")
    if not 1 <= args.count <= 20 or not 1 <= len(args.description.strip()) <= 2000:
        parser.error("Description 1-2000 characters; count 1-20")
    if not providers or len(set(providers)) != len(providers) or set(providers) - set(sources.PROVIDERS):
        parser.error("Choose unique sources from commons,met,artic,loc")
    output = Path(args.output).resolve()
    if not output.is_relative_to(ROOT / "image-search-output") or output == ROOT / "image-search-output":
        parser.error("Output must be a new child of image-search-output/")
    output.mkdir(parents=True, exist_ok=False)
    return 0 if execute(args, output) else 1


if __name__ == "__main__":
    raise SystemExit(main())
