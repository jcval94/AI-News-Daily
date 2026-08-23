from __future__ import annotations

from pathlib import Path

from pipeline.review_hub_v2 import build_site as _build_site_v2
from pipeline.review_hub_v2 import parse_args


def _replace_once(document: str, needle: str, replacement: str, *, label: str) -> str:
    if needle not in document:
        raise RuntimeError(f"Review Hub v3 could not find expected {label} marker")
    return document.replace(needle, replacement, 1)


def upgrade_document(document: str) -> str:
    """Apply UX, accessibility, and delivery-safe enhancements to the v2 static page."""

    viewport = '<meta name="viewport" content="width=device-width, initial-scale=1">'
    document = _replace_once(
        document,
        viewport,
        viewport
        + '\n<meta name="description" content="AI News Daily editorial review hub for reviewing scripts, evidence, diagnostics and multimedia.">'
        + '\n<meta name="theme-color" content="#090c12">'
        + '\n<meta name="color-scheme" content="dark">',
        label="viewport meta",
    )

    progressive_css = r"""
/* v3: UX/accessibility/performance hardening layered over the stable v2 renderer. */
.skip-link{position:fixed;left:12px;top:12px;z-index:1000;padding:10px 14px;border-radius:10px;background:var(--accent);color:#07121a!important;font-weight:850;transform:translateY(-160%);transition:transform .16s ease;text-decoration:none!important}.skip-link:focus{transform:translateY(0)}
:where(a,input,summary):focus-visible{outline:3px solid var(--accent);outline-offset:3px}
section[id]{scroll-margin-top:116px}
.script{max-height:none;overflow:visible}
details.diagnostic>summary{display:flex;align-items:center;justify-content:space-between;gap:14px;min-height:52px}details.diagnostic>summary::after{content:'＋';font-size:20px;color:var(--accent);line-height:1}details.diagnostic[open]>summary::after{content:'−'}
.media-card{content-visibility:auto;contain-intrinsic-size:360px}.media-card video{cursor:pointer}
@media(max-width:700px){
  .search-dock{position:static;backdrop-filter:none}
  .quick-nav{flex-wrap:nowrap;overflow-x:auto;overscroll-behavior-x:contain;padding-bottom:5px;scrollbar-width:thin}
  .quick-nav a{flex:0 0 auto;display:inline-flex;align-items:center;min-height:36px;white-space:nowrap}
  .hero-actions{display:grid;grid-template-columns:1fr;gap:8px}
  .button{display:flex;align-items:center;justify-content:center;min-height:44px;margin:0}
  .script{padding:18px;font-size:16.5px;line-height:1.78}
  .table-wrap{overscroll-behavior-x:contain;-webkit-overflow-scrolling:touch}
  table{min-width:720px}
  section[id]{scroll-margin-top:12px}
}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}.skip-link{transition:none}}
"""
    document = _replace_once(
        document,
        "</style>",
        progressive_css + "\n</style>",
        label="style close",
    )

    document = _replace_once(
        document,
        '<body><main class="wrap">',
        '<body><a class="skip-link" href="#guion">Saltar al guion</a><main class="wrap">',
        label="body/main",
    )

    document = document.replace("preload='metadata'", "preload='none'")
    document = document.replace("loading='lazy'", "loading='lazy' decoding='async'")
    document = document.replace("target='_blank'><img", "target='_blank' rel='noreferrer'><img")

    document = _replace_once(
        document,
        'id="globalSearch" type="search" autocomplete="off"',
        'id="globalSearch" type="search" autocomplete="off" enterkeyhint="search"',
        label="global search input",
    )
    document = _replace_once(
        document,
        '<span id="searchCount" class="search-count">',
        '<span id="searchCount" class="search-count" aria-live="polite">',
        label="search count",
    )
    return document


def build_site(
    *,
    episode_dir: Path,
    media_dir: Path,
    media_zip: Path,
    regression_path: Path,
    cases_path: Path,
    output_dir: Path,
    run_id: str,
) -> Path:
    index_path = _build_site_v2(
        episode_dir=episode_dir,
        media_dir=media_dir,
        media_zip=media_zip,
        regression_path=regression_path,
        cases_path=cases_path,
        output_dir=output_dir,
        run_id=run_id,
    )
    upgraded = upgrade_document(index_path.read_text(encoding="utf-8"))
    index_path.write_text(upgraded, encoding="utf-8")
    return index_path


def main() -> None:
    args = parse_args()
    result = build_site(
        episode_dir=Path(args.episode_dir),
        media_dir=Path(args.media_dir),
        media_zip=Path(args.media_zip),
        regression_path=Path(args.regression),
        cases_path=Path(args.cases),
        output_dir=Path(args.output_dir),
        run_id=str(args.run_id),
    )
    print(result)


if __name__ == "__main__":
    main()
