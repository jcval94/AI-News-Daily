# Local handoff

This directory is the only committed ingress for local workstation requests.

Rules:

- Git/repo may propose JSON jobs under local_handoff/requests/.
- A request must be tracked, committed and clean before staging; even then it is never trusted as executable state.
- The Windows user stages a request into .local/jobs/staged/.
- Staging records SHA-256 and source repo path.
- Execution requires both job mode=execute and a local --execute / -Execute action.
- Receipts and raw media remain private under .local/ and recordings/.

Normal flow:

~~~text
repo request
  -> stage-request
  -> private staged copy + SHA-256
  -> dry-run
  -> explicit local execute
  -> receipt
~~~

Never place passwords, tokens, absolute machine paths, or raw media here.


## P1 request kit

Para un episodio real no copies templates manualmente uno por uno. Genera el set completo:

~~~powershell
.\scripts\local\prepare_p1_requests.ps1 -TargetDate YYYY-MM-DD
~~~

Se crean seis requests ordenados bajo `local_handoff/requests/`:

1. recording.ingest
2. recording.transcribe
3. recording.align
4. resolve.sync_audio
5. timeline.validate
6. resolve.import_timeline

El generador valida schemas, pero no hace commit, staging ni ejecución. Esa separación es deliberada: primero revisa el diff y crea un commit Git; sólo entonces `stage_request.ps1` puede aceptar cada request.
