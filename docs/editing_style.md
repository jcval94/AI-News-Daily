# Editing Style — JC Reflective Video Essay

`config/editing_style.yaml` is the deterministic audiovisual grammar for the channel.

It exists to prevent a common failure mode in automated editing: an agent can suggest individually plausible cuts that collectively produce an incoherent, over-edited video. The style file sets stable defaults and measurable boundaries while leaving room for explicit creative exceptions.

## External principles used

The initial grammar is deliberately conservative and draws from established guidance rather than creator folklore:

- YouTube's audience-retention tooling treats the first 30 seconds as a distinct intro window and recommends testing opening styles while ensuring the opening matches the promise of title/thumbnail.
- Adobe describes the straight cut as the most common transition and recommends limiting visible transitions, keeping them consistent, and using them purposefully.
- Adobe's B-roll guidance treats B-roll as material that supports the principal footage/story and can cover edits, not as generic filler.
- Adobe's J/L-cut guidance emphasizes audio continuity as a way to keep scene changes flowing without conspicuous visual effects.
- Blackmagic's official Resolve training is used as the implementation compatibility target for documentary/interview workflows, without making the grammar Resolve-specific.

The source URLs are versioned inside `editing_style.yaml`.

## Channel-specific decisions

Some rules are **our design choices**, not universal facts:

- the presenter is the visual home base;
- the presenter should appear within the first six seconds;
- the opening may become visually dense after that human anchor;
- the normal transition is a hard cut;
- visible transitions are rare;
- relevant evidence beats generic polished stock;
- reflective/emotional passages prefer the presenter;
- the entire essay should not inherit the fast-cut grammar of the cold open.

These choices fit a presenter-led reflective essay format and can change later from actual retention data.

## Policy layers

The style has three jobs.

### 1. Defaults

When the multimedia planner does not explicitly specify a transition or treatment, `edit_manifest.json` receives the role-specific default from `editing_style.yaml`.

Examples:

- evidence image → `highlight_crop`
- evidence video → `natural_motion`
- historical mirror → slower visual treatment
- rhythm → short video-first cuts
- presenter → `clean_a_roll`

### 2. Lint

Every generated edit manifest receives `style_warnings[]`. Current checks include:

- presenter appears too late in the opening;
- B-roll/media runs continuously for too long;
- presenter remains uninterrupted beyond the attention-reset target;
- media duration falls outside its visual-role range;
- unknown visual roles;
- transitions outside the allow-list;
- excessive visible-transition density;
- presenter visual share outside the target range.

### 3. Learning

The initial enforcement mode is `observe`, not blocking.

This is intentional. We do not yet have enough published-channel retention data to claim that a specific number such as 45 seconds of uninterrupted presenter or 55% presenter share is causally optimal. The first versions should record violations and outcomes. Hard gates should be introduced only after repeated evidence across multiple videos.

## Cold open

The first 30 seconds are treated as a measurement window, following YouTube's retention model.

Our current production grammar is:

1. establish the presenter early;
2. earn attention with the hook, not an effect;
3. allow a denser visual montage through roughly the first 20 seconds;
4. use short, specific moving shots;
5. return to normal essay grammar after the opening.

The deterministic multimedia fallback now preserves the first opening slot for the presenter and keeps the remaining opening opportunities available for media.

## Authority

`script.txt` remains the editorial/factual authority.

`editing_style.yaml` controls audiovisual defaults and lint only. It may not change narration, invent evidence, or make an unverified image appear to be documentary proof.

## Future calibration

After several published videos, update numeric values using:

- 30-second intro retention;
- audience-retention dips and spikes;
- presenter visual share;
- average media duration;
- longest continuous B-roll/media run.

Do not tune the grammar to one anomalous video.
