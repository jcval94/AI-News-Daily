from __future__ import annotations

import unittest

from pipeline.review_hub_v5 import apply_p0_information_architecture
from pipeline.review_hub_v6 import apply_p1_scanability


BASE_DOCUMENT = """<!doctype html><html lang="es"><head><style>.base{display:block}</style></head><body>
<a class="skip-link" href="#guion">Saltar al guion</a><main class="wrap">
<section class="hero"><h1>Ensayo</h1><p class="lede">Pregunta central</p><div class="hero-row"><span>estado</span></div><div class="hero-actions"><a class="button">Guion</a></div><div class="hero-meta">Revisión humana: <strong>sin registro humano</strong></div></section>
<section class="search-dock"><div class="search-row"><input id="globalSearch"><span id="searchCount">Busca</span></div></section>
<div id="noResults" hidden>Sin resultados</div>
<section id="guion" data-search-group><h2>Guion actual</h2><div id="scriptText" class="script">GUION</div></section>
<section id="arquitectura" data-search-group><h2>Arquitectura narrativa</h2><div data-search-item>Arquitectura</div></section>
<section id="beats" data-search-group><h2>Beats del ensayo</h2><div data-search-item>Beat</div></section>
<section id="diagnostico" data-search-group><h2>Diagnóstico</h2><details class="diagnostic"><summary>Detalle</summary><div class="diagnostic-body"><p class="muted metric-provenance">Procedencia real.</p><div class="grid2"><div class="card"><div class="review-notes"><ul><li>Uno</li><li>Dos</li><li>Tres</li><li>Cuatro</li></ul></div></div></div></div></details></section>
<section id="fuentes" data-search-group><h2>Fuentes seleccionadas</h2><div class="table-wrap"><table><tbody><tr data-search-item><td>Fuente</td></tr></tbody></table></div></section>
<section id="multimedia" data-search-group><h2>Multimedia de revisión</h2><p>Resumen</p><div class="media-grid"><article class='media-card searchable-card' data-search-item><video></video></article><article class='media-card searchable-card' data-search-item><img></article></div></section>
<section id="historial" data-search-group><h2>Guiones anteriores</h2><div data-search-item>Historial</div></section>
<section id="artefactos" data-search-group><h2>Artefactos técnicos</h2><div data-search-item>Artifact</div></section>
<div class="footer">footer</div></main><script></script></body></html>"""


class ReviewHubV6Tests(unittest.TestCase):
    def setUp(self) -> None:
        indicators = {
            "publishable": False,
            "status": "script_not_approved",
            "word_count": 1675,
            "duration_minutes": 11.2,
            "episode_date": "2026-08-21",
            "run_id": "32541706631",
        }
        reviews = {
            "gate": {"checks": {"factuality_low": False}},
            "editorial": {"score": 7.1, "approved": False, "problems": ["Factualidad"]},
            "youtube_attention_master": {"score": 7.6, "approved": False},
            "voice_humanity": {"score": 8.1, "approved": False},
            "seo_master": {"score": 8.9, "approved": True},
        }
        selected = {"items": [{"title": "Caso", "source": "Fuente", "news_id": "one"}]}
        p0 = apply_p0_information_architecture(
            BASE_DOCUMENT,
            indicators=indicators,
            reviews=reviews,
            selected=selected,
        )
        self.document = apply_p1_scanability(
            p0,
            indicators=indicators,
            plan={"beats": [{"beat_id": "b1"}], "evidence": [{"evidence_id": "e1"}]},
            selected=selected,
            manifest=[
                {"file": "a.mp4", "asset_type": "video", "start_seconds": 0},
                {"file": "b.jpg", "asset_type": "image", "start_seconds": 25},
            ],
        )

    def test_p1_compacts_hero_and_moves_provenance(self) -> None:
        hero = self.document.split('<section class="hero">', 1)[1].split("</section>", 1)[0]
        technical = self.document.split('id="panel-technical"', 1)[1]
        self.assertIn("Episodio 2026-08-21 · run 32541706631", hero)
        self.assertNotIn("Revisión humana", hero)
        self.assertIn("Provenance del run", technical)
        self.assertIn("Revisión humana", technical)

    def test_p1_adds_focused_subtabs_without_removing_sections(self) -> None:
        for name in ("architecture", "beats", "sources"):
            self.assertIn(f'data-subtab="{name}"', self.document)
        for name in ("judges", "history", "artifacts"):
            self.assertIn(f'data-subtab="{name}"', self.document)
        for section_id in ("arquitectura", "beats", "fuentes", "diagnostico", "historial", "artefactos"):
            self.assertIn(f'id="{section_id}"', self.document)
        self.assertIn("1</strong> beats", self.document)
        self.assertIn("1</strong> evidencias", self.document)
        self.assertIn("1</strong> fuentes", self.document)

    def test_p1_search_media_and_long_review_controls_are_present(self) -> None:
        self.assertIn('id="clearSearch"', self.document)
        self.assertIn('class="search-shortcut"', self.document)
        self.assertIn('data-media-filter="opening"', self.document)
        self.assertIn('data-media-filter="video"', self.document)
        self.assertIn('data-media-filter="image"', self.document)
        self.assertEqual(self.document.count("data-media-kind='"), 2)
        self.assertIn("review-notes-toggle", self.document)
        self.assertIn("metric-provenance-details", self.document)


if __name__ == "__main__":
    unittest.main()
