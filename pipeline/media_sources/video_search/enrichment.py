"""Source captions, clearly labelled ASR, and genuine YouTube replay heatmaps."""
from __future__ import annotations

import html
import json
import math
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from pipeline.media_sources.video_search.providers import safe_error


def allowed_caption_url(url):
    p = urllib.parse.urlsplit(url)
    host = p.hostname or ""
    domains = ("youtube.com", "googlevideo.com", "google.com", "archive.org")
    if p.scheme != "https" or p.username or p.password or p.port not in (None, 443):
        raise ValueError("Unsupported caption URL")
    if not any(host == d or host.endswith("." + d) for d in domains):
        raise ValueError("Unsupported caption host")


class CaptionRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        allowed_caption_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_caption(url):
    allowed_caption_url(url)
    with urllib.request.build_opener(CaptionRedirect).open(url, timeout=30) as response:
        data = response.read(5 * 1024 * 1024 + 1)
    if len(data) > 5 * 1024 * 1024:
        raise ValueError("Caption file exceeds 5 MiB")
    return data.decode("utf-8-sig")


def clock(value):
    parts = value.replace(",", ".").split(":")
    return sum(float(p) * 60 ** i for i, p in enumerate(reversed(parts)))


def validate_segments(rows):
    result = []
    for row in rows:
        start, end = float(row["start"]), float(row["end"])
        text = html.unescape(re.sub(r"<[^>]*>", "", str(row["text"]))).strip()
        if not all(math.isfinite(v) for v in (start, end)) or not 0 <= start < end:
            raise ValueError("Invalid transcript timestamps")
        if text:
            result.append({"start": round(start, 3), "end": round(end, 3), "text": text})
    return sorted(result, key=lambda row: (row["start"], row["end"]))


def parse_captions(raw, ext):
    rows = []
    if ext == "json3":
        for event in json.loads(raw).get("events", []):
            text = "".join(s.get("utf8", "") for s in event.get("segs", []))
            if text.strip() and event.get("dDurationMs", 0) > 0:
                start = float(event["tStartMs"]) / 1000
                rows.append({"start": start, "end": start + float(event["dDurationMs"]) / 1000, "text": text})
    else:
        for block in re.split(r"\n\s*\n", raw.replace("\r\n", "\n")):
            lines = block.splitlines()
            for index, line in enumerate(lines):
                match = re.match(r"\s*([\d:.,]+)\s+-->\s+([\d:.,]+)", line)
                if match:
                    rows.append({"start": clock(match[1]), "end": clock(match[2]),
                                 "text": " ".join(lines[index + 1:])})
                    break
    return validate_segments(rows)


def plain_transcript(segments):
    words, previous = [], None
    for segment in segments:
        current = segment["text"].split()
        overlap = 0
        if previous and segment["start"] < previous["end"]:
            for n in range(min(30, len(words), len(current)), 0, -1):
                if words[-n:] == current[:n]:
                    overlap = n
                    break
        words.extend(current[overlap:])
        previous = segment
    return " ".join(words)


def caption_options(raw):
    for field, kind in (("subtitles", "publisher_captions"), ("automatic_captions", "platform_auto_captions")):
        tracks = raw.get(field) or {}
        languages = sorted(tracks, key=lambda lang: (not lang.startswith("es"), not lang.startswith("en"), lang))
        for language in languages:
            for ext in ("json3", "vtt", "srt"):
                options = [v for v in tracks[language] if v.get("ext") == ext and v.get("url")]
                if options:
                    yield {"url": options[0]["url"], "ext": ext, "language": language, "method": kind}
                    break
    for caption in raw.get("archive_captions", []):
        yield {**caption, "method": "archive_captions", "language": "unspecified"}


def transcribe_audio(media_path, folder, command):
    key = os.environ.get("OPENAI_API_KEY", "")
    if not key:
        raise RuntimeError("OPENAI_API_KEY missing for audio transcription")
    audio = folder / "transcription-input.mp3"
    try:
        command(["ffmpeg", "-nostdin", "-v", "error", "-i", str(media_path), "-vn", "-ac", "1",
                 "-ar", "16000", "-b:a", "48k", "-y", str(audio)], timeout=90)
        if audio.stat().st_size > 24 * 1024 * 1024:
            raise ValueError("Transcription audio exceeds upload budget")
        boundary = "videoexperiment" + uuid.uuid4().hex
        body = bytearray()
        for name, value in (("model", "whisper-1"), ("response_format", "verbose_json"),
                            ("timestamp_granularities[]", "segment"), ("temperature", "0")):
            body.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
        body.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="audio.mp3"\r\nContent-Type: audio/mpeg\r\n\r\n'.encode())
        body.extend(audio.read_bytes())
        body.extend(f"\r\n--{boundary}--\r\n".encode())
        request = urllib.request.Request("https://api.openai.com/v1/audio/transcriptions", data=bytes(body), headers={
            "Authorization": f"Bearer {key}", "Content-Type": f"multipart/form-data; boundary={boundary}"})
        with urllib.request.urlopen(request, timeout=180) as response:
            payload = json.loads(response.read(8 * 1024 * 1024))
        rows = [v for v in payload.get("segments", []) if float(v.get("no_speech_prob", 0)) < .8]
        return validate_segments(rows), payload.get("language", "unknown")
    finally:
        audio.unlink(missing_ok=True)


def transcript(media_path, folder, raw, media, mode, setting, command):
    result = {"status": "unavailable", "method": None, "segments": [], "text": "", "attempts": []}
    if setting == "off":
        result.update(status="disabled", reason="Transcription disabled by input")
        return result
    # At most two source tracks. Authentication/rate challenges stop source attempts.
    for option in list(caption_options(raw))[:2]:
        try:
            content = fetch_caption(option["url"])
            segments = parse_captions(content, option["ext"])
            if not segments:
                raise ValueError("Caption file contains no timed text")
            (folder / ("captions." + option["ext"])).write_text(content, encoding="utf-8")
            result.update(status="available", method=option["method"], language=option["language"],
                          scope="full_source", segments=segments, text=plain_transcript(segments))
            return result
        except Exception as error:
            result["attempts"].append({"method": option["method"], "error": safe_error(error)})
            if isinstance(error, urllib.error.HTTPError) and error.code in (401, 403, 429):
                break
    if setting == "auto" and media.get("audio_codec"):
        try:
            segments, language = transcribe_audio(media_path, folder, command)
            duration = media["duration_seconds"]
            if any(s["end"] > duration + 2 for s in segments):
                raise ValueError("Generated transcript timestamps exceed downloaded media")
            result.update(status="available" if segments else "unavailable", method="generated_asr",
                          model="whisper-1", language=language,
                          scope="downloaded_clip" if mode == "clip" else "full_downloaded_video",
                          segments=segments, text=plain_transcript(segments),
                          note="Generated from audio; may contain recognition errors. Not publisher captions.")
            if not segments:
                result["reason"] = "No speech recognized"
        except Exception as error:
            result.update(status="failed", reason=safe_error(error))
    else:
        result["reason"] = "No published captions or no audio stream; ASR not applicable/enabled"
    return result


def replay_data(raw, source):
    result = {"status": "unavailable", "provider": "youtube", "scope": "original_full_video",
              "unit": "relative_replay_intensity", "bins": []}
    if source != "youtube":
        result.update(status="not_applicable", reason="This provider does not expose YouTube Most Replayed data")
        return result
    if not raw.get("heatmap"):
        result["reason"] = "YouTube did not expose a replay heatmap to the extractor"
        return result
    bins = []
    try:
        for row in raw["heatmap"]:
            start, end, value = (float(row[k]) for k in ("start_time", "end_time", "value"))
            if not all(math.isfinite(v) for v in (start, end, value)) or not (0 <= start < end and 0 <= value <= 1):
                raise ValueError("Invalid replay bin")
            bins.append({"start_time": start, "end_time": end, "value": value})
        bins.sort(key=lambda b: b["start_time"])
        if len(bins) > 10000 or any(a["end_time"] > b["start_time"] + .01 for a, b in zip(bins, bins[1:])):
            raise ValueError("Overlapping or excessive replay bins")
        result.update(status="available", bins=bins,
                      peaks=sorted(bins, key=lambda b: b["value"], reverse=True)[:5])
    except (ValueError, TypeError, KeyError) as error:
        result.update(status="invalid", reason=str(error))
    return result


def plot_replay(data, path):
    bins = data["bins"]
    maximum = max((b["end_time"] for b in bins), default=1) or 1
    points = " ".join(f"{40 + 920 * (b['start_time'] + b['end_time']) / (2 * maximum):.2f},{180 - 140 * b['value']:.2f}" for b in bins)
    path.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 220"><rect width="1000" height="220" fill="white"/><text x="40" y="24">YouTube Most Replayed — published relative intensity</text><polyline fill="none" stroke="#5144ad" stroke-width="2" points="' + points + '"/><text x="40" y="208">Original video, 0–' + str(round(maximum, 1)) + ' seconds</text></svg>', encoding="utf-8")


def enrich(media_path, folder, raw, media, source, mode, setting, command):
    text = transcript(media_path, folder, raw, media, mode, setting, command)
    replay = replay_data(raw, source)
    if replay["status"] == "available":
        try:
            plot_replay(replay, folder / "most_replayed.svg")
            replay["graph_file"] = "most_replayed.svg"
        except Exception as error:
            replay["graph_error"] = safe_error(error)
    (folder / "transcript.json").write_text(json.dumps(text, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if text["status"] == "available":
        (folder / "transcript.txt").write_text(text["text"] + "\n", encoding="utf-8")
    (folder / "most_replayed.json").write_text(json.dumps(replay, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"transcript": {k: v for k, v in text.items() if k not in ("text", "segments")},
            "most_replayed": {k: v for k, v in replay.items() if k not in ("bins", "peaks")}}
