# Prompt — siguiente conversación

Quiero continuar el proyecto `jcval94/AI-News-Daily` desde la sección del **Local Editing Harness**.

Contexto ya implementado:

- Windows 11 es el runtime local primario.
- DaVinci Resolve es el host de postproducción.
- Existe `pipeline/local/` con doctor/preflight, toolchain, status, root sandbox, jobs allowlisted, staging y receipts.
- `local_handoff/requests/` es la única entrada versionada repo → local.
- Un request debe estar tracked + committed + clean antes de staging.
- La ejecución real sólo puede ocurrir desde una copia privada stageada y requiere doble consentimiento: `mode=execute` + `-Execute`.
- El staging fija SHA-256 y Git commit.
- El receipt v2 debe conservar esa provenance.
- No existe shell arbitrario, daemon HTTP ni MCP executor de bajo nivel.
- Raw recordings, cache y estado de máquina están fuera de Git.
- CI prueba el harness en Linux y Windows; DaVinci Resolve real se valida únicamente en la workstation.
- Recording Ingest, WhisperX adapter, Recording Alignment, Resolve Alignment Bridge, Virtual Timeline, OTIO, placeholders y pre-recording preview ya existen.

Mi máquina real es una ASUS Zenbook S16 con Windows 11 y DaVinci Resolve instalado. **No asumas CPU/GPU/RAM ni edición/versión de Resolve: descúbrelos en local.**

Objetivo de esta conversación:

1. Audita primero `docs/local/README.md`, `docs/local/contracts.md` y `docs/local/acceptance.md`.
2. Ejecuta el acceptance P0 real de la workstation:
   - bootstrap;
   - doctor -Deep;
   - toolchain;
   - tests/local;
   - doctor -Resolve -Deep -OtioSmoke con Resolve abierto.
3. Reporta el hardware/toolchain detectado: Windows, Python, FFmpeg/ffprobe, GPU/CUDA si existe, Resolve/API, OTIO y espacio de disco.
4. Decide **con evidencia del equipo real** si WhisperX conviene con GPU, CPU o un entorno Python separado. No instales un stack CUDA pesado si el hardware no lo justifica.
5. Corrige únicamente problemas reales encontrados por el acceptance; no reescribas el harness por gusto.
6. Después ejecuta un P1 controlado usando un episodio aprobado y media de prueba/real si está disponible:
   `recording.ingest → recording.transcribe → recording.align → resolve.sync_audio → timeline.validate/import`.
7. Mantén todo fail-closed:
   - no borrar raw media;
   - no sobreescribir proyectos/timelines existentes;
   - no persistir paths absolutos;
   - no ejecutar requests directamente desde Git;
   - no crear una primitive shell genérica.
8. Si P0/P1 queda verde, diseña e implementa como siguiente prioridad `aligned_timeline.build`: reemplazar V1 placeholders por retakes reales, reconstruir duración real, retemporizar V2 y generar un aligned OTIO nuevo para Resolve.
9. Actualiza tests, docs y arquitectura sólo según evidencia real.
10. Al final separa claramente:
    - probado en CI;
    - probado en la Zenbook real;
    - probado dentro de Resolve real;
    - todavía no probado.

No me preguntes por información que puedas detectar con el harness. Haz cambios directamente en el repo cuando estén justificados.
