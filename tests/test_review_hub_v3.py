from __future__ import annotations

import unittest

from pipeline.review_hub_v3 import upgrade_document


class ReviewHubV3Tests(unittest.TestCase):
    def test_progressive_ux_and_delivery_hardening(self) -> None:
        page = """<!doctype html>
<html lang=\"es\"><head>
<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
<style>.script{max-height:920px;overflow:auto}</style>
</head><body><main class=\"wrap\">
<input id=\"globalSearch\" type=\"search\" autocomplete=\"off\">
<span id=\"searchCount\" class=\"search-count\">Busca en todo el hub</span>
<video controls preload='metadata'></video>
<a href='asset.jpg' target='_blank'><img src='asset.jpg' loading='lazy' alt='asset'></a>
</main></body></html>"""

        upgraded = upgrade_document(page)

        self.assertIn('class="skip-link"', upgraded)
        self.assertIn('href="#guion"', upgraded)
        self.assertIn('aria-live="polite"', upgraded)
        self.assertIn('enterkeyhint="search"', upgraded)
        self.assertIn("preload='none'", upgraded)
        self.assertNotIn("preload='metadata'", upgraded)
        self.assertIn("decoding='async'", upgraded)
        self.assertIn("target='_blank' rel='noreferrer'><img", upgraded)
        self.assertIn(".script{max-height:none;overflow:visible}", upgraded)
        self.assertIn("prefers-reduced-motion", upgraded)
        self.assertIn("content-visibility:auto", upgraded)
        self.assertIn('name="description"', upgraded)


if __name__ == "__main__":
    unittest.main()
