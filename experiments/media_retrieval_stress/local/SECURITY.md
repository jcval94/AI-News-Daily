# Local worker security and privacy boundary

The workstation worker has more power than a cloud retriever, so the trust boundary is explicit.

## Rules

1. Job JSON is data, never executable instructions.
2. No job field may contain shell fragments or arbitrary command arguments.
3. Subprocesses are invoked with argument arrays and `shell=False`.
4. Browser cookies, profiles and authentication tokens remain local.
5. Cookie exports are never written into the repository.
6. A logged-in browser session may improve discovery but **does not change rights status**.
7. No DRM, paywall, access-control or licensing bypass is part of this design.
8. `reference_only`, `review_required` and `blocked` sources are not automatically downloaded.
9. Large binaries are stored outside the repository under `AI_NEWS_MEDIA_LAB_HOME`.
10. Git receives hashes, metadata, scene intervals and provenance—not the media vault itself.

## Why this matters

A page may be technically downloadable while still being unsuitable for automated reuse.
The local worker treats **technical accessibility** and **production eligibility** as separate facts.
