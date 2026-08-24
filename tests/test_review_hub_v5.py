from __future__ import annotations

import unittest

from pipeline.review_hub_v5 import _primary_failures, apply_p0_information_architecture


BASE_DOCUMENT = """<!doctype html>
<html lang="es"><head><style>.base{display:block}</style></head><body>
<a class="skip-link" href="#guion">Saltar al guion</a><main class="wrap">
<section class="hero"><h1>Ensayo</h1></section>
<section class="search-dock" aria-label="Buscador"><div class="search-row"><input id="globalSearch"><span id="searchCount">Busca</span></div></section>
<div id="noResults" class="no-results" hidden>Sin resultados</div>
<section id="guion" data-search-group><h2>Guion actual</h2><div id="scriptText" class="script">TEXTO COMPLETO DEL GUION</div></section>
<section id="arquitectura" data-search-group><h2>Arquitectura narrativa</h2><div data-search-item>Arquitectura</div></section>
<section id="beats" data-search-group><h2>Beats del ensayo</h2><div data-search-item>Beat</div></section>
<section id="diagnostico" data-search-group><h2>Diagnóstico</h2><details class="diagnostic"><summary>Detalle</summary></details></section>
<section id="fuentes" data-search-group><h2>Fuentes seleccionadas</h2><div class="table-wrap"><table><tbody><tr data-search-item data-search-text="Caso Uno"><td>Caso Uno</td></tr></tbody></table></div></section>
<section id="multimedia" data-search-group><h2>Multimedia de revisión</h2><div data-search-item>Media</div></section>
<section id="historial" data-search-group><h2>Guiones anteriores</h2><div data-search-item>Historial</div></section>
<section id="artefactos" data-search-group><h2>Artefactos técnicos</h2><div data-search-item>Artifact</div></section>
<div class="footer">footer</div></main>
<script>(()=>{const scriptNode=document.getElementById('scriptText');})();</script>
</body></html>"""


class ReviewHubV5Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.indicators = {
            "publishable": False,
            "status": "script_not_approved",
            "word_count": 1675,
            "duration_minutes": 11.2,
            "run_id": "32541706631",
        }
        self.reviews = {
            "gate": {"checks": {"factuality_low": False}},
            "editorial": {
                "score": 7.1,
                "approved": False,
                "factuality_risk": "medium",
                "problems": ["Factualidad: la evidencia necesita mejor trazabilidad."],
            },
            "youtube_attention_master": {
                "score": 7.6,
                "approved": False,
                "problems": ["La atención cae en la sección central."],
            },
            "voice_humanity": {
                "score": 8.1,
                "approved": False,
                "problems": ["La voz todavía suena demasiado generada."],
            },
            "seo_master": {
                "score": 8.9,
                "approved": True,
                "problems": ["Detalle SEO secundario."],
            },
        }
        self.selected = {
            "items": [
                {
                    "title": "Caso Uno",
                    "source": "Fuente A",
                    "url_quality": "article",
                    "news_id": "one",
                    "url": "https://example.com/one",
                },
                {
                    "title": "Caso Dos",
                    "source": "Fuente B",
                    "url_quality": "article",
                    "news_id": "two",
                    "url": "https://example.com/two",
                },
            ]
        }

    def test_p0_reorganizes_page_into_five_task_tabs(self) -> None:
        document = apply_p0_information_architecture(
            BASE_DOCUMENT,
            indicators=self.indicators,
            reviews=self.reviews,
            selected=self.selected,
        )

        for tab in ("overview", "script", "evidence", "media", "technical"):
            self.assertIn(f'data-tab="{tab}"', document)
            self.assertIn(f'data-panel="{tab}"', document)
        self.assertIn('role="tablist"', document)
        self.assertIn('class="workspace-nav"', document)
        self.assertIn('position:sticky', document)

    def test_overview_is_decision_first_and_does_not_contain_full_script(self) -> None:
        document = apply_p0_information_architecture(
            BASE_DOCUMENT,
            indicators=self.indicators,
            reviews=self.reviews,
            selected=self.selected,
        )
        overview = document[document.index('id="panel-overview"'):document.index('id="panel-script"')]
        script = document[document.index('id="panel-script"'):document.index('id="panel-evidence"')]

        self.assertIn("Qué necesita trabajo", overview)
        self.assertIn("Editorial", overview)
        self.assertIn("Attention", overview)
        self.assertIn("Voice", overview)
        self.assertIn("SEO", overview)
        self.assertIn("Revisar guion", overview)
        self.assertNotIn("TEXTO COMPLETO DEL GUION", overview)
        self.assertIn("TEXTO COMPLETO DEL GUION", script)
        self.assertIn('id="scriptText"', script)

    def test_diagnostics_move_to_technical_and_sources_get_mobile_cards(self) -> None:
        document = apply_p0_information_architecture(
            BASE_DOCUMENT,
            indicators=self.indicators,
            reviews=self.reviews,
            selected=self.selected,
        )
        evidence = document[document.index('id="panel-evidence"'):document.index('id="panel-media"')]
        technical = document[document.index('id="panel-technical"'):]

        self.assertIn('class="table-wrap source-table"', evidence)
        self.assertIn('class="source-cards"', evidence)
        self.assertEqual(evidence.count("data-source-mobile-item"), 2)
        self.assertIn("Caso Uno", evidence)
        self.assertIn("Caso Dos", evidence)
        self.assertIn("#panel-evidence #fuentes .source-table{display:none}", document)
        self.assertIn(".source-cards{display:grid", document)
        self.assertIn('id="diagnostico"', technical)
        self.assertIn('id="historial"', technical)
        self.assertIn('id="artefactos"', technical)

    def test_primary_failures_prioritize_failed_judges(self) -> None:
        failures = _primary_failures(self.reviews)
        self.assertEqual(len(failures), 3)
        self.assertEqual([item["label"] for item in failures], ["Editorial", "Attention", "Voice"])
        self.assertNotIn("SEO", [item["label"] for item in failures])


if __name__ == "__main__":
    unittest.main()
