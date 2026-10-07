from __future__ import annotations

from typing import Any

from google.adk.agents import Agent

from app.agent import WriterDraftResult, model, writer_agent


MARKER_GUARD = """

ABSOLUTE STRUCTURED-WRITER VALIDATION — REQUIRED:
Before returning, silently validate the WriterDraftResult against episode_plan.
1. opening is non-empty spoken narration.
2. beats contains exactly one spoken string per episode_plan.beats item, in plan order.
3. synthesis is non-empty spoken narration.
4. Do not emit <!--SECTION:...--> or <!--MEMORY:...--> comments; Python owns hidden metadata.
5. primary_memory_section_index uses 0=opening, 1..N=beats in order, N+1=synthesis.
6. That index must match the primary narrative_parallel.placement.
7. The primary Narrative Memory passage must BEGIN the indexed section so Python can place its hidden marker deterministically.
8. Return one structured draft only. Do not append an alternate draft, recap, continuation, or prose outside the schema.
"""



hardened_writer_agent = Agent(
    name="essay_script_writer",
    model=model(),
    description=writer_agent.description,
    instruction=str(writer_agent.instruction) + MARKER_GUARD,
    output_schema=WriterDraftResult,
    output_key="writer_draft",
)


def install(base: Any) -> Any:
    """Replace only the writer with a structured-output-hardened equivalent."""
    base.writer_agent = hardened_writer_agent
    return base
