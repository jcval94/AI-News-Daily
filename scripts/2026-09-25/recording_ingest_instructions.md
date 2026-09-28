# Recording ingest — 2026-09-25

## Regla principal

No renombres por contenido libre. Usa siempre el take_id exacto del Recording Pack.

Formato: <take_id>__r<NN>__<label>.<ext>

Ejemplos:

- opening_t01__r01__camA.mov
- opening_t01__r02__camA.mov
- opening_t01__r01__audio.wav

## Retakes

- Empieza en r01.
- Si repites una toma completa, incrementa r02, r03, etc.
- No borres una toma anterior porque parezca peor.
- El ingest escoge sólo un candidato técnico provisional; WhisperX/alignment decidirá después si otra toma respeta mejor el guion.

## Audio

- Mantén el scratch audio de cámara ENCENDIDO aunque uses lavalier.
- El scratch audio permite timestamps relativos al video y waveform sync automático en Resolve.
- Si tienes lavalier/mic externo, usa el mismo take_id y retake con audio.wav, lav.wav, etc.
- Un take sin audio embebido sano y sin audio externo pareado no queda listo para alignment.

## Carpeta recomendada

recordings/2026-09-25/inbox

Los archivos crudos permanecen fuera de Git. El scanner sólo lee, nunca mueve ni borra.

## Comando futuro

python -m pipeline.recording_ingest --target-date 2026-09-25 --input-dir "/ruta/a/recordings" --enforce
