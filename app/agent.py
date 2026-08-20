from __future__ import annotations

import os
from typing import List

from google.adk.agents import Agent, LoopAgent, SequentialAgent
from google.adk.apps import App
from google.adk.models import Gemini
from google.adk.tools import exit_loop
from google.genai import types
from pydantic import BaseModel, Field

MODEL = os.getenv("GEMINI_MODEL", "gemini-3.7-flash")
QUALITY_THRESHOLD = float(os.getenv("SCRIPT_QUALITY_THRESHOLD", "8.7"))
MAX_REFINEMENT_ITERATIONS = int(os.getenv("MAX_REFINEMENT_ITERATIONS", "5"))


def model() -> Gemini:
    return Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    )


class ReviewResult(BaseModel):
    score: float = Field(ge=0, le=10)
    approved: bool
    factuality_risk: str
    strengths: List[str]
    problems: List[str]
    improvements: List[str]


class StoryboardShot(BaseModel):
    shot_number: int = Field(ge=1)
    visual_query: str
    on_screen_text: str
    visual_type: str = "stock_or_commons"


class StoryboardPlan(BaseModel):
    shots: List[StoryboardShot]


writer_agent = Agent(
    name="youth_script_writer",
    model=model(),
    description="Writes a concise, energetic Spanish video script from verified AI news.",
    instruction="""
You write Spanish scripts for short-form videos aimed at people roughly 16-28 years old.
Use ONLY the source material in {news_text}. Do not invent launches, dates, prices, quotes,
benchmarks, people, companies, or capabilities.

Goal:
- 60-90 seconds when spoken naturally.
- Open with a strong 1-sentence hook.
- Explain the 3-5 most important AI developments in plain Spanish.
- Sound energetic and contemporary, but never forced, childish, or cringe.
- Prefer concrete consequences: what changed, who it affects, and why it matters.
- Keep technical terms when useful, but explain them in one phrase.
- End with a short closing question or CTA.
- Avoid hype words unless the evidence supports them.

Return ONLY the finished narration script. No notes, no score, no markdown table.
""",
    output_key="draft_script",
)

reviewer_agent = Agent(
    name="script_critic",
    model=model(),
    description="Scores the current script for factuality, clarity, pacing, youth appeal, and usefulness.",
    instruction=f"""
Evaluate the current script in {{draft_script}} against the original source material in {{news_text}}.
Be strict. Score 0-10 using these dimensions:
- factual accuracy and traceability: 35%
- clarity and structure: 20%
- value/importance of selected stories: 20%
- pacing and spoken naturalness: 15%
- appeal to a young audience without sounding fake: 10%

Set approved=true ONLY when score >= {QUALITY_THRESHOLD} AND factuality_risk is 'low'.
List concrete problems and actionable improvements. Do not rewrite the script here.
""",
    output_schema=ReviewResult,
    output_key="review",
)

quality_gate_agent = Agent(
    name="quality_gate",
    model=model(),
    description="Stops the loop when the critic has approved the script.",
    instruction=f"""
Read the structured review in {{review}}.
If approved is true, score is at least {QUALITY_THRESHOLD}, and factuality_risk is low,
call exit_loop immediately. Otherwise do NOT call exit_loop and say only: CONTINUE.
""",
    tools=[exit_loop],
)

refiner_agent = Agent(
    name="script_refiner",
    model=model(),
    description="Improves the script using the latest critic feedback while preserving factual accuracy.",
    instruction="""
Revise the current script in {draft_script} using every relevant item from {review}.
Use {news_text} as the only factual source of truth.
Preserve correct facts, remove unsupported claims, improve hook/flow/clarity, and keep the final
spoken duration around 60-90 seconds.
Return ONLY the revised narration script.
""",
    output_key="draft_script",
)

refinement_loop = LoopAgent(
    name="script_quality_loop",
    sub_agents=[reviewer_agent, quality_gate_agent, refiner_agent],
    max_iterations=MAX_REFINEMENT_ITERATIONS,
)

root_agent = SequentialAgent(
    name="ai_news_video_script_pipeline",
    description="Writes and iteratively improves a youth-oriented AI news script.",
    sub_agents=[writer_agent, refinement_loop],
)

storyboard_agent = Agent(
    name="storyboard_designer",
    model=model(),
    description="Creates one visual-search instruction for every four seconds of narration.",
    instruction="""
Create a visual storyboard for the script in {final_script}.
You MUST return exactly {shot_count} shots.
Each shot represents exactly 4 seconds, in order.

For every shot:
- shot_number starts at 1 and increments by 1.
- visual_query must be a short ENGLISH search query suitable for Pexels or Wikimedia Commons.
- Prefer literal, searchable visuals: company logos/buildings, chips, robots, code, phones,
  data centers, researchers, AI interfaces, cities, regulation/government buildings.
- Do not request copyrighted movie/TV footage or fabricated screenshots.
- on_screen_text must be Spanish and <= 8 words.
- Avoid repeating the same visual query unless continuity truly requires it.

The number of shots is non-negotiable: exactly {shot_count}.
""",
    output_schema=StoryboardPlan,
    output_key="storyboard",
)

app = App(root_agent=root_agent, name="app")
