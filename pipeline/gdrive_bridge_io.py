"""Shared, deterministic Drive discovery and verified same-file moves.

This module never creates files, changes permissions or publishes content.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from typing import Any

import requests

SHEET_MIME = "application/vnd.google-apps.spreadsheet"
FILE_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,200}")


@dataclass(frozen=True)
class Lane:
    workflow: str
    sheet_pattern: str
    raw_prefix: str = ""


LANES = {
    "daily": Lane("gdrive-raw-bridge-probe.yml", r"__bridge_inbox_AI-News-Daily__\d{4}-\d{2}-\d{2}_\d{6}", "ai-news-daily.news."),
    "weekly": Lane("gdrive-weekly-research-bridge.yml", r"__bridge_inbox_AI-News-Daily__research-weekly__\d{4}-\d{2}-\d{2}_\d{6}"),
    "narrative": Lane("gdrive-narrative-memory-bridge.yml", r"__bridge_inbox_AI-News-Daily__narrative-memory__\d{4}-\d{2}-\d{2}_\d{6}"),
}


def require_id(value: str) -> str:
    if not FILE_ID_RE.fullmatch(value):
        raise ValueError("Invalid Drive file/folder identifier")
    return value


class Drive:
    def __init__(self, token: str, session: Any = None):
        if not token:
            raise ValueError("Missing Drive access token")
        self.session = session if session is not None else requests.Session()
        self.headers = {"Authorization": f"Bearer {token}"}

    def list_inbox(self, folder: str) -> list[dict[str, Any]]:
        require_id(folder)
        files: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        seen_tokens: set[str] = set()
        page_token = ""
        for _ in range(1000):
            params = {
                "q": f"'{folder}' in parents and trashed=false",
                "fields": "nextPageToken,incompleteSearch,files(id,name,createdTime,parents,mimeType)",
                "pageSize": 100,
                "orderBy": "createdTime asc",
                "supportsAllDrives": "true",
                "includeItemsFromAllDrives": "true",
            }
            if page_token:
                params["pageToken"] = page_token
            response = self.session.get("https://www.googleapis.com/drive/v3/files", headers=self.headers, params=params, timeout=30)
            response.raise_for_status()
            body = response.json()
            if body.get("incompleteSearch"):
                raise ValueError("Drive discovery incomplete; refusing to report an empty inbox")
            if not isinstance(body.get("files"), list):
                raise ValueError("Malformed Drive file listing")
            for item in body["files"]:
                require_id(str(item.get("id") or ""))
                if item["id"] not in seen_ids:
                    seen_ids.add(item["id"])
                    files.append(item)
            page_token = body.get("nextPageToken") or ""
            if not page_token:
                return files
            if not isinstance(page_token, str) or page_token in seen_tokens:
                raise ValueError("Invalid or repeated Drive pagination token")
            seen_tokens.add(page_token)
        raise ValueError("Drive discovery exceeded page budget; no partial result accepted")

    def metadata(self, file_id: str) -> dict[str, Any]:
        require_id(file_id)
        response = self.session.get(f"https://www.googleapis.com/drive/v3/files/{file_id}", headers=self.headers, params={"fields": "id,name,parents,trashed", "supportsAllDrives": "true"}, timeout=30)
        response.raise_for_status()
        body = response.json()
        if body.get("id") != file_id or body.get("trashed"):
            raise ValueError("Drive metadata identity/trashed mismatch")
        return body

    def move_verified(self, file_id: str, source: str, destination: str, expected_name: str, outcome: str) -> dict[str, Any]:
        for value in (file_id, source, destination):
            require_id(value)
        if outcome not in {"processed", "failed"} or source == destination:
            raise ValueError("Invalid move contract")
        final_name = outcome + "__" + expected_name
        before = self.metadata(file_id)
        if before.get("parents") == [destination] and before.get("name") == final_name:
            return before
        if before.get("parents") != [source] or before.get("name") != expected_name:
            raise ValueError("Drive move precondition mismatch: expected same file/name and sole inbox parent")
        response = self.session.patch(f"https://www.googleapis.com/drive/v3/files/{file_id}", headers=self.headers,
            params={"addParents": destination, "removeParents": source, "fields": "id,name,parents", "supportsAllDrives": "true"},
            json={"name": final_name}, timeout=30)
        response.raise_for_status()
        # HTTP success is insufficient: fresh read of the same file is mandatory.
        after = self.metadata(file_id)
        if after.get("parents") != [destination] or after.get("name") != final_name:
            raise ValueError("Drive move readback mismatch: destination/name not confirmed")
        return after


def candidates(files: list[dict[str, Any]], lane: str) -> list[dict[str, Any]]:
    contract = LANES[lane]
    eligible = []
    for item in files:
        name = str(item.get("name") or "")
        mime = item.get("mimeType")
        kind = ""
        if mime == SHEET_MIME and re.fullmatch(contract.sheet_pattern, name):
            kind = "sheet"
        elif contract.raw_prefix and mime == "text/plain" and name.startswith(contract.raw_prefix) and "\n" not in name and "\r" not in name:
            kind = "raw"
        if kind:
            eligible.append({**item, "file_kind": kind})
    return sorted(eligible, key=lambda f: (str(f.get("createdTime") or ""), f["file_kind"] != "sheet", f["id"]))


def select(files: list[dict[str, Any]], lane: str, requested_id: str = "") -> dict[str, Any] | None:
    if requested_id:
        require_id(requested_id)
    pending = candidates(files, lane)
    return next((f for f in pending if not requested_id or f["id"] == requested_id), None)


def write_outputs(values: dict[str, str]) -> None:
    path = os.getenv("GITHUB_OUTPUT")
    for key, value in values.items():
        if "\n" in value or "\r" in value:
            raise ValueError("Unsafe multiline workflow output")
    if path:
        with open(path, "a", encoding="utf-8") as out:
            for key, value in values.items():
                out.write(f"{key}={value}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["select", "move"])
    parser.add_argument("--lane", choices=LANES)
    parser.add_argument("--outcome", choices=["processed", "failed"])
    args = parser.parse_args()
    drive = Drive(os.environ["ACCESS_TOKEN"])
    inbox = os.environ["INBOX_FOLDER_ID"]
    if args.operation == "select":
        if not args.lane:
            parser.error("select requires --lane")
        item = select(drive.list_inbox(inbox), args.lane, os.getenv("REQUESTED_FILE_ID", ""))
        write_outputs({"file_id": item["id"] if item else "", "file_name": item["name"] if item else "", "file_kind": item["file_kind"] if item else ""})
        print(json.dumps({"lane": args.lane, "status": "selected" if item else "idle", "file_id": item["id"] if item else None}))
    else:
        if not args.outcome:
            parser.error("move requires --outcome")
        result = drive.move_verified(os.environ["FILE_ID"], inbox, os.environ[args.outcome.upper() + "_FOLDER_ID"], os.environ["FILE_NAME"], args.outcome)
        print(json.dumps({"status": "verified_" + args.outcome, "file_id": result["id"], "parents": result["parents"]}))


if __name__ == "__main__":
    main()
