# Local Harness Contracts

Todos los contratos locales son JSON Schema versionados.

## local_config

`config/local/local_config.schema.json` valida `.local/local_config.json`. Define roots, executables, Resolve, WhisperX y seguridad. No contiene secretos.

## local_environment

`config/local/local_environment.schema.json` describe SO, Python, GPU hints y estado de Resolve sin persistir rutas absolutas.

## local_capabilities

`config/local/local_capabilities.schema.json` registra capacidades probadas en la workstation. Tool instalado no equivale a capability probada.

## local_job

`config/local/local_job.schema.json` sólo permite operaciones allowlisted. Los paths usan `root_id + relative_path`. La ejecución requiere doble consentimiento: `mode=execute` dentro del job y `--execute`/`-Execute` en el runner. Un job `mode=plan` nunca puede ser forzado a ejecutar desde CLI. No existen campos shell/cwd/env.

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
