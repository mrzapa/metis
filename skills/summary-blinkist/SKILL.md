---
id: summary-blinkist
name: Summary Blinkist
description: Condensed key ideas and takeaways for summarization requests.
enabled_by_default: true
priority: 100
triggers:
  keywords:
    - summarize
    - summary
    - recap
    - key ideas
    - takeaways
  modes:
    - Summary
  file_types:
    - .pdf
    - .docx
    - .epub
    - .md
  output_styles:
    - Brief / exec summary
    - Blinkist-style summary
runtime_overrides:
  selected_mode: Summary
  retrieval_k: 20
  top_k: 4
  mmr_lambda: 0.6
  retrieval_mode: hierarchical
  agentic_mode: false
  agentic_max_iterations: 2
  output_style: Blinkist-style summary
  system_instructions_append: Distill the material into key ideas, memorable points, and practical takeaways.
  citation_policy_append: Each major summary section should have at least one supporting citation.
---
Use this skill when the user wants a condensed synthesis rather than a verbatim walkthrough.

Emphasize the thesis, the most important ideas, and what a reader should remember or do next.
Avoid tangents and over-detailing.
