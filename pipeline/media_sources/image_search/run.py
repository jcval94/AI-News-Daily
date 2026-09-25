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

from pipeline.media_sources.image_search import model, sources


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


def inspect_file(path, *, min_short=200, min_long=600):
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
            if min(im.size) < min_short or max(im.size) < min_long:
                raise ValueError(f"Image below minimum useful resolution ({min_short}/{min_long} px)")
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
