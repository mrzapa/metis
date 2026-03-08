---
id: qa-core
name: Q&A Core
description: Direct grounded answers for general document questions.
enabled_by_default: true
priority: 100
triggers:
  keywords:
    - answer
    - explain
    - what
    - why
    - how
  modes:
    - Q&A
  file_types:
    - .txt
    - .md
    - .html
    - .htm
    - .pdf
    - .docx
  output_styles:
    - Default answer
    - Detailed answer
    - Brief / exec summary
runtime_overrides:
  selected_mode: Q&A
  retrieval_k: 25
  top_k: 5
  mmr_lambda: 0.5
  retrieval_mode: flat
  agentic_mode: false
  agentic_max_iterations: 2
  output_style: Default answer
  system_instructions_append: Give the answer first, then justify it with grounded supporting detail.
  citation_policy_append: Cite factual claims inline using [S#] markers from the retrieved context.
---
Use this skill for standard grounded document question-answering.

Prefer a concise direct answer first.
Then add the minimum supporting detail needed to make the answer trustworthy.
If the context is insufficient, say so plainly instead of guessing.
