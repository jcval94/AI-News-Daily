from __future__ import annotations

import argparse
import html
import json
import os
import re
import subprocess
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from pipeline.source_naming import is_supported_source, source_date


DATE_DIR_RE = re.compile(r"^20\d{2}-\d{2}-\d{2}$")
ACTION_RE = re.compile(r"(?m)^\s*-?\s*uses:\s*([^@\s]+)@([^\s#]+)")
PYTHON_RE = re.compile(r'requires-python\s*=\s*["\']([^"\']+)["\']')
PYTHON_VERSION_RE = re.compile(r'python-version:\s*["\']?([^"\'\s]+)')
SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
IMPORTANT_WORKFLOWS = (
    "CI",
    "Build AI News Video Kit",
    "Editorial Regression",
    "Editorial Review Hub",
)
REQUIRED_PATHS = (
    "README.md",
    "AGENTS.md",
    "pyproject.toml",
    "requirements.lock",
    ".github/workflows/ci.yml",
    ".github/workflows/build-video-kit.yml",
    ".github/workflows/editorial-regression.yml",
    ".github/workflows/editorial-review-hub.yml",
)


@dataclass(frozen=True)
class HealthCheck:
    id: str
    category: str
    status: str
    title: str
    summary: str
    detail: str = ""
    value: str = ""


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ""


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _days_between(as_of: date, value: date | None) -> int | None:
    return max(0, (as_of - value).days) if value is not None else None


def _date_text(value: date | None) -> str:
    return value.isoformat() if value is not None else "—"


def _age_text(days: int | None) -> str:
    if days is None:
        return "—"
    return "hoy" if days == 0 else f"{days} día{'s' if days != 1 else ''}"


def _parse_iso_date(value: str) -> date | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except (TypeError, ValueError):
        return None


def _severity(checks: Iterable[HealthCheck]) -> str:
    statuses = {check.status for check in checks}
    if "critical" in statuses:
        return "critical"
    if "warn" in statuses:
        return "attention"
    return "healthy"


def _required_files(root: Path) -> HealthCheck:
    missing = [path for path in REQUIRED_PATHS if not (root / path).is_file()]
    if missing:
        return HealthCheck(
            "required-files",
            "Estructura",
            "critical",
            "Contratos esenciales",
            f"Faltan {len(missing)} archivos requeridos.",
            ", ".join(missing),
            str(len(missing)),
        )
    return HealthCheck(
        "required-files",
        "Estructura",
        "ok",
        "Contratos esenciales",
        "README, AGENTS, lockfile y workflows principales están presentes.",
        value=str(len(REQUIRED_PATHS)),
    )


def _repository_size(root: Path, github: dict[str, Any]) -> HealthCheck:
    size_kb = github.get("repository", {}).get("size")
    if not isinstance(size_kb, int):
        total = 0
        try:
            for path in root.rglob("*"):
                if path.is_file() and ".git" not in path.parts:
                    total += path.stat().st_size
        except OSError:
            total = 0
        size_kb = round(total / 1024) if total else None
    if size_kb is None:
        return HealthCheck(
            "repo-size",
            "Higiene",
            "info",
            "Tamaño del repositorio",
            "No fue posible calcular el tamaño.",
        )
    size_mb = size_kb / 1024
    if size_mb >= 500:
        status = "critical"
        summary = "El repositorio es demasiado pesado para un flujo operativo sano."
    elif size_mb >= 100:
        status = "warn"
        summary = "El tamaño ya merece vigilancia para evitar checkouts y CI lentos."
    else:
        status = "ok"
        summary = "El repositorio se mantiene ligero."
    return HealthCheck(
        "repo-size",
        "Higiene",
        status,
        "Tamaño del repositorio",
        summary,
        value=f"{size_mb:.1f} MB",
    )


def _lock_and_ignore(root: Path) -> list[HealthCheck]:
    checks: list[HealthCheck] = []
    lock = root / "requirements.lock"
    checks.append(
        HealthCheck(
            "dependency-lock",
            "Dependencias",
            "ok" if lock.is_file() else "critical",
            "Dependencias reproducibles",
            "Existe requirements.lock." if lock.is_file() else "Falta requirements.lock.",
        )
    )
    ignore = _read_text(root / ".gitignore")
    wanted = {".env", ".pipeline-runs/"}
    missing = sorted(token for token in wanted if token not in ignore)
    checks.append(
        HealthCheck(
            "gitignore",
            "Higiene",
            "warn" if missing else "ok",
            "Archivos efímeros y secretos",
            (
                "Los patrones sensibles/efímeros principales están ignorados."
                if not missing
                else "Faltan exclusiones importantes en .gitignore."
            ),
            ", ".join(missing),
        )
    )
    return checks


def _dependency_automation(root: Path) -> HealthCheck:
    configured = any(
        path.is_file()
        for path in (
            root / ".github" / "dependabot.yml",
            root / ".github" / "dependabot.yaml",
            root / "renovate.json",
            root / ".github" / "renovate.json",
        )
    )
    return HealthCheck(
        "dependency-automation",
        "Dependencias",
        "ok" if configured else "warn",
        "Actualizaciones de dependencias",
        (
            "Hay un bot de actualización de dependencias configurado."
            if configured
            else "No se detectó Dependabot ni Renovate."
        ),
        (
            ""
            if configured
            else "Conviene automatizar PRs de actualización y dejar que CI valide el lockfile."
        ),
    )


def _python_contract(root: Path) -> HealthCheck:
    pyproject = _read_text(root / "pyproject.toml")
    ci = _read_text(root / ".github/workflows/ci.yml")
    declared_match = PYTHON_RE.search(pyproject)
    declared = declared_match.group(1) if declared_match else ""
    tested = sorted(set(PYTHON_VERSION_RE.findall(ci)))
    if declared.startswith(">=3.11") and tested == ["3.12"]:
        return HealthCheck(
            "python-contract",
            "CI",
            "warn",
            "Contrato de Python",
            "El paquete declara Python >=3.11, pero CI sólo prueba 3.12.",
            "Agrega 3.11 al matrix o estrecha requires-python si 3.11 ya no es un objetivo.",
            f"{declared} · CI {', '.join(tested)}",
        )
    if not tested:
        return HealthCheck(
            "python-contract",
            "CI",
            "warn",
            "Contrato de Python",
            "No pude detectar una versión de Python ejercitada por CI.",
            value=declared or "—",
        )
    return HealthCheck(
        "python-contract",
        "CI",
        "ok",
        "Contrato de Python",
        "La versión declarada y la cobertura visible de CI no muestran una contradicción obvia.",
        value=f"{declared or '—'} · CI {', '.join(tested)}",
    )


def _action_pinning(root: Path) -> HealthCheck:
    refs: list[str] = []
    workflows = root / ".github" / "workflows"
    if workflows.is_dir():
        for path in workflows.glob("*.yml"):
            for action, ref in ACTION_RE.findall(_read_text(path)):
                if action.startswith("./"):
                    continue
                if not SHA_RE.fullmatch(ref):
                    refs.append(f"{action}@{ref}")
    unique = sorted(set(refs))
    if unique:
        sample = ", ".join(unique[:6])
        extra = f" (+{len(unique) - 6} más)" if len(unique) > 6 else ""
        return HealthCheck(
            "action-pinning",
            "Seguridad",
            "warn",
            "Pinning de GitHub Actions",
            f"{len(unique)} Actions externas usan tags/branches mutables en vez de SHA inmutable.",
            sample + extra,
            str(len(unique)),
        )
    return HealthCheck(
        "action-pinning",
        "Seguridad",
        "ok",
        "Pinning de GitHub Actions",
        "Las Actions externas detectadas están fijadas por SHA.",
    )


def _editorial_regression_contract(root: Path) -> HealthCheck:
    workflow = _read_text(root / ".github/workflows/editorial-regression.yml")
    legacy_glob = "????-??-??.txt" in workflow
    semantic_resolution = (
        "source_naming" in workflow
        or "news_resolution" in workflow
        or "latest_repository_source_date" in workflow
    )
    if legacy_glob and not semantic_resolution:
        return HealthCheck(
            "regression-source-contract",
            "CI",
            "warn",
            "Frescura de Editorial Regression",
            "Editorial Regression aún resuelve la fecha con el patrón canónico YYYY-MM-DD.txt.",
            "Los digests timestamped YYYY-MM-DD-HH-MM-SS.txt pueden quedar fuera y hacer que la regresión corra con noticias viejas.",
        )
    return HealthCheck(
        "regression-source-contract",
        "CI",
        "ok",
        "Frescura de Editorial Regression",
        "La resolución de fuentes no depende únicamente del nombre canónico diario.",
    )


def _news_health(root: Path, as_of: date) -> tuple[list[HealthCheck], dict[str, Any]]:
    news_dir = root / "news"
    by_day: dict[date, list[str]] = {}
    if news_dir.is_dir():
        for path in news_dir.iterdir():
            if not is_supported_source(path):
                continue
            value = source_date(path)
            if value is not None:
                by_day.setdefault(value, []).append(path.name)
    latest = max(by_day) if by_day else None
    age = _days_between(as_of, latest)
    duplicates = {day: sorted(names) for day, names in by_day.items() if len(names) > 1}

    checks: list[HealthCheck] = []
    if latest is None:
        checks.append(
            HealthCheck(
                "news-freshness",
                "Operación",
                "critical",
                "Frescura de fuentes",
                "No hay fuentes de noticias fechadas utilizables.",
            )
        )
    else:
        if age is not None and age > 3:
            status = "critical"
            summary = "La ingesta diaria está claramente atrasada."
        elif age is not None and age > 1:
            status = "warn"
            summary = "La última fuente tiene más de un día de antigüedad."
        else:
            status = "ok"
            summary = "La ingesta de noticias está fresca."
        checks.append(
            HealthCheck(
                "news-freshness",
                "Operación",
                status,
                "Frescura de fuentes",
                summary,
                f"Última fecha detectada: {_date_text(latest)}.",
                _age_text(age),
            )
        )

    if duplicates:
        recent = sorted(duplicates, reverse=True)
        examples = "; ".join(
            f"{day.isoformat()}: {', '.join(duplicates[day])}" for day in recent[:3]
        )
        checks.append(
            HealthCheck(
                "duplicate-news-days",
                "Operación",
                "warn",
                "Fuentes duplicadas por día",
                f"{len(duplicates)} fecha(s) tienen más de una captura candidata.",
                examples,
                str(len(duplicates)),
            )
        )
    else:
        checks.append(
            HealthCheck(
                "duplicate-news-days",
                "Operación",
                "ok",
                "Fuentes duplicadas por día",
                "No se detectaron múltiples capturas para una misma fecha.",
                value="0",
            )
        )

    return checks, {
        "latest_news_date": latest.isoformat() if latest else None,
        "news_staleness_days": age,
        "duplicate_news_days": {
            day.isoformat(): names for day, names in sorted(duplicates.items())
        },
        "news_days": len(by_day),
    }


def _latest_episode(root: Path) -> tuple[date | None, dict[str, Any]]:
    scripts = root / "scripts"
    candidates: list[tuple[date, Path]] = []
    if scripts.is_dir():
        for path in scripts.iterdir():
            if not path.is_dir() or not DATE_DIR_RE.fullmatch(path.name):
                continue
            try:
                candidates.append((date.fromisoformat(path.name), path))
            except ValueError:
                continue
    if not candidates:
        return None, {}
    episode_date, episode_dir = max(candidates, key=lambda item: item[0])
    return episode_date, _read_json(episode_dir / "run_state.json", {})


def _production_health(root: Path, as_of: date) -> tuple[HealthCheck, dict[str, Any]]:
    episode_date, state = _latest_episode(root)
    age = _days_between(as_of, episode_date)
    status_value = str(state.get("status") or "unknown")
    publishable = bool(state.get("publishable"))

    if episode_date is None:
        check = HealthCheck(
            "production-freshness",
            "Operación",
            "critical",
            "Frescura de producción",
            "No existe ningún episodio canónico fechado en scripts/.",
        )
    elif age is not None and age > 10:
        check = HealthCheck(
            "production-freshness",
            "Operación",
            "critical",
            "Frescura de producción",
            "La producción canónica está muy atrasada respecto al calendario Tuesday/Friday.",
            f"Último episodio: {episode_date.isoformat()} · estado {status_value}.",
            _age_text(age),
        )
    elif age is not None and age > 5:
        check = HealthCheck(
            "production-freshness",
            "Operación",
            "warn",
            "Frescura de producción",
            "La producción canónica ya rebasa el margen esperado entre ejecuciones.",
            f"Último episodio: {episode_date.isoformat()} · estado {status_value}.",
            _age_text(age),
        )
    elif status_value != "approved" or not publishable:
        check = HealthCheck(
            "production-freshness",
            "Operación",
            "warn",
            "Frescura de producción",
            "El episodio canónico más reciente no aparece como aprobado/publicable.",
            f"Último episodio: {episode_date.isoformat()} · estado {status_value}.",
            _age_text(age),
        )
    else:
        check = HealthCheck(
            "production-freshness",
            "Operación",
            "ok",
            "Frescura de producción",
            "La producción canónica está dentro del margen esperado.",
            f"Último episodio: {episode_date.isoformat()} · estado {status_value}.",
            _age_text(age),
        )
    return check, {
        "latest_episode_date": episode_date.isoformat() if episode_date else None,
        "latest_episode_status": status_value,
        "latest_episode_publishable": publishable,
        "production_staleness_days": age,
    }


def _pages_health(pages_root: Path | None) -> tuple[HealthCheck, dict[str, Any]]:
    if pages_root is None:
        return (
            HealthCheck(
                "pages-history",
                "Pages",
                "info",
                "Catálogo de Pages",
                "No se proporcionó un árbol Pages para auditar.",
            ),
            {"pages_episode_count": None},
        )
    episodes_root = pages_root / "episodes"
    count = 0
    if episodes_root.is_dir():
        count = sum(
            1
            for path in episodes_root.iterdir()
            if path.is_dir() and (path / "index.html").is_file()
        )
    if not (pages_root / "index.html").is_file():
        status = "critical"
        summary = "Falta el catálogo raíz de Pages."
    elif count == 0:
        status = "critical"
        summary = "Pages no contiene episodios navegables."
    else:
        status = "ok"
        summary = f"Pages contiene {count} episodio(s) recuperado(s) y un catálogo raíz."
    return (
        HealthCheck(
            "pages-history",
            "Pages",
            status,
            "Catálogo de Pages",
            summary,
            value=str(count),
        ),
        {"pages_episode_count": count},
    )


def _gh_api(repository: str, endpoint: str) -> Any:
    if not repository:
        return None
    try:
        completed = subprocess.run(
            ["gh", "api", endpoint],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return json.loads(completed.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return None


def collect_github_snapshot(repository: str) -> dict[str, Any]:
    repo = _gh_api(repository, f"repos/{repository}")
    pulls = _gh_api(repository, f"repos/{repository}/pulls?state=open&per_page=100")
    issues = _gh_api(repository, f"repos/{repository}/issues?state=open&per_page=100")
    branch = repo.get("default_branch", "main") if isinstance(repo, dict) else "main"
    runs = _gh_api(
        repository,
        f"repos/{repository}/actions/runs?branch={branch}&status=completed&per_page=100",
    )
    return {
        "repository": repo if isinstance(repo, dict) else {},
        "pulls": pulls if isinstance(pulls, list) else [],
        "issues": [
            item
            for item in (issues if isinstance(issues, list) else [])
            if isinstance(item, dict) and "pull_request" not in item
        ],
        "workflow_runs": (
            runs.get("workflow_runs", []) if isinstance(runs, dict) else []
        ),
    }


def _workflow_checks(github: dict[str, Any]) -> list[HealthCheck]:
    runs = github.get("workflow_runs", [])
    if not isinstance(runs, list) or not runs:
        return [
            HealthCheck(
                "workflow-status",
                "Actions",
                "info",
                "Últimas ejecuciones",
                "No fue posible obtener historial de GitHub Actions.",
            )
        ]
    latest: dict[str, dict[str, Any]] = {}
    for raw in runs:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or "")
        if name and name not in latest:
            latest[name] = raw
    checks: list[HealthCheck] = []
    for workflow in IMPORTANT_WORKFLOWS:
        run = latest.get(workflow)
        if run is None:
            checks.append(
                HealthCheck(
                    f"workflow-{workflow.casefold().replace(' ', '-')}",
                    "Actions",
                    "warn",
                    workflow,
                    "No aparece una ejecución completada reciente en el snapshot.",
                )
            )
            continue
        conclusion = str(run.get("conclusion") or "unknown")
        when = str(run.get("updated_at") or run.get("created_at") or "")
        if conclusion == "success":
            status = "ok"
            summary = "La última ejecución completada terminó correctamente."
        elif conclusion in {"failure", "timed_out", "action_required"}:
            status = "critical" if workflow in {
                "CI",
                "Build AI News Video Kit",
                "Editorial Review Hub",
            } else "warn"
            summary = f"La última ejecución terminó en {conclusion}."
        else:
            status = "warn"
            summary = f"La última ejecución terminó en {conclusion}."
        checks.append(
            HealthCheck(
                f"workflow-{workflow.casefold().replace(' ', '-')}",
                "Actions",
                status,
                workflow,
                summary,
                when,
                conclusion,
            )
        )
    return checks


def _pull_request_health(github: dict[str, Any], as_of: date) -> tuple[HealthCheck, dict[str, Any]]:
    pulls = github.get("pulls", [])
    if not isinstance(pulls, list):
        pulls = []
    stale: list[str] = []
    drafts = 0
    for pr in pulls:
        if not isinstance(pr, dict):
            continue
        if pr.get("draft"):
            drafts += 1
            continue
        created = _parse_iso_date(str(pr.get("created_at") or ""))
        age = _days_between(as_of, created)
        if age is not None and age > 14:
            stale.append(f"#{pr.get('number')} · {age}d · {pr.get('title', '')}")
    if stale:
        check = HealthCheck(
            "open-prs",
            "Mantenimiento",
            "warn",
            "Pull requests abiertos",
            f"Hay {len(stale)} PR(s) no-draft con más de 14 días.",
            "; ".join(stale[:4]),
            str(len(pulls)),
        )
    else:
        check = HealthCheck(
            "open-prs",
            "Mantenimiento",
            "ok",
            "Pull requests abiertos",
            f"{len(pulls)} abierto(s), sin deuda no-draft >14 días.",
            f"Drafts: {drafts}",
            str(len(pulls)),
        )
    return check, {
        "open_pr_count": len(pulls),
        "draft_pr_count": drafts,
        "stale_pr_count": len(stale),
    }


def _issue_health(github: dict[str, Any]) -> tuple[HealthCheck, dict[str, Any]]:
    issues = github.get("issues", [])
    count = len(issues) if isinstance(issues, list) else 0
    return (
        HealthCheck(
            "open-issues",
            "Mantenimiento",
            "info",
            "Issues abiertos",
            f"{count} issue(s) abierto(s).",
            value=str(count),
        ),
        {"open_issue_count": count},
    )


def audit_repository(
    *,
    repo_root: Path,
    pages_root: Path | None = None,
    as_of: date | None = None,
    github_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    as_of = as_of or datetime.now(ZoneInfo("America/Mexico_City")).date()
    github = github_snapshot or {}
    checks: list[HealthCheck] = [
        _required_files(repo_root),
        _repository_size(repo_root, github),
        *_lock_and_ignore(repo_root),
        _dependency_automation(repo_root),
        _python_contract(repo_root),
        _action_pinning(repo_root),
        _editorial_regression_contract(repo_root),
    ]
    news_checks, news_metrics = _news_health(repo_root, as_of)
    checks.extend(news_checks)
    production_check, production_metrics = _production_health(repo_root, as_of)
    checks.append(production_check)
    pages_check, pages_metrics = _pages_health(pages_root)
    checks.append(pages_check)
    checks.extend(_workflow_checks(github))
    pr_check, pr_metrics = _pull_request_health(github, as_of)
    checks.append(pr_check)
    issue_check, issue_metrics = _issue_health(github)
    checks.append(issue_check)

    status_counts = {
        key: sum(1 for check in checks if check.status == key)
        for key in ("critical", "warn", "ok", "info")
    }
    metrics = {
        **news_metrics,
        **production_metrics,
        **pages_metrics,
        **pr_metrics,
        **issue_metrics,
        "repository_size_mb": (
            round(float(github.get("repository", {}).get("size", 0)) / 1024, 1)
            if github.get("repository", {}).get("size") is not None
            else None
        ),
    }
    return {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "as_of_date": as_of.isoformat(),
        "status": _severity(checks),
        "status_counts": status_counts,
        "metrics": metrics,
        "checks": [asdict(check) for check in checks],
    }


def _esc(value: Any) -> str:
    return html.escape(str(value if value is not None else "—"))


def _status_copy(status: str) -> tuple[str, str]:
    return {
        "healthy": ("SALUDABLE", "ok"),
        "attention": ("REQUIERE ATENCIÓN", "warn"),
        "critical": ("CRÍTICO", "critical"),
    }.get(status, (status.upper(), "info"))


def health_document(report: dict[str, Any]) -> str:
    label, status_class = _status_copy(str(report.get("status") or "unknown"))
    metrics = report.get("metrics", {}) if isinstance(report.get("metrics"), dict) else {}
    checks = report.get("checks", []) if isinstance(report.get("checks"), list) else []
    cards = []
    for check in checks:
        if not isinstance(check, dict):
            continue
        status = str(check.get("status") or "info")
        cards.append(
            '<article class="check-card" data-search-item>'
            f'<div class="check-top"><span class="status {status}">{_esc(status.upper())}</span>'
            f'<span class="category">{_esc(check.get("category"))}</span></div>'
            f'<h3>{_esc(check.get("title"))}</h3>'
            f'<p>{_esc(check.get("summary"))}</p>'
            + (
                f'<div class="detail">{_esc(check.get("detail"))}</div>'
                if check.get("detail")
                else ""
            )
            + (
                f'<strong class="value">{_esc(check.get("value"))}</strong>'
                if check.get("value")
                else ""
            )
            + '</article>'
        )

    critical = int(report.get("status_counts", {}).get("critical", 0) or 0)
    warns = int(report.get("status_counts", {}).get("warn", 0) or 0)
    latest_news = metrics.get("latest_news_date") or "—"
    latest_episode = metrics.get("latest_episode_date") or "—"
    open_prs = metrics.get("open_pr_count")
    pages_count = metrics.get("pages_episode_count")

    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark">
<title>AI News Daily · Salud del repo</title>
<style>
:root{{--bg:#080d13;--panel:#0f1823;--line:#233247;--text:#edf6ff;--muted:#8ea1b4;--ok:#56c596;--warn:#f2bd63;--critical:#ef6a6a;--accent:#67d9ff}}
*{{box-sizing:border-box}}html,body{{margin:0;background:var(--bg);color:var(--text);font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
body{{min-height:100vh}}.shell{{width:min(1180px,calc(100% - 32px));margin:0 auto;padding:28px 0 50px}}
.topbar{{display:flex;justify-content:space-between;align-items:center;gap:14px;margin-bottom:20px}}a{{color:#bdeaff;text-decoration:none}}.back{{padding:8px 11px;border:1px solid var(--line);border-radius:10px;background:#101a25}}
.hero{{border:1px solid var(--line);border-radius:22px;background:linear-gradient(145deg,#0d1721,#102234);padding:24px}}.eyebrow{{font-size:10px;text-transform:uppercase;letter-spacing:.12em;color:var(--accent);font-weight:850}}h1{{font-size:clamp(30px,5vw,55px);letter-spacing:-.04em;line-height:1;margin:9px 0 12px}}.hero p{{color:#b3c3d2;line-height:1.55;max-width:780px}}
.overall{{display:inline-flex;align-items:center;padding:7px 10px;border-radius:999px;font-size:11px;font-weight:900;letter-spacing:.05em}}.overall.ok{{background:#15382d;color:#a9efd2}}.overall.warn{{background:#3a2c16;color:#ffd993}}.overall.critical{{background:#421d20;color:#ffb1b1}}
.kpis{{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:9px;margin:14px 0 24px}}.kpi{{border:1px solid var(--line);border-radius:14px;background:var(--panel);padding:13px}}.kpi span{{display:block;color:var(--muted);font-size:9px;text-transform:uppercase;letter-spacing:.08em}}.kpi strong{{display:block;margin-top:7px;font-size:19px}}
.controls{{display:flex;gap:10px;align-items:center;margin:0 0 14px}}#healthSearch{{flex:1;border:1px solid var(--line);border-radius:11px;background:#0c141e;color:var(--text);padding:11px 12px;outline:none}}#healthSearch:focus{{border-color:#3e87a8;box-shadow:0 0 0 3px #16435b55}}
.checks{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}}.check-card{{position:relative;border:1px solid var(--line);border-radius:16px;background:var(--panel);padding:15px;min-height:170px}}.check-card[hidden]{{display:none}}.check-top{{display:flex;justify-content:space-between;gap:8px;align-items:center}}.status{{font-size:9px;font-weight:900;letter-spacing:.07em;padding:5px 7px;border-radius:999px}}.status.ok{{background:#15382d;color:#a9efd2}}.status.warn{{background:#3a2c16;color:#ffd993}}.status.critical{{background:#421d20;color:#ffb1b1}}.status.info{{background:#1a2b3b;color:#b5d9ee}}.category{{font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:.07em}}.check-card h3{{font-size:15px;margin:11px 0 7px}}.check-card p{{font-size:12px;color:#b4c2cf;line-height:1.5;margin:0}}.detail{{margin-top:10px;padding-top:9px;border-top:1px solid #263448;color:var(--muted);font-size:10px;line-height:1.45;overflow-wrap:anywhere}}.value{{display:block;margin-top:10px;font-size:18px}}.foot{{color:var(--muted);font-size:10px;margin-top:18px}}
@media(max-width:980px){{.kpis{{grid-template-columns:repeat(3,minmax(0,1fr))}}.checks{{grid-template-columns:repeat(2,minmax(0,1fr))}}}}@media(max-width:650px){{.shell{{width:min(100% - 20px,1180px)}}.topbar{{align-items:flex-start;flex-direction:column}}.kpis,.checks{{grid-template-columns:1fr}}}}
</style>
</head>
<body data-health-page="repo-health">
<main class="shell">
<div class="topbar"><div><span class="eyebrow">AI News Daily · Observabilidad</span></div><a class="back" href="../">← Episodios</a></div>
<section class="hero">
<span class="overall {status_class}">{_esc(label)}</span>
<h1>Salud del repositorio</h1>
<p>Una vista operativa y estructural: fuentes, producción, Actions, Pages, contratos, dependencias y deuda visible. El estado se construye desde archivos y señales reales del repositorio; no es una evaluación editorial del contenido.</p>
</section>
<section class="kpis">
<div class="kpi"><span>Críticos</span><strong>{critical}</strong></div>
<div class="kpi"><span>Advertencias</span><strong>{warns}</strong></div>
<div class="kpi"><span>Última fuente</span><strong>{_esc(latest_news)}</strong></div>
<div class="kpi"><span>Última producción</span><strong>{_esc(latest_episode)}</strong></div>
<div class="kpi"><span>PRs abiertos</span><strong>{_esc(open_prs)}</strong></div>
<div class="kpi"><span>Episodios en Pages</span><strong>{_esc(pages_count)}</strong></div>
</section>
<div class="controls"><input id="healthSearch" type="search" placeholder="Filtrar checks…" aria-label="Filtrar checks"></div>
<section class="checks">{''.join(cards)}</section>
<p class="foot">Snapshot al {_esc(report.get("as_of_date"))} · generado {_esc(report.get("generated_at_utc"))} · JSON: <a href="repo-health.json">repo-health.json</a></p>
</main>
<script>
const input=document.getElementById('healthSearch');
const cards=[...document.querySelectorAll('[data-search-item]')];
input.addEventListener('input',()=>{{
  const q=input.value.trim().toLocaleLowerCase('es');
  cards.forEach(card=>{{card.hidden=!!q&&!card.textContent.toLocaleLowerCase('es').includes(q);}});
}});
</script>
</body>
</html>
"""


def write_health_outputs(report: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "repo-health.json"
    html_path = output_dir / "index.html"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    html_path.write_text(health_document(report), encoding="utf-8")
    return json_path, html_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit repository health and build a Pages view")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--pages-root", default="")
    parser.add_argument("--repository", default=os.getenv("GITHUB_REPOSITORY", ""))
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--as-of", default="")
    parser.add_argument("--offline", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    as_of = date.fromisoformat(args.as_of) if args.as_of else None
    github = {} if args.offline else collect_github_snapshot(str(args.repository or ""))
    report = audit_repository(
        repo_root=Path(args.repo_root),
        pages_root=Path(args.pages_root) if args.pages_root else None,
        as_of=as_of,
        github_snapshot=github,
    )
    json_path, html_path = write_health_outputs(report, Path(args.output_dir))
    print(json.dumps({
        "status": report["status"],
        "json": str(json_path),
        "html": str(html_path),
        "counts": report["status_counts"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
