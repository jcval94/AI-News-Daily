from __future__ import annotations

import importlib
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ResolveDiscovery:
    api_root: Path | None
    module_dir: Path | None
    script_lib: Path | None
    readme: Path | None


def _first_existing(paths: list[Path]) -> Path | None:
    for path in paths:
        try:
            if path.exists():
                return path.resolve()
        except OSError:
            continue
    return None


def discover_resolve(config: dict[str, Any]) -> ResolveDiscovery:
    cfg = config.get("resolve", {})
    api_candidates: list[Path] = []
    lib_candidates: list[Path] = []

    if cfg.get("api_root"):
        api_candidates.append(Path(str(cfg["api_root"])).expanduser())
    if os.environ.get("RESOLVE_SCRIPT_API"):
        api_candidates.append(Path(os.environ["RESOLVE_SCRIPT_API"]))
    program_data = Path(os.environ.get("PROGRAMDATA", r"C:\\ProgramData"))
    api_candidates.append(
        program_data / "Blackmagic Design" / "DaVinci Resolve" / "Support" / "Developer" / "Scripting"
    )
    api_root = _first_existing(api_candidates)
    module_dir = _first_existing([api_root / "Modules"]) if api_root else None

    if cfg.get("script_lib"):
        lib_candidates.append(Path(str(cfg["script_lib"])).expanduser())
    if os.environ.get("RESOLVE_SCRIPT_LIB"):
        lib_candidates.append(Path(os.environ["RESOLVE_SCRIPT_LIB"]))
    program_files = Path(os.environ.get("ProgramFiles", r"C:\\Program Files"))
    lib_candidates.append(
        program_files / "Blackmagic Design" / "DaVinci Resolve" / "fusionscript.dll"
    )
    script_lib = _first_existing(lib_candidates)
    readme = (
        _first_existing([api_root / "README.txt", api_root.parent / "README.txt", api_root / "README.md"])
        if api_root else None
    )
    return ResolveDiscovery(api_root, module_dir, script_lib, readme)


def load_resolve_module(config: dict[str, Any]) -> tuple[Any, ResolveDiscovery]:
    discovery = discover_resolve(config)
    try:
        return importlib.import_module("DaVinciResolveScript"), discovery
    except ImportError:
        pass
    if discovery.api_root is None or discovery.module_dir is None:
        raise RuntimeError(
            "DaVinci Resolve scripting SDK was not discovered. Open Resolve and check its "
            "installed Developer/Scripting README, or set resolve.api_root in .local/local_config.json."
        )
    module_file = discovery.module_dir / "DaVinciResolveScript.py"
    if not module_file.is_file():
        raise RuntimeError("DaVinciResolveScript.py was not found in the discovered SDK")
    os.environ["RESOLVE_SCRIPT_API"] = str(discovery.api_root)
    if discovery.script_lib:
        os.environ["RESOLVE_SCRIPT_LIB"] = str(discovery.script_lib)
    if str(discovery.module_dir) not in sys.path:
        sys.path.insert(0, str(discovery.module_dir))
    try:
        return importlib.import_module("DaVinciResolveScript"), discovery
    except ImportError as exc:
        raise RuntimeError("Could not import DaVinciResolveScript") from exc


def probe_connected_resolve(resolve: Any) -> dict[str, Any]:
    if not resolve:
        raise RuntimeError("Resolve scripting returned no application object")
    version = None
    for attr in ("GetVersionString", "GetVersion"):
        fn = getattr(resolve, attr, None)
        if callable(fn):
            try:
                version = fn()
                break
            except Exception:
                pass
    manager = resolve.GetProjectManager() if hasattr(resolve, "GetProjectManager") else None
    if not manager:
        raise RuntimeError("Resolve ProjectManager is unavailable")
    return {
        "connected": True,
        "version": str(version) if version is not None else "unknown",
        "project_manager": True,
        "audio_sync_api": bool(
            hasattr(resolve, "AUDIO_SYNC_MODE") and hasattr(resolve, "AUDIO_SYNC_WAVEFORM")
        ),
    }


def connect_resolve(config: dict[str, Any]) -> tuple[Any, ResolveDiscovery]:
    module, discovery = load_resolve_module(config)
    resolve = module.scriptapp("Resolve")
    if not resolve:
        raise RuntimeError(
            "Resolve scripting API is installed but Resolve is not reachable. Open Resolve "
            "and enable local external scripting if the installed edition/version requires it."
        )
    return resolve, discovery
