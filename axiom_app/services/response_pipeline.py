"""Advanced response pipelines for summary, tutoring, and grounding."""

from __future__ import annotations

from dataclasses import dataclass, field
import html
import json
import pathlib
import re
from typing import Any

from axiom_app.models.session_types import EvidenceSource


@dataclass(slots=True)
class PipelineResult:
    """Structured output from an advanced response pipeline."""

    response_text: str
    plan_payload: dict[str, Any] = field(default_factory=dict)
    grounding_html: str = ""
    validation_notes: list[str] = field(default_factory=list)


def is_blinkist_summary_mode(mode: str, output_style: str = "") -> bool:
    normalized_mode = str(mode or "").strip().lower()
    normalized_style = str(output_style or "").strip().lower()
    return normalized_mode == "summary" or normalized_style == "blinkist-style summary"


def is_tutor_mode(mode: str) -> bool:
    return str(mode or "").strip().lower() == "tutor"


def is_one_shot_learning_request(query: str) -> bool:
    text = str(query or "").strip().lower()
    if not text:
        return False
    one_shot_signals = (
        "one-shot",
        "one shot",
        "no follow-up",
        "no follow up",
        "without questions",
        "just teach me",
        "single response",
    )
    return any(signal in text for signal in one_shot_signals)


def extract_json_payload(text: str) -> dict[str, Any]:
    raw = str(text or "").strip()
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
        return payload if isinstance(payload, dict) else {}
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    for start_idx, char in enumerate(raw):
        if char != "{":
            continue
        try:
            payload, _end = decoder.raw_decode(raw[start_idx:])
        except json.JSONDecodeError:
            continue
        return payload if isinstance(payload, dict) else {}
    return {}


def render_flashcards(flashcards: list[dict[str, Any]]) -> str:
    rendered = ["### Flashcards (10)"]
    for idx, card in enumerate(flashcards or [], start=1):
        question = str(card.get("q") or "").strip()
        answer = str(card.get("a") or "").strip()
        sources = [str(s).strip() for s in (card.get("sources") or []) if str(s).strip()]
        citation = f" [{' '.join(sources)}]" if sources else ""
        if not question or not answer:
            continue
        rendered.append(f"{idx}. Q: {question}")
        rendered.append(f"   A: {answer}{citation}")
    return "\n".join(rendered)


def render_quiz(quiz_items: list[dict[str, Any]], answer_key: list[dict[str, Any]]) -> str:
    rendered = ["### Quiz (5 questions)"]
    for idx, item in enumerate(quiz_items or [], start=1):
        q_text = str(item.get("question") or "").strip()
        if q_text:
            rendered.append(f"{idx}. {q_text}")
    rendered.append("\n### Answer Key")
    for idx, item in enumerate(answer_key or [], start=1):
        answer = str(item.get("answer") or "").strip()
        reason = str(item.get("why") or "").strip()
        sources = [str(s).strip() for s in (item.get("sources") or []) if str(s).strip()]
        citation = f" [{' '.join(sources)}]" if sources else ""
        if answer:
            line = f"{idx}. {answer}"
            if reason:
                line += f" - {reason}"
            line += citation
            rendered.append(line)
    return "\n".join(rendered)


def build_source_cards(sources: list[EvidenceSource]) -> str:
    if not sources:
        return ""
    cards: list[str] = []
    for source in sources:
        locator = source.locator or source.section_hint or source.breadcrumb or source.header_path
        cards.append(
            "\n".join(
                [
                    f"{source.sid}",
                    f"Title: {source.title or source.label or source.source}",
                    f"Locator: {locator or '-'}",
                    f"Path: {source.file_path or '-'}",
                    f"Excerpt: {source.excerpt or source.snippet}",
                ]
            )
        )
    return "\n\n".join(cards)


def run_blinkist_summary_pipeline(
    llm: Any,
    *,
    query_text: str,
    context_block: str,
    sources: list[EvidenceSource],
) -> PipelineResult:
    source_cards = build_source_cards(sources)
    stage_a_prompt = (
        "You are Stage A planner for Blinkist-style summary mode. "
        "Build a strict JSON plan using CONTEXT and SOURCE_CARDS only. "
        "Do not ask for more information. Omit unsupported claims. Return ONLY valid JSON with keys: "
        "premise, key_ideas, actionable_takeaways, memorable_quotes, key_takeaways, chapter_mini_summaries."
    )
    stage_a_messages = [
        {"type": "system", "content": stage_a_prompt},
        {
            "type": "human",
            "content": (
                f"User request:\n{query_text}\n\n"
                f"CONTEXT:\n{context_block}\n\n"
                f"SOURCE_CARDS:\n{source_cards}"
            ),
        },
    ]
    stage_a_response = llm.invoke(stage_a_messages)
    plan_payload = extract_json_payload(str(getattr(stage_a_response, "content", stage_a_response) or ""))

    stage_b_prompt = (
        "You are Stage B renderer for Blinkist-style summary mode. "
        "Render final output from PLAN_JSON only. Use this template exactly:\n"
        "1) Premise\n"
        "2) 10 Key Ideas\n"
        "3) 5 Actionable Takeaways\n"
        "4) 3 Memorable Quotes\n"
        "5) Whole-book key takeaways\n"
        "6) Optional Chapter-by-chapter mini-summaries\n"
        "Use [S#] citations. Never emit placeholders."
    )
    stage_b_messages = [
        {"type": "system", "content": stage_b_prompt},
        {
            "type": "human",
            "content": (
                f"User request:\n{query_text}\n\n"
                f"PLAN_JSON:\n{json.dumps(plan_payload, ensure_ascii=False, indent=2)}\n\n"
                f"SOURCE_CARDS:\n{source_cards}"
            ),
        },
    ]
    stage_b_response = llm.invoke(stage_b_messages)
    response_text = str(getattr(stage_b_response, "content", stage_b_response) or "").strip()
    if not response_text:
        response_text = render_blinkist_summary_fallback(plan_payload)
    return PipelineResult(
        response_text=response_text or render_blinkist_summary_fallback(plan_payload),
        plan_payload=plan_payload,
    )


def render_blinkist_summary_fallback(plan_payload: dict[str, Any]) -> str:
    premise = str(plan_payload.get("premise") or "").strip()
    key_ideas = [item for item in (plan_payload.get("key_ideas") or []) if isinstance(item, dict)]
    takeaways = [item for item in (plan_payload.get("actionable_takeaways") or []) if isinstance(item, dict)]
    quotes = [item for item in (plan_payload.get("memorable_quotes") or []) if isinstance(item, dict)]
    whole_book = [str(item).strip() for item in (plan_payload.get("key_takeaways") or []) if str(item).strip()]
    chapters = [item for item in (plan_payload.get("chapter_mini_summaries") or []) if isinstance(item, dict)]

    rendered = ["1) Premise"]
    if premise:
        rendered.append(premise)
    rendered.append("\n2) 10 Key Ideas")
    for idx, item in enumerate(key_ideas[:10], start=1):
        sources = [str(s).strip() for s in (item.get("sources") or []) if str(s).strip()]
        citation = f" [{' '.join(sources)}]" if sources else ""
        rendered.append(f"Idea {idx} - {str(item.get('title') or '').strip() or f'Idea {idx}'}")
        if item.get("what"):
            rendered.append(f"What it is: {str(item.get('what')).strip()}{citation}")
        if item.get("why"):
            rendered.append(f"Why it matters: {str(item.get('why')).strip()}{citation}")
        if item.get("how"):
            rendered.append(f"How to apply: {str(item.get('how')).strip()}{citation}")
    rendered.append("\n3) 5 Actionable Takeaways")
    for idx, item in enumerate(takeaways[:5], start=1):
        title = str(item.get("title") or f"Takeaway {idx}").strip()
        steps = [str(step).strip() for step in (item.get("steps") or []) if str(step).strip()]
        sources = [str(s).strip() for s in (item.get("sources") or []) if str(s).strip()]
        citation = f" [{' '.join(sources)}]" if sources else ""
        rendered.append(f"{idx}. {title}{citation}")
        for step in steps:
            rendered.append(f"   - {step}")
    rendered.append("\n4) 3 Memorable Quotes")
    for idx, item in enumerate(quotes[:3], start=1):
        quote = str(item.get("quote") or "").strip()
        why = str(item.get("why_it_matters") or "").strip()
        locator = str(item.get("source_locator") or "").strip()
        sources = [str(s).strip() for s in (item.get("sources") or []) if str(s).strip()]
        citation = f" [{' '.join(sources)}]" if sources else ""
        if quote:
            rendered.append(f"{idx}. \"{quote}\"")
            if why:
                rendered.append(f"   Why it matters: {why}{citation}")
            if locator:
                rendered.append(f"   Source locator: {locator}")
    rendered.append("\n5) Whole-book key takeaways")
    for item in whole_book[:5]:
        rendered.append(f"- {item}")
    if chapters:
        rendered.append("\n6) Chapter-by-chapter mini-summaries")
        for item in chapters:
            chapter = str(item.get("chapter") or "").strip()
            summary = str(item.get("summary") or "").strip()
            sources = [str(s).strip() for s in (item.get("sources") or []) if str(s).strip()]
            citation = f" [{' '.join(sources)}]" if sources else ""
            if chapter or summary:
                rendered.append(f"- {chapter or 'Chapter'}: {summary}{citation}")
    return "\n".join(rendered).strip()


def run_tutor_pipeline(
    llm: Any,
    *,
    query_text: str,
    context_block: str,
    sources: list[EvidenceSource],
) -> PipelineResult:
    source_cards = build_source_cards(sources)
    one_shot_mode = is_one_shot_learning_request(query_text)
    socratic_rule = (
        "socratic_questions must be an empty array because the user requested a one-shot explanation."
        if one_shot_mode
        else "socratic_questions must contain exactly 3 questions."
    )
    stage_a_prompt = (
        "You are Stage A planner for Tutor mode. "
        "Build strict JSON grounded in CONTEXT and SOURCE_CARDS only. Return ONLY valid JSON with keys: "
        "lesson, analogies, socratic_questions, flashcards, quiz. "
        f"{socratic_rule}"
    )
    stage_a_messages = [
        {"type": "system", "content": stage_a_prompt},
        {
            "type": "human",
            "content": (
                f"User request:\n{query_text}\n\n"
                f"CONTEXT:\n{context_block}\n\n"
                f"SOURCE_CARDS:\n{source_cards}"
            ),
        },
    ]
    stage_a_response = llm.invoke(stage_a_messages)
    plan_payload = extract_json_payload(str(getattr(stage_a_response, "content", stage_a_response) or ""))

    lesson = dict(plan_payload.get("lesson") or {})
    analogies = [item for item in (plan_payload.get("analogies") or []) if isinstance(item, dict)]
    socratic_questions = [str(item).strip() for item in (plan_payload.get("socratic_questions") or []) if str(item).strip()]
    flashcards = [item for item in (plan_payload.get("flashcards") or []) if isinstance(item, dict)]
    quiz_payload = dict(plan_payload.get("quiz") or {})
    quiz_questions = [item for item in (quiz_payload.get("questions") or []) if isinstance(item, dict)]
    answer_key = [item for item in (quiz_payload.get("answer_key") or []) if isinstance(item, dict)]

    lesson_title = str(lesson.get("concept") or "").strip() or "Concept"
    lesson_body = str(lesson.get("explanation") or "").strip()
    lesson_sources = [str(s).strip() for s in (lesson.get("sources") or []) if str(s).strip()]
    lesson_citation = f" [{' '.join(lesson_sources)}]" if lesson_sources else ""

    rendered = [f"## Tutor - {lesson_title}"]
    if lesson_body:
        rendered.append(f"{lesson_body}{lesson_citation}")
    rendered.append("\n### Analogies & Examples")
    for idx, item in enumerate(analogies[:3], start=1):
        example = str(item.get("example") or "").strip()
        sources_for_item = [str(s).strip() for s in (item.get("sources") or []) if str(s).strip()]
        citation = f" [{' '.join(sources_for_item)}]" if sources_for_item else ""
        if example:
            rendered.append(f"{idx}. {example}{citation}")
    if not one_shot_mode:
        rendered.append("\n### Socratic Questions")
        for idx, question in enumerate(socratic_questions[:3], start=1):
            rendered.append(f"{idx}. {question}")
    rendered.append("\n" + render_flashcards(flashcards[:10]))
    rendered.append("\n" + render_quiz(quiz_questions[:5], answer_key[:5]))
    return PipelineResult(response_text="\n".join(rendered).strip(), plan_payload=plan_payload)


def build_grounding_html(
    output_dir: str | pathlib.Path,
    *,
    title: str,
    query_text: str,
    answer_text: str,
    sources: list[EvidenceSource],
    extra_html: str = "",
) -> str:
    root = pathlib.Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    path = root / "langextract_grounding_latest.html"
    if extra_html:
        html_body = extra_html
    else:
        items = []
        for source in sources:
            items.append(
                "<li>"
                f"<strong>{html.escape(source.sid)}</strong> "
                f"{html.escape(source.title or source.source)}"
                f"<br><small>{html.escape(source.locator or source.section_hint or source.breadcrumb or '')}</small>"
                f"<pre>{html.escape(source.excerpt or source.snippet)}</pre>"
                "</li>"
            )
        html_body = (
            "<html><body>"
            f"<h2>{html.escape(title)}</h2>"
            f"<p><strong>Query:</strong> {html.escape(query_text)}</p>"
            f"<pre>{html.escape(answer_text)}</pre>"
            "<h3>Evidence</h3>"
            f"<ol>{''.join(items)}</ol>"
            "</body></html>"
        )
    path.write_text(html_body, encoding="utf-8")
    return str(path)


def apply_claim_level_grounding(
    answer_text: str,
    sources: list[EvidenceSource],
) -> tuple[str, list[str]]:
    if not sources:
        return answer_text, []

    source_tokens = {
        source.sid: _claim_tokens(source.excerpt or source.snippet)
        for source in sources
    }
    notes: list[str] = []
    kept: list[str] = []
    for raw_line in str(answer_text or "").splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            kept.append(raw_line)
            continue
        if _looks_structural_line(stripped) or _extract_source_labels(stripped):
            kept.append(raw_line)
            continue
        if not _looks_factual_claim(stripped):
            kept.append(raw_line)
            continue
        best_label, best_score = _best_source_label(stripped, source_tokens)
        if best_label and best_score >= 0.26:
            kept.append(f"{stripped} [{best_label}]")
            notes.append(f"Appended grounding citation [{best_label}] to an uncited factual claim.")
            continue
        if best_label and best_score >= 0.16:
            bounded = _rewrite_to_bounded_language(stripped, best_label)
            kept.append(bounded)
            notes.append("Rewrote a weakly supported factual claim with bounded language.")
            continue
        notes.append("Dropped unsupported factual claim during claim-level grounding.")

    cleaned = "\n".join(line for line in kept if line.strip()).strip()
    return cleaned or answer_text, notes


def _claim_tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-zA-Z0-9][a-zA-Z0-9_-]{2,}", str(text or "").lower())
        if token not in {"with", "from", "that", "this", "into", "were", "have", "their", "about"}
    }


def _extract_source_labels(text: str) -> list[str]:
    labels: list[str] = []
    for match in re.findall(r"\[(S\d+(?:\s*,\s*S\d+)*)\]", str(text or "")):
        for token in match.split(","):
            label = token.strip()
            if label:
                labels.append(label)
    return labels


def _best_source_label(claim: str, source_tokens: dict[str, set[str]]) -> tuple[str | None, float]:
    claim_tokens = _claim_tokens(claim)
    if not claim_tokens:
        return None, 0.0
    best_label = None
    best_score = 0.0
    for label, tokens in source_tokens.items():
        if not tokens:
            continue
        overlap = len(claim_tokens & tokens)
        score = overlap / max(1, len(claim_tokens))
        if score > best_score:
            best_label = label
            best_score = score
    return best_label, best_score


def _looks_structural_line(text: str) -> bool:
    return bool(re.match(r"^\s{0,3}#{1,6}\s+\S", text) or re.match(r"^\d+\)", text))


def _looks_factual_claim(text: str) -> bool:
    factual_hint_re = re.compile(
        r"\b(is|are|was|were|has|have|had|shows?|indicates?|states?|reports?|found|observed|according|caused?|led|resulted)\b",
        re.I,
    )
    return bool(factual_hint_re.search(text)) or len(text) >= 40


def _rewrite_to_bounded_language(claim: str, label: str) -> str:
    bounded = claim.rstrip(" .")
    if not bounded.lower().startswith(("the retrieved context suggests", "the available evidence suggests")):
        bounded = f"The available evidence suggests {bounded[:1].lower() + bounded[1:]}"
    return f"{bounded}. [{label}]"
