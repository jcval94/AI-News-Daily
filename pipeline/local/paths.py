from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path, PureWindowsPath
from typing import Any

_WINDOWS_ABS_RE = re.compile(r'''(?i)(?<![\w])(?:[a-z]:\\|\\\\)[^\r\n"']+''')


def looks_absolute(value: str) -> bool:
    text = str(value or "")
    return Path(text).is_absolute() or PureWindowsPath(text).is_absolute() or text.startswith("\\\\")


@dataclass(frozen=True)
class RootMap:
    repo: Path
    recordings: Path
    work: Path
    cache: Path
    previews: Path
    allowed_roots: frozenset[str] = field(
        default_factory=lambda: frozenset(
            {"repo", "recordings", "work", "cache", "previews"}
        )
    )

    @classmethod
    def from_config(cls, config: dict[str, Any], *, repo_root: Path) -> "RootMap":
        paths = config["paths"]

        def resolve(value: str) -> Path:
            if value == "auto":
                return repo_root.resolve()
            candidate = Path(value).expanduser()
            return candidate.resolve() if candidate.is_absolute() else (repo_root / candidate).resolve()

        allowed = frozenset(
            str(item)
            for item in config.get("security", {}).get(
                "allowed_roots",
                ["repo", "recordings", "work", "cache", "previews"],
            )
        )
        return cls(
            repo=repo_root.resolve(),
            recordings=resolve(str(paths["recordings_root"])),
            work=resolve(str(paths["work_root"])),
            cache=resolve(str(paths["cache_root"])),
            previews=resolve(str(paths["preview_root"])),
            allowed_roots=allowed,
        )

    def as_dict(self) -> dict[str, Path]:
        return {
            "repo": self.repo,
            "recordings": self.recordings,
            "work": self.work,
            "cache": self.cache,
            "previews": self.previews,
        }

    def root(self, root_id: str) -> Path:
        roots = self.as_dict()
        if root_id not in roots:
            raise ValueError(f"Unknown local root_id: {root_id}")
        if root_id not in self.allowed_roots:
            raise PermissionError(f"Local root_id is not allowed by policy: {root_id}")
        return roots[root_id]

    def resolve_ref(
        self,
        ref: dict[str, Any],
        *,
        must_exist: bool = False,
        expect_dir: bool | None = None,
    ) -> Path:
        root_id = str(ref.get("root_id", "") or "")
        relative = str(ref.get("relative_path", "") or "")
        if not root_id or not relative:
            raise ValueError("Path reference requires root_id and relative_path")
        if looks_absolute(relative):
            raise ValueError("Path reference relative_path must not be absolute")
        root = self.root(root_id).resolve()
        candidate = (root / relative).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"Path reference escapes root {root_id!r}: {relative!r}") from exc
        if must_exist and not candidate.exists():
            raise FileNotFoundError(f"Local path does not exist: {root_id}:{relative}")
        if expect_dir is True and candidate.exists() and not candidate.is_dir():
            raise ValueError(f"Expected directory: {root_id}:{relative}")
        if expect_dir is False and candidate.exists() and not candidate.is_file():
            raise ValueError(f"Expected file: {root_id}:{relative}")
        return candidate

    def redact(self, value: str) -> str:
        text = str(value)
        replacements = sorted(
            ((str(path), f"<ROOT:{root_id}>") for root_id, path in self.as_dict().items()),
            key=lambda item: len(item[0]),
            reverse=True,
        )
        for raw, token in replacements:
            text = text.replace(raw, token)
            text = text.replace(raw.replace("\\", "/"), token)
        home = str(Path.home())
        text = text.replace(home, "<HOME>")
        text = text.replace(home.replace("\\", "/"), "<HOME>")
        return _WINDOWS_ABS_RE.sub("<ABSOLUTE_WINDOWS_PATH>", text)
