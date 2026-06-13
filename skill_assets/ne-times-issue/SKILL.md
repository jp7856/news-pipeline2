---
name: ne-times-issue
description: >-
  NE Times(영자신문 4종: Kinder/Kids/Junior/Times) 콘텐츠 제작 워크플로우.
  영어 학습용 신문 기사 생성, 한국어 번역, 표절/저작권 검수, 어휘리스트,
  워크북 액티비티, Teacher's Guide 부가자료, 이미지 후보 추천까지 한 번에
  처리한다. 사용자가 NE Times 기사 작성, 영자신문 콘텐츠, 워크북 제작,
  어휘리스트 생성, "1회분/complete set 제작", 특정 지면(2면, 5면 등) 기사,
  Kinder/Kids/Junior/Times 레벨 콘텐츠를 언급하면 반드시 이 스킬을 사용할 것.
  키워드만 주어져도(예: "부산 관광 기사 L2로 써줘") 이 스킬을 사용한다.
---

# NE Times Issue Production

Produce classroom-ready English newspaper content for NE Times' four weekly
papers. This skill turns a topic instruction (keywords + optional reference
links) into either a single article package or a complete issue set, following
the editorial team's established prompt assets.

## Adopt the persona first

Before any writing, read `references/persona.md`. It defines who you are (a
15-year veteran writer/editor of English-education newspapers), the four
papers and their CEFR ranges, the editorial principles, and the 8-point
Plagiarism-Risk Checklist used for copyright review. Everything you produce
must pass that checklist.

## The two modes

**Mode A — Single article package** (most common request)
One article for one page/level, plus its companion materials.

**Mode B — Complete issue set**
A full issue (1회분) of one paper: every page generated in sequence using the
run sheet in `references/run-sheets.md`. Treat it as Mode A repeated per page.

If the user's request doesn't make the mode, paper (Kinder/Kids/Junior/Times),
level, or page obvious, ask before generating — a wrong level wastes an entire
generation cycle.

## Workflow (per article)

Follow these steps in order. Steps 1–2 exist because the source prompts demand
real facts with verifiable sources; never write the article first and look for
sources afterward.

### 1. Research
Search the web for the topic. Collect 2–4 reliable sources (news outlets,
official announcements). Record each source URL — only URLs of pages you
actually fetched and read; never list plausible-looking "decorative" URLs.
If the user supplied reference links, fetch and use them, but corroborate
with at least one more source. Extract the facts, figures, names, and dates
the article will need. Do not invent or "fill in" any fact not found in a
source.

**Temporal check**: compare every event date against today's date. An event
that has already happened must be written in past tense with its actual
outcome (researched, not assumed); an upcoming event in future tense. Writing
a finished event as upcoming is a publication-killing error — it has occurred
in production when generation relied on stale model knowledge instead of
live research.

### 2. Level + template selection
Read `references/leveling.md` for the unified CEFR table (it also resolves
known inconsistencies in the legacy documents — follow its operational
standard). Then read `references/article-templates.md` and pick the template
matching the paper, page, and level. The template gives word count range,
paragraph/subheading structure, and content-slot order.

### 3. Draft the article — two versions
Write **two alternative drafts** (this preserves the team's practice of
generating with two models and choosing the better one):
- Version A: natural, lively, engaging tone
- Version B: stricter level fidelity, more controlled vocabulary

Both must satisfy the template's word count (Microsoft Word counting standard
— count with `scripts/validate.py`, never by eye), structure, and CEFR level.
Label them clearly and recommend one with a one-line reason. List sources
under each draft.

### 4. Validate
Run `scripts/validate.py` on each draft:
```
python scripts/validate.py draft.txt --min 270 --max 280 [--sources sources.txt]
```
It checks word count, detects citation artifacts (e.g. "위키백과+1",
"SBS 뉴스" fragments LLMs leave in text), flags suspiciously long verbatim
overlaps with source text, and verifies source URLs respond. Fix every
failure and re-run until clean. Word count failures are the most common —
trim or expand precisely, do not pad with filler.

### 5. Editing pass (fresh-eyes review)
Re-read the chosen draft as an editor, per the Editing rules in
`references/persona.md`: list each suggested change as 원문 → 수정안 → 사유
(grammar, awkwardness, level fit, and especially factual accuracy against
the collected sources). Then apply every factual correction and any clear
improvement, and re-run validate.py on the corrected text. Include the
suggestion list in the deliverable so the human editor sees what changed.
Findings here are a **gate, not a memo**: a factual error that is detected
but not fixed will propagate into the translation, workbook, and crossword —
this exact failure has occurred in production.

### 6. Copyright / plagiarism review
Run the corrected draft through the Plagiarism-Risk Checklist in
`references/persona.md` item by item. Report the result as a short table
(item → pass/revise). If any item fails, revise and re-check. This is a
required deliverable, not an internal step — and like step 5, it blocks
progress: do not continue to later steps with an unresolved flag.

### 7. Korean translation
Translate the final article into natural Korean (교육용 보조 자료 톤,
번역투 최소화). Keep proper nouns consistent with Korean press usage.

### 8. Vocabulary list
Two situations:
- If the user provides an article with `@`-marked words: follow
  `references/vocab-rules.md` exactly (it is strict — extraction only,
  no judgment).
- If no `@` marks exist (the usual case for new articles): propose 8–14
  candidate words appropriate to the paper's level (justify against the CEFR
  band in `references/leveling.md`), present them for confirmation, then
  format the final list per `references/vocab-rules.md` output rules.

### 9. Workbook
Read `references/workbook-formats.md` and use the format matching the level
and article structure (8 formats: L1 MCQ / L1 True-False / L2 ABC / L2 ABC
3-subheading / L2 AB Synonym / L2 AB Antonym / L3 Three Sequence / L3 Match
the Words with Blanks). Produce **two sets** of comprehension/discussion
questions so the editor can choose, per the persona's working rules. Include
the Extra Activity (phrasal verbs) where the format specifies it.

### 10. Crossword sentences (when requested or when the issue includes one)
Follow the Crossword Puzzle Sentences rule in `references/persona.md`: for
each selected vocabulary word, confirm the Korean meaning in context, then
write two sample sentences with the word as a 6-space blank — one at B1, one
at B1-B2 — so the editor can choose.

### 11. Teacher's Guide extras (when requested or in Mode B)
Follow `references/tg-extras.md` for the paper in question (Kids / UBER Kids /
TIMES variants).

### 12. Image candidates
Follow `references/image-licensing.md`. Suggest 3–5 image concepts and, for
each, where to obtain a rights-safe version (priority order: licensed stock →
public domain/CC0 → AI-generated). Never present a Google Images result as
"copyright-safe". Output the license-evidence log table defined 