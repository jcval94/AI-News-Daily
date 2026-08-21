from __future__ import annotations

import os
from typing import List, Literal

from google.adk.agents import Agent, LoopAgent, SequentialAgent
from google.adk.apps import App
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools import exit_loop
from pydantic import BaseModel, Field

MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-nano")
QUALITY_THRESHOLD = float(os.getenv("SCRIPT_QUALITY_THRESHOLD", "8.7"))
JUDGE_THRESHOLD = float(os.getenv("JUDGE_THRESHOLD", "8.5"))
MAX_REFINEMENT_ITERATIONS = int(os.getenv("MAX_REFINEMENT_ITERATIONS", "5"))
MAX_SELECTED_NEWS = int(os.getenv("MAX_SELECTED_NEWS", "8"))


def model() -> LiteLlm:
    """Return an OpenAI-backed model while keeping Google ADK as orchestrator."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required")

    return LiteLlm(
        model=f"openai/{MODEL}",
        api_key=api_key,
    )


class SelectedNewsItem(BaseModel):
    title: str
    date: str
    source: str
    url: str = ""
    summary: str
    why_it_matters: str
    category: str


class SelectionResult(BaseModel):
    items: List[SelectedNewsItem] = Field(default_factory=list, max_length=MAX_SELECTED_NEWS)
    discarded_duplicates: List[str] = Field(default_factory=list)
    selection_notes: List[str] = Field(default_factory=list)


class ReviewResult(BaseModel):
    score: float = Field(ge=0, le=10)
    approved: bool
    factuality_risk: str = "low"
    strengths: List[str]
    problems: List[str]
    improvements: List[str]


class MasterJudgeResult(BaseModel):
    score: float = Field(ge=0, le=10)
    approved: bool
    strengths: List[str]
    problems: List[str]
    improvements: List[str]


class MultimediaSegment(BaseModel):
    slot_number: int = Field(ge=1)
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0)
    mode: Literal["media", "presenter"]
    visual_query: str = ""
    on_screen_text: str = ""
    reason: str = ""


class MultimediaPlan(BaseModel):
    segments: List[MultimediaSegment]


selector_agent = Agent(
    name="news_relevance_selector",
    model=model(),
    description="Selects the most relevant unique AI news before script writing.",
    instruction=f"""
You are the editorial selection desk for a youth-oriented AI news video.
Read all raw news in {{news_text}} and select ONLY the most relevant developments.
Also inspect {{previous_selected_news}}, which contains stories already used in recent episodes.

Rules:
- Return at most {MAX_SELECTED_NEWS} stories.
- Remove duplicates aggressively, including different articles about the same underlying event.
- Do not reuse an event from previous_selected_news unless the current input contains a materially new development.
- If a previously covered event is kept because it materially changed, explain that in selection_notes.
- When two current items cover the same event, keep the clearest and most authoritative source.
- Prefer major model/product launches, agentic AI, important research, regulation, hardware,
  safety/security developments, and company moves with broad impact.
- Do not select filler, minor marketing announcements, or near-duplicate follow-ups.
- Preserve the factual date, source and URL whenever present in the input.
- Rank implicitly by importance: the first item should be the strongest story.
- Never invent facts that are not in the source text.
""",
    output_schema=SelectionResult,
    output_key="selected_news",
)


writer_agent = Agent(
    name="youth_script_writer",
    model=model(),
    description="Writes a concise, energetic Spanish video script from selected verified AI news.",
    instruction="""
You write Spanish scripts for short-form videos aimed at people roughly 16-28 years old.
Use ONLY {selected_news} as the editorial content and {news_text} as factual source material.
Do not invent launches, dates, prices, quotes, benchmarks, people, companies, or capabilities.

Goal:
- 60-90 seconds when spoken naturally.
- Open with a strong hook immediately.
- Cover only the most important selected stories; do not force every story into the script.
- Explain developments in plain Spanish and focus on what changed, who it affects and why it matters.
- Keep useful technical terms, but explain them briefly.
- Use relevant names/keywords naturally so the topic is searchable, without keyword stuffing.
- Maintain retention with concise transitions and curiosity, without fake urgency or clickbait.
- End with a short closing question or CTA.

Return ONLY the finished narration script. No notes, no score, no markdown table.
""",
    output_key="draft_script",
)


reviewer_agent = Agent(
    name="script_critic",
    model=model(),
    description="Scores the current script for factuality, clarity, pacing, relevance and usefulness.",
    instruction=f"""
Evaluate {{draft_script}} against {{selected_news}} and the original {{news_text}}.
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


seo_master_agent = Agent(
    name="seo_master",
    model=model(),
    description="Acts as the SEO Master judge for discoverability without sacrificing natural speech.",
    instruction=f"""
Judge {{draft_script}} as an expert YouTube/AI SEO editor.
Use {{selected_news}} to understand the real entities and topics.
Approve ONLY if score >= {JUDGE_THRESHOLD}.

Evaluate whether:
- the strongest searchable entities/topics appear naturally early enough;
- the script makes the video's subject unmistakable;
- important model/company/product names are preserved when editorially relevant;
- wording supports search intent without keyword stuffing;
- there is no misleading clickbait or unsupported superlative.

Return a strict score, approved flag, strengths, problems and actionable improvements.
Do not rewrite the script.
""",
    output_schema=MasterJudgeResult,
    output_key="seo_review",
)


youtube_attention_master_agent = Agent(
    name="youtube_attention_master",
    model=model(),
    description="Acts as the YouTube Attention Master judge for hook and viewer retention.",
    instruction=f"""
Judge {{draft_script}} as an expert in YouTube audience retention for viewers around 16-28.
Approve ONLY if score >= {JUDGE_THRESHOLD}.

Evaluate whether:
- the opening earns attention in the first 3 seconds;
- the first 15 seconds create clear curiosity and value without false urgency;
- pacing avoids long setup, repetition and dead zones;
- transitions create forward momentum;
- the strongest story appears early;
- language sounds contemporary and human, not forced or cringe;
- the ending is concise and gives a reason to comment/share/continue watching.

Return a strict score, approved flag, strengths, problems and actionable improvements.
Do not rewrite the script.
""",
    output_schema=MasterJudgeResult,
    output_key="attention_review",
)


quality_gate_agent = Agent(
    name="quality_gate",
    model=model(),
    description="Stops refinement only when all three judges approve the current script.",
    instruction=f"""
Read {{review}}, {{seo_review}} and {{attention_review}}.
Call exit_loop ONLY when ALL of the following are true:
- review.approved is true, review.score >= {QUALITY_THRESHOLD}, review.factuality_risk is low;
- seo_review.approved is true and seo_review.score >= {JUDGE_THRESHOLD};
- attention_review.approved is true and attention_review.score >= {JUDGE_THRESHOLD}.
Otherwise do NOT call exit_loop and say only: CONTINUE.
""",
    tools=[exit_loop],
)


refiner_agent = Agent(
    name="script_refiner",
    model=model(),
    description="Improves the script using feedback from all editorial judges.",
    instruction="""
Revise {draft_script} using every relevant item from {review}, {seo_review} and {attention_review}.
Use {selected_news} and {news_text} as the only factual source of truth.
Preserve correct facts, remove unsupported claims, improve the hook, retention, clarity and natural SEO,
and keep the final spoken duration around 60-90 seconds.
Return ONLY the revised narration script.
""",
    output_key="draft_script",
)


refinement_loop = LoopAgent(
    name="script_quality_loop",
    sub_agents=[
        reviewer_agent,
        seo_master_agent,
        youtube_attention_master_agent,
        quality_gate_agent,
        refiner_agent,
    ],
    max_iterations=MAX_REFINEMENT_ITERATIONS,
)


root_agent = SequentialAgent(
    name="ai_news_video_script_pipeline",
    description="Selects news, writes a script and iteratively improves it until all judges approve.",
    sub_agents=[selector_agent, writer_agent, refinement_loop],
)


multimedia_editor_agent = Agent(
    name="multimedia_editor_master",
    model=model(),
    description="Chooses when the presenter appears and when external multimedia is actually necessary.",
    instruction="""
You are the Multimedia Editor Master for the approved narration in {final_script}.
You receive the canonical timeline slots in {timeline_slots}.
Return exactly one decision for every provided slot, preserving each slot_number/start_seconds/end_seconds.

For each slot choose ONE mode:
- presenter: a person should be on camera; no external multimedia should be downloaded.
- media: external visual multimedia materially improves understanding or attention.

Rules:
- Use at most {max_media_downloads} media slots. This is a hard cap.
- Use media only when it adds real visual value; do not download filler.
- Prefer presenter for transitions, opinions, connective narration and lines that benefit from human presence.
- For media slots, visual_query must be a short ENGLISH query suitable for Pexels/Wikimedia Commons.
- For presenter slots, visual_query must be empty.
- on_screen_text must be Spanish and at most 8 words.
- Avoid copyrighted movie/TV footage and fabricated screenshots.
- The first 15 seconds are split into 3-second slots to force a visible change every 3 seconds.
  Honor those slots exactly; a visible change may be new media or a presenter shot/overlay decision.
""",
    output_schema=MultimediaPlan,
    output_key="multimedia_plan",
)


app = App(root_agent=root_agent, name="app")
