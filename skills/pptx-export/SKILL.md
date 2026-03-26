---
id: pptx-export
name: PPTX Export (PptxGenJS)
description: Prepare METIS RAG and Evidence Pack outputs as slide-ready content for PowerPoint export using PptxGenJS.
enabled_by_default: true
priority: 100
triggers:
  keywords:
    - pptx
    - powerpoint
    - slide deck
    - slides
    - export deck
    - executive deck
    - evidence pack slides
    - presentation
    - pptxgenjs
    - board deck
  modes:
    - Evidence Pack
    - Research
    - Summary
    - Q&A
  file_types:
    - .pdf
    - .docx
    - .md
    - .txt
    - .html
  output_styles:
    - Structured report
    - Brief / exec summary
    - Detailed answer
runtime_overrides:
  selected_mode: Evidence Pack
  retrieval_k: 35
  top_k: 10
  mmr_lambda: 0.5
  retrieval_mode: hierarchical
  agentic_mode: true
  agentic_max_iterations: 3
  output_style: Structured report
  system_instructions_append: Shape the answer into slide-sized sections suitable for direct mapping to PptxGenJS slides.
  citation_policy_append: Keep source anchors per slide and include citation tags for factual bullets.
---
Use this skill when the user wants chat output that can be exported to a PPTX deck in the web app with PptxGenJS.

Produce content in slide-oriented chunks:
- Slide title: one clear takeaway.
- Subtitle/context: optional one-line framing.
- Bullets: 3-5 concise points, each ideally under 14 words.
- Evidence/citations: include inline tags like [S1], [S2] per factual bullet.
- Speaker note text: optional 1-2 sentence expansion per slide.

For METIS Evidence Pack and RAG outputs:
- Group by claims, timeline steps, risks, decisions, or recommendations.
- Keep one idea per slide; split dense sections into multiple slides.
- Preserve uncertainty explicitly (for example: "Insufficient evidence", "Conflicting sources").
- End with a Sources slide listing all cited source IDs and short labels.

Output format preference:
- Return a numbered slide list.
- For each slide, include: `title`, `bullets`, `citations`, and optional `notes`.
- Keep language presentation-ready and avoid long prose blocks.

Target requirement:
- PPTX export target is PptxGenJS for web generation; structure output so each slide maps cleanly to a PptxGenJS slide object.
