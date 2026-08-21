# Editorial calibration policy

The pipeline separates **measurement** from **enforcement**. Voice dimensions (`voice_fidelity`, `intellectual_depth`, `human_relevance`, `analogy_quality`) remain visible in every run, but no deterministic floor is activated until the human-labelled corpus is balanced enough to estimate false accepts and false rejects.

Minimum evidence before changing the gate or judge-model mix:

- at least 5 full scripts reviewed by a human;
- at least 2 human-publishable scripts;
- at least 2 human-rejected scripts.

Until then:

- do not invent per-dimension thresholds;
- do not switch a judge to a stronger/different model merely because all judges currently share one model;
- use `pipeline.editorial_calibration` to monitor judge↔human agreement and judge-pair approval agreement.

The first baseline consists of three real 2026-08-21 E2E runs. All were human-rejected. This is useful evidence of false-accept tendencies (especially SEO/Attention), but it cannot estimate the cost of rejecting a genuinely good essay.
