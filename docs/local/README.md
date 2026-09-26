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

La ejecución directa desde un JSON del repo está deshabilitada. `run_job.ps1` es sólo para validación/dry-run. Para ejecutar, el request debe entrar por `local_handoff/requests/`, pasar por staging privado y después usar `run_staged.ps1 -Execute`.

## Seguridad

El executor usa `subprocess.run([...], shell=False)`, rechaza parámetros desconocidos, no acepta command/cwd/env arbitrarios, bloquea traversal/rutas absolutas, usa roots allowlisted, no borra raw media, evita overwrite por default, bloquea jobs duplicados por `job_id` y redacta roots en logs/receipts. Si un root se elimina de `security.allowed_roots`, el resolver lo bloquea aunque siga siendo un tipo de root válido en el schema.

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

## Repo → local: staging obligatorio

Los requests que un agente o un commit coloque en local_handoff/requests/ son propuestas, no ejecución.

Primero:

~~~powershell
Copy-Item local_handoff\examples\example-ingest.json local_handoff\requests\my-ingest.json
.\scripts\local\stage_request.ps1 -Request local_handoff\requests\my-ingest.json
~~~

Después inspecciona:

~~~powershell
.\scripts\local\status.ps1
~~~

Dry-run del staged job:

~~~powershell
.\scripts\local\run_staged.ps1 -JobId request-ingest-20260925
~~~

Ejecución real:

~~~powershell
.\scripts\local\run_staged.ps1 -JobId request-ingest-20260925 -Execute
~~~

El staging guarda SHA-256. Si alguien modifica la copia privada después de aceptarla, run-staged falla cerrado.

## Toolchain snapshot

Para registrar versiones sin persistir rutas privadas:

~~~powershell
.\scripts\local\toolchain.ps1
.\scripts\local\toolchain.ps1 -Resolve
~~~

Salida: .local/toolchain.latest.json.

## Estado rápido

~~~powershell
.\scripts\local\status.ps1
~~~

Muestra preflight, requests disponibles, jobs staged y receipts sin abrir Resolve.
