from __future__ import annotations

from typing import Any

from google.adk.agents import Agent

from app.agent import model, writer_agent


MARKER_GUARD = """

ABSOLUTE SECTION-MARKER VALIDATION — REQUIRED:
Before returning the script, silently validate the marker sequence against episode_plan.beats.
The output is invalid unless ALL of these are true:
1. <!--SECTION:opening--> appears exactly once and is first.
2. For every beat in episode_plan.beats, <!--SECTION:beat:BEAT_ID--> appears exactly once, in plan order.
3. No beat marker may be repeated, restarted, copied, or emitted a second time later in the narration.
4. <!--SECTION:synthesis--> appears exactly once and is last.
5. The total number of SECTION markers must equal len(episode_plan.beats) + 2.
6. If you want to revisit an earlier idea, do so in prose under the current section; NEVER repeat its marker.
7. Do not emit a second pass, alternate draft, recap, appendix, or continuation containing section markers.
Return one draft only.
"""


hardened_writer_agent = Agent(
    name="essay_script_writer",
    model=model(),
    description=writer_agent.description,
    instruction=str(writer_agent.instruction) + MARKER_GUARD,
    output_key="draft_script",
)


def install(base: Any) -> Any:
    """Replace only the writer with a marker-contract-hardened equivalent."""
    base.writer_agent = hardened_writer_agent
    return base
