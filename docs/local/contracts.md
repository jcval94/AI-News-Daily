# Local Harness Contracts

Todos los contratos locales son JSON Schema versionados.

## local_config

`config/local/local_config.schema.json` valida `.local/local_config.json`. Define roots, executables, Resolve, WhisperX y seguridad. No contiene secretos.

## local_environment

`config/local/local_environment.schema.json` describe SO, Python, GPU hints y estado de Resolve sin persistir rutas absolutas.

## local_capabilities

`config/local/local_capabilities.schema.json` registra capacidades probadas en la workstation. Tool instalado no equivale a capability probada.

## local_job

`config/local/local_job.schema.json` sólo permite operaciones allowlisted. Los paths usan `root_id + relative_path`. La ejecución requiere doble consentimiento: `mode=execute` dentro del job y `--execute`/`-Execute` en el runner. Un job `mode=plan` nunca puede ser forzado a ejecutar desde CLI. Además, `run-job` es dry-run only: la ejecución real requiere una copia privada stageada y `run-staged --execute`. No existen campos shell/cwd/env.

## local_receipt

`config/local/local_receipt.schema.json` registra estado, timestamps, exit code, comando redactado y logs relativos. Un receipt existente impide repetir el mismo `job_id`.

## local_run_manifest

`config/local/local_run_manifest.schema.json` agrupa preflight, receipts y resultado de una futura ejecución multi-step.

## Autoridad

```text
script / alignment / OTIO canónico
        >
local config
        >
job
        >
receipt
        >
Resolve UI state
```

Resolve ejecuta contratos; no los sustituye.

## local_stage

`config/local/local_stage.schema.json` prueba que un request versionado fue aceptado localmente. Guarda source_repo_path + SHA-256 + staged_job_path. Un request del repo no debe ejecutarse directamente.

## local_toolchain

`config/local/local_toolchain.schema.json` captura versiones de Python/OpenTimelineIO/FFmpeg/ffprobe/WhisperX/Resolve sin persistir rutas absolutas.

## Repo/local trust boundary

~~~text
local_handoff/requests/   = propuesta versionada
.local/jobs/staged/       = aceptación privada + hash
.local/jobs/receipts/     = evidencia de ejecución
~~~

Git nunca es una cola autoejecutable.

## Caducidad y retries

`expires_at` es opcional en `local_job`. Si existe y ya venció, staging falla cerrado.

Las operaciones con efectos laterales —especialmente Resolve— no tienen retry automático. Para reintentar después de revisar el fallo, crea un nuevo `job_id`; el receipt del intento anterior permanece como evidencia.
