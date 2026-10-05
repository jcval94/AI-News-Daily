# Local Harness Acceptance Checklist

## Comando recomendado

P0 de workstation:

~~~powershell
.\scripts\local\acceptance.ps1 -Tier P0
~~~

P0 incluyendo DaVinci Resolve real + OTIO nativo:

~~~powershell
.\scripts\local\acceptance.ps1 -Tier P0 -Resolve
~~~

P1 de un episodio real:

~~~powershell
.\scripts\local\acceptance.ps1 -Tier P1 -Resolve -TargetDate YYYY-MM-DD
~~~

Cada ejecución escribe `.local/acceptance.latest.json`. Ese archivo es la evidencia local durable y separa repo, workstation, Resolve y media P1. `not_run` nunca cuenta como `pass`; P1 con operaciones faltantes queda `partial`.


Esta checklist valida la workstation real sin confundir CI con aceptación local.

## P0 — Toolchain y frontera de confianza

Objetivo: demostrar que Windows puede ejecutar el harness de forma segura antes de tocar media real.

1. Bootstrap:

~~~powershell
.\scripts\local\bootstrap.ps1
~~~

2. Diagnóstico profundo sin Resolve:

~~~powershell
.\scripts\local\doctor.ps1 -Deep
~~~

3. Snapshot de toolchain:

~~~powershell
.\scripts\local\toolchain.ps1
~~~

4. Tests locales:

~~~powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests\local -v
~~~

Criterios de salida:

- Python core >= 3.12;
- FFmpeg y ffprobe disponibles;
- OpenTimelineIO round-trip pasa;
- no hay paths absolutos persistidos;
- no hay shell arbitrario;
- staging sólo acepta requests tracked + committed + clean;
- la ejecución real exige staging + mode=execute + -Execute;
- receipt v2 conserva source Git commit + request SHA-256.

## P0-Resolve — API y OTIO nativo

Abre DaVinci Resolve y ejecuta:

~~~powershell
.\scripts\local\doctor.ps1 -Resolve -Deep -OtioSmoke
~~~

Criterios de salida:

- DaVinciResolveScript importable;
- Resolve reachable;
- ProjectManager disponible;
- AutoSyncAudio API detectable;
- OTIO nativo se importa en __AI_NEWS_LOCAL_ACCEPTANCE__;
- SaveProject funciona.

No uses un proyecto de episodio para esta prueba.

## P1 — Episodio real

Usa un episodio aprobado con Recording Pack. El cierre de P1 requiere receipts v2 exitosos y con provenance válida para:

- recording.ingest;
- recording.transcribe;
- recording.align;
- resolve.sync_audio;
- timeline.validate;
- resolve.import_timeline.


1. Copia media a un root privado configurado en recordings.
2. Crea y commitea un request en local_handoff/requests/.
3. Stage:

~~~powershell
.\scripts\local\stage_request.ps1 -Request local_handoff\requests\<request>.json
~~~

4. Inspecciona:

~~~powershell
.\scripts\local\status.ps1
~~~

5. Dry-run:

~~~powershell
.\scripts\local\run_staged.ps1 -JobId <job_id>
~~~

6. Ejecuta explícitamente:

~~~powershell
.\scripts\local\run_staged.ps1 -JobId <job_id> -Execute
~~~

Criterios de salida:

- Recording Ingest Manifest completo;
- ningún raw media entra a Git;
- receipt v2 existe y encadena commit SHA + request SHA-256;
- cualquier Resolve side effect ocurre en proyecto/timeline nuevo;
- no hay overwrite silencioso;
- si una capacidad no se puede verificar, falla cerrado.

## P2 — Edición automatizada

Sólo después de P1:

- aligned_timeline.build;
- proxies si el hardware real lo requiere;
- captions;
- audio normalization;
- reemplazo V1 por A-roll real;
- retiming V2 con timings reales;
- import del aligned OTIO en Resolve.

P2 no debe convertir MCP/Computer Use en shell executor. El harness determinista sigue siendo la autoridad de side effects.
