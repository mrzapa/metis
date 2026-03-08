---
id: research-claims
name: Research Claims
description: Structured claim and counterclaim analysis for deep research questions.
enabled_by_default: true
priority: 100
triggers:
  keywords:
    - research
    - compare arguments
    - counterclaim
    - analyze evidence
    - evaluate sources
  modes:
    - Research
  file_types:
    - .pdf
    - .docx
    - .html
    - .md
  output_styles:
    - Structured report
    - Detailed answer
runtime_overrides:
  selected_mode: Research
  retrieval_k: 42
  top_k: 12
  mmr_lambda: 0.4
  retrieval_mode: hierarchical
  agentic_mode: true
  agentic_max_iterations: 3
  output_style: Structured report
  system_instructions_append: Organize findings into claims, counterclaims, evidence quality, and unresolved gaps.
  citation_policy_append: Every major claim or counterclaim requires direct supporting citation.
---
Use this skill for deeper investigative or analytical work.

Structure the answer so a reader can audit what is supported, what is disputed, and what remains uncertain.
Prefer explicit tradeoffs and evidence quality notes over narrative fluff.
