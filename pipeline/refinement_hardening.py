from __future__ import annotations

from types import ModuleType

from app.refiners import editorial_factual_refiner_agent


def install(base_module: ModuleType | None = None) -> ModuleType:
    """Install a recovery refiner that matches the gate semantics used by pipeline.run.

    pipeline.run intentionally routes any failing editorial/factual block to its `factual`
    phase before voice or secondary polish. The legacy factual-only agent could therefore
    receive conceptual/editorial feedback it was forbidden to act on and repeatedly consume
    the entire refinement budget. The hardened runtime keeps voice and secondary passes
    isolated, but lets this first phase repair the complete editorial/factual block that the
    gate actually evaluates.
    """
    if base_module is None:
        from pipeline import run as base_module

    base_module.factual_refiner_agent = editorial_factual_refiner_agent
    return base_module
