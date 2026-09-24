# Independent rare-media stress test

Twelve frozen targets, each tested independently for images and videos (24 cases).
Run only on manual dispatch or an intentional change to `live-request.json` on
`experiment/youtube-artifacts`. No production imports, schedule, or promotion.

Each case requests one exact asset. Images use Commons, Met, Art Institute and
Library of Congress; videos search YouTube and Internet Archive. Videos are full,
with short known durations preferred, and transcription explicitly **off**.
The usual media size/duration/decoding and source-access gates remain enforced.

`cases.json` fixes the intended referent, descriptions, reference sources and
literal evidence groups before running. The references disambiguate the target;
they are not necessarily media providers. For people, a named source photograph
is required; identity is never inferred from faces. For events, generic places,
vehicles, birds or portraits of participants do not prove an event depiction.
An explanatory video specifically about the event qualifies; a brief incidental
mention in a general programme does not. Generated images do not qualify.

Artifacts include media (if retrieved), discovery candidates, rejections, source
metadata, integrity hashes and `benchmark.json`. Literal matching cannot measure
precision: it excludes queries and model reasons, but still requires human source
review. `exact_success` remains null until that review. An empty retrieval is a
failure to satisfy the user's target, even if a negative test completed normally.
A green benchmark workflow means completed evaluation, not 100% successful retrieval.
Do not substitute easier topics after a failure.

Reproduce one case:

```bash
python -m experiments.media_stress.run --case toyota-war --modality images
python -m experiments.media_stress.run --case toyota-war --modality videos
```

Outputs must be new directories. GitHub artifacts are retained for seven days;
committed results retain run IDs, source URLs and review evidence afterward.
