---
id: evidence-pack-timeline
name: Evidence Pack Timeline
description: Timeline-heavy packet construction for incident, chronology, and dossier requests.
enabled_by_default: true
priority: 100
triggers:
  keywords:
    - evidence pack
    - timeline
    - chronology
    - incident
    - dossier
    - affidavit
  modes:
    - Evidence Pack
  file_types:
    - .pdf
    - .docx
    - .md
    - .txt
  output_styles:
    - Structured report
    - Script / talk track
runtime_overrides:
  selected_mode: Evidence Pack
  retrieval_k: 35
  top_k: 10
  mmr_lambda: 0.5
  retrieval_mode: hierarchical
  agentic_mode: true
  agentic_max_iterations: 3
  output_style: Structured report
  system_instructions_append: Build a chronology-first evidence packet with explicit source anchoring and date-sensitive organization.
  citation_policy_append: Every factual line in the packet must be backed by citations.
---
Use this skill when the output should read like a packet, dossier, or chronology rather than a conversational answer.

Prefer dates, actors, events, supporting excerpts, and clear uncertainty markers.
Make it easy for a user to trace each line back to evidence.
