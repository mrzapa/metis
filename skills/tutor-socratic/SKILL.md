---
id: tutor-socratic
name: Tutor Socratic
description: Teaching-oriented explanations with guided questions and practice prompts.
enabled_by_default: true
priority: 100
triggers:
  keywords:
    - teach me
    - tutor
    - quiz me
    - help me learn
    - explain like
  modes:
    - Tutor
  file_types:
    - .pdf
    - .docx
    - .md
    - .txt
  output_styles:
    - Default answer
    - Detailed answer
runtime_overrides:
  selected_mode: Tutor
  retrieval_k: 24
  top_k: 6
  mmr_lambda: 0.55
  retrieval_mode: hierarchical
  agentic_mode: true
  agentic_max_iterations: 2
  output_style: Default answer
  system_instructions_append: Teach the concept clearly, check understanding, and use practice-oriented follow-ups when helpful.
  citation_policy_append: Cite each factual teaching block so the learner can verify the explanation.
---
Use this skill for educational, coaching, or study-oriented interactions.

Favor plain explanations, examples, and scaffolded understanding.
When appropriate, move from explanation to questions, flashcards, or small checks for understanding.
