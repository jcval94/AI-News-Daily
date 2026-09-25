# Local Editing Harness — Windows 11 + DaVinci Resolve

Esta sección define la frontera entre el repositorio canónico y la workstation local de edición.

## Diseño

El harness no es un segundo pipeline. Envuelve módulos existentes y resuelve rutas Windows, instalación real de Resolve, FFmpeg/ffprobe, GPU, disco, recordings privados y ejecución local.

```text
repo / contratos portables
        ↓
pipeline.local doctor
        ↓
local_environment + local_capabilities
        ↓
local_job.json
        ↓
allowlist + root sandbox + dry-run
        ↓
local_receipt.json
        ↓
Resolve / FFmpeg / WhisperX
```

El repositorio conserva la verdad editorial. Resolve es el host de ejecución local.

## Por qué no hay daemon, HTTP local o MCP executor en P0

Para una sola Zenbook, un servicio permanente añade lifecycle, puertos y superficie de seguridad. P0 usa CLI + PowerShell + jobs declarativos + receipts. Un MCP futuro podrá crear jobs y leer receipts, pero no recibirá shell arbitrario.

## Primer uso

```powershell
.\scripts\local\bootstrap.ps1
.\scripts\local\doctor.ps1 -Deep
```

Después abre DaVinci Resolve:

```powershell
.\scripts\local\doctor.ps1 -Resolve -Deep
```

Y para el acceptance OTIO real:

```powershell
.\scripts\local\doctor.ps1 -Resolve -Deep -OtioSmoke
```

El smoke usa el proyecto aislado `__AI_NEWS_LOCAL_ACCEPTANCE__`; no toca proyectos de episodios.

## Config privada

`.local/local_config.json` se crea desde `config/local/local_config.example.json` y está fuera de Git.

Roots lógicos:

- `repo`
- `recordings`
- `work`
- `cache`
- `previews`

Los jobs no almacenan rutas absolutas. Ejemplo:

```json
{
  "root_id": "recordings",
  "relative_path": "2026-09-25/inbox"
}
```

Puedes mover media de C: a D: cambiando sólo la config privada.

## Operaciones allowlisted

```powershell
.\.venv\Scripts\python.exe -m pipeline.local operations
```

P0 implementa `media.scan`, `recording.ingest`, `recording.transcribe`, `recording.align`, `resolve.sync_audio`, `timeline.build`, `timeline.validate`, `resolve.import_timeline` y `preview.render`.

Planeadas: `proxy.generate`, `captions.burn_or_track`, `audio.normalize`, `aligned_timeline.build`.

## Jobs

Valida:

```powershell
.\.venv\Scripts\python.exe -m pipeline.local validate-job config\local\local_job.example.json
```

Dry-run:

```powershell
.\scripts\local\run_job.ps1 -Job config\local\local_job.example.json
```

Ejecuta:

```powershell
.\scripts\local\run_job.ps1 -Job config\local\local_job.example.json -Execute
```

`-Execute` autoriza al runner. Las operaciones Resolve además requieren `mode=execute` dentro del job.

## Seguridad

El executor usa `subprocess.run([...], shell=False)`, rechaza parámetros desconocidos, no acepta command/cwd/env arbitrarios, bloquea traversal/rutas absolutas, usa roots allowlisted, no borra raw media, evita overwrite por default, bloquea jobs duplicados por `job_id` y redacta roots en logs/receipts.

Estado privado: `.local/`, `recordings/`, `local_cache/`, `local_exports/`, `.venv-whisperx/`.

## Resolve

No se considera suficiente “tener Resolve instalado”. El doctor prueba discovery del SDK, conexión, ProjectManager, AutoSyncAudio y opcionalmente un import OTIO real + SaveProject.

Referencia oficial: https://www.blackmagicdesign.com/products/davinciresolve

## WhisperX

Permanece opcional y fuera del lock del core. No se asume CUDA por el nombre Zenbook S16. El doctor registra `nvidia-smi` cuando existe; configura CPU/GPU sólo con hardware confirmado.

Referencia: https://github.com/m-bain/whisperX

## WSL2

No es el runtime principal. Resolve es Windows-native y mezclar filesystems complica path mapping y debugging. La ruta principal es Windows Python + PowerShell + Resolve.

## Acceptance

```powershell
.\scripts\local\acceptance.ps1 -Tier P0
.\scripts\local\acceptance.ps1 -Tier P0 -Resolve
```

P1 se usa con media real.

## Qué sigue

P1: acceptance con un episodio real. P2: aligned timeline, proxies, captions y audio normalization. P3: MCP delgado para jobs/receipts, nunca shell.
