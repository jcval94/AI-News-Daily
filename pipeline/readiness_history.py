from __future__ import annotations

import argparse
import html
import json
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any


ARTIFACT_PREFIX = "production-readiness-"


def _esc(value: Any) -> str:
    return html.escape(str(value if value is not None else "—"))


def _created_ts(value: str) -> float:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return 0.0


def collect_snapshots(root: Path) -> list[dict[str, Any]]:
    """Collect valid preflight snapshots, keeping the newest observation per target date."""
    by_target: dict[str, dict[str, Any]] = {}
    for path in root.rglob("production-readiness.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        target = str(payload.get("target_date") or "")
        try:
            datetime.strptime(target, "%Y-%m-%d")
        except ValueError:
            continue
        if not isinstance(payload.get("readiness_score"), (int, float)):
            continue
        previous = by_target.get(target)
        if previous is None or _created_ts(payload.get("generated_at_utc", "")) >= _created_ts(
            previous.get("generated_at_utc", "")
        ):
            by_target[target] = payload
    return sorted(by_target.values(), key=lambda row: str(row["target_date"]), reverse=True)


def build_report(root: Path) -> dict[str, Any]:
    rows = collect_snapshots(root)
    scores = [float(row.get("readiness_score", 0.0) or 0.0) for row in rows]
    source_scores = [
        float(row.get("source_quality", {}).get("score", 0.0) or 0.0)
        for row in rows
    ]
    ready_count = sum(1 for row in rows if row.get("status") == "ready")
    return {
        "schema_version": 1,
        "snapshot_count": len(rows),
        "ready_count": ready_count,
        "at_risk_count": len(rows) - ready_count,
        "average_readiness_score": round(mean(scores), 1) if scores else None,
        "average_source_quality_score": round(mean(source_scores), 1) if source_scores else None,
        "latest": rows[0] if rows else None,
        "snapshots": rows,
    }


def readiness_document(report: dict[str, Any]) -> str:
    rows = report.get("snapshots", []) if isinstance(report.get("snapshots"), list) else []
    latest = report.get("latest") if isinstance(report.get("latest"), dict) else {}
    latest_score = latest.get("readiness_score") if latest else None
    latest_status = str(latest.get("status") or "no-data") if latest else "no-data"

    cards = []
    table_rows = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        coverage = row.get("source_coverage", {}) if isinstance(row.get("source_coverage"), dict) else {}
        quality = row.get("source_quality", {}) if isinstance(row.get("source_quality"), dict) else {}
        score = float(row.get("readiness_score", 0.0) or 0.0)
        width = max(0.0, min(100.0, score))
        target = str(row.get("target_date") or "")
        status = str(row.get("status") or "unknown")
        missing = ", ".join(str(v) for v in coverage.get("missing_dates", [])) or "ninguna"
        unparseable = ", ".join(str(v) for v in coverage.get("unparseable_dates", [])) or "ninguna"
        cards.append(
            '<article class="snapshot">'
            f'<div class="snapshot-top"><strong>{_esc(target)}</strong><span class="pill { _esc(status) }">{_esc(status.upper())}</span></div>'
            f'<div class="score">{score:.1f}<small>/100</small></div>'
            f'<div class="bar"><i style="width:{width:.1f}%"></i></div>'
            f'<p>Cobertura parseable: <b>{float(coverage.get("coverage_ratio", 0.0) or 0.0):.0%}</b> · '
            f'calidad de fuentes: <b>{float(quality.get("score", 0.0) or 0.0):.0f}/100</b></p>'
            f'<small>Faltantes: {_esc(missing)} · No parseables: {_esc(unparseable)}</small>'
            '</article>'
        )
        table_rows.append(
            '<tr>'
            f'<td>{_esc(target)}</td>'
            f'<td>{score:.1f}</td>'
            f'<td>{float(coverage.get("coverage_ratio", 0.0) or 0.0):.0%}</td>'
            f'<td>{float(quality.get("score", 0.0) or 0.0):.0f}</td>'
            f'<td>{_esc(status)}</td>'
            '</tr>'
        )

    empty = (
        '<div class="empty">Todavía no hay snapshots programados. El histórico aparecerá tras el primer Production Preflight.</div>'
        if not cards
        else ""
    )
    latest_text = "—" if latest_score is None else f"{float(latest_score):.1f}/100"

    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark">
<title>Production Readiness · AI News Daily</title>
<style>
:root{{--bg:#080d13;--panel:#0f1823;--line:#233247;--text:#edf6ff;--muted:#8ea1b4;--accent:#67d9ff;--ok:#56c596;--warn:#f2bd63}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
main{{width:min(1180px,calc(100% - 32px));margin:auto;padding:30px 0 60px}}a{{color:#bdeaff;text-decoration:none}}
.hero{{border:1px solid var(--line);border-radius:22px;background:linear-gradient(145deg,#0d1721,#102234);padding:24px}}.eyebrow{{font-size:10px;text-transform:uppercase;letter-spacing:.12em;color:var(--accent);font-weight:850}}h1{{font-size:clamp(32px,5vw,58px);letter-spacing:-.04em;line-height:1;margin:9px 0 12px}}.hero p{{color:#b3c3d2;line-height:1.55;max-width:820px}}
.kpis{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:14px 0 24px}}.kpi,.snapshot{{border:1px solid var(--line);border-radius:15px;background:var(--panel);padding:15px}}.kpi span{{display:block;color:var(--muted);font-size:9px;text-transform:uppercase;letter-spacing:.08em}}.kpi strong{{display:block;margin-top:6px;font-size:22px}}
.grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}}.snapshot-top{{display:flex;justify-content:space-between;gap:10px}}.pill{{font-size:9px;font-weight:850;padding:5px 8px;border-radius:999px;background:#1a2b3b;color:#b5d9ee}}.pill.ready{{background:#15382d;color:#a9efd2}}.pill.at_risk{{background:#3a2c16;color:#ffd993}}.score{{font-size:34px;font-weight:850;margin:14px 0 5px}}.score small{{font-size:12px;color:var(--muted)}}.bar{{height:8px;background:#091018;border-radius:99px;overflow:hidden}}.bar i{{display:block;height:100%;background:linear-gradient(90deg,#3288ac,#6edaff);border-radius:99px}}.snapshot p,.snapshot small{{color:#a9bac9;font-size:11px;line-height:1.55}}
.panel{{margin-top:24px;border:1px solid var(--line);border-radius:16px;background:var(--panel);padding:16px;overflow:auto}}table{{width:100%;border-collapse:collapse;font-size:11px}}th,td{{text-align:left;padding:9px;border-bottom:1px solid #1c2a39}}th{{color:var(--muted);font-size:9px;text-transform:uppercase;letter-spacing:.08em}}.empty{{border:1px dashed var(--line);border-radius:15px;padding:22px;color:var(--muted);margin-top:18px}}
.foot{{margin-top:20px;color:var(--muted);font-size:10px}}@media(max-width:760px){{.kpis,.grid{{grid-template-columns:1fr}}}}
</style>
</head>
<body data-readiness-page="production-readiness">
<main>
<section class="hero"><span class="eyebrow">AI News Daily · Preflight histórico</span><h1>Production Readiness</h1><p>Señal anticipada de la corrida siguiente. Combina cobertura parseable, calidad observacional de las fuentes, disponibilidad de Narrative Memory y presencia de la credencial obligatoria. El preflight no llama modelos ni modifica estado productivo.</p></section>
<section class="kpis">
<div class="kpi"><span>Último readiness</span><strong>{_esc(latest_text)}</strong></div>
<div class="kpi"><span>Último estado</span><strong>{_esc(latest_status)}</strong></div>
<div class="kpi"><span>Snapshots</span><strong>{_esc(report.get("snapshot_count"))}</strong></div>
<div class="kpi"><span>Promedio</span><strong>{_esc(report.get("average_readiness_score"))}</strong></div>
</section>
{empty}
<section class="grid">{"".join(cards)}</section>
<section class="panel"><span class="eyebrow">Histórico</span><table><thead><tr><th>Producción</th><th>Readiness</th><th>Cobertura</th><th>Source quality</th><th>Estado</th></tr></thead><tbody>{"".join(table_rows) if table_rows else '<tr><td colspan="5">Sin datos todavía.</td></tr>'}</tbody></table></section>
<p class="foot">Source quality es telemetría observacional y no es un hard gate. JSON: <a href="production-readiness-history.json">production-readiness-history.json</a>.</p>
</main>
</body>
</html>
"""


def _github_artifacts(repository: str) -> list[dict[str, Any]]:
    completed = subprocess.run(
        ["gh", "api", f"repos/{repository}/actions/artifacts?per_page=100"],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    payload = json.loads(completed.stdout)
    rows = payload.get("artifacts", []) if isinstance(payload, dict) else []
    return [row for row in rows if isinstance(row, dict)]


def recover_preflight_artifacts(
    *,
    repository: str,
    output_root: Path,
    max_artifacts: int = 20,
) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    candidates = [
        row
        for row in _github_artifacts(repository)
        if str(row.get("name") or "").startswith(ARTIFACT_PREFIX)
        and not bool(row.get("expired"))
    ]
    candidates.sort(key=lambda row: _created_ts(row.get("created_at", "")), reverse=True)
    diagnostics = []
    for position, row in enumerate(candidates[: max(1, max_artifacts)]):
        run = row.get("workflow_run") if isinstance(row.get("workflow_run"), dict) else {}
        run_id = run.get("id")
        name = str(row.get("name") or "")
        if not run_id or not name:
            continue
        destination = output_root / f"{position:02d}-{run_id}"
        destination.mkdir(parents=True, exist_ok=True)
        completed = subprocess.run(
            ["gh", "run", "download", str(run_id), "--name", name, "--dir", str(destination)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        diagnostics.append(
            {
                "name": name,
                "run_id": run_id,
                "status": "downloaded" if completed.returncode == 0 else "download_failed",
            }
        )
    return {"candidate_count": len(candidates), "downloads": diagnostics}


def build_dashboard(*, input_root: Path, output_dir: Path) -> tuple[Path, Path]:
    report = build_report(input_root)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "production-readiness-history.json"
    html_path = output_dir / "index.html"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    html_path.write_text(readiness_document(report), encoding="utf-8")
    return json_path, html_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build historical Production Readiness dashboard")
    parser.add_argument("--input-root", default="")
    parser.add_argument("--repository", default="")
    parser.add_argument("--download-root", default=".preflight-history")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--max-artifacts", type=int, default=20)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_root = Path(args.input_root) if args.input_root else Path(args.download_root)
    if args.repository:
        if input_root.exists():
            shutil.rmtree(input_root)
        recover_preflight_artifacts(
            repository=args.repository,
            output_root=input_root,
            max_artifacts=args.max_artifacts,
        )
    json_path, html_path = build_dashboard(input_root=input_root, output_dir=Path(args.output_dir))
    print(json.dumps({"json": str(json_path), "html": str(html_path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
