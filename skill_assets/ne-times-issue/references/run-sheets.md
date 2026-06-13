# Run Sheets — Complete Issue Composition (1회분 지면 구성표)

A run sheet maps each page of one issue to a template, level, and workbook
format. Mode B = execute the full per-article workflow once per row, then
produce an issue summary table (page / topic / level / final word count /
validation status / plagiarism check result).

The default Times run sheet below is reconstructed from the production
examples in golden-samples/. **Always show the run sheet to the user before
generating and let them adjust topics, drop pages, or change formats** —
actual issues vary week to week.

## Default run sheet: NE Times

| Page | Template | Level (CEFR) | Words | Workbook format | Notes |
|---|---|---|---|---|---|
| 2면 | TIMES-L2-NOSUB | L2 (B2) | 270–280 | L2 AB Synonym or Antonym | |
| 3-1면 | TIMES-L1-STANDARD | L1 (A2-B1) | 190–200 | L1 MCQ or True-False | |
| 3-2면 | TIMES-L1-MINI | L1 (A2-B1) | ~100 | — (short news) | |
| 4면 | TIMES-L3 | L3 (C1) | ~300 | L3 Three Sequence or Match-the-Words | |
| 5면 | TIMES-L1-SHORT | L1 (B1) | 135–140 | L1 MCQ or True-False | |
| 8면 | TIMES-L2-2SUB | L2 (B2) | 280–290 | L2 ABC | 2 subheadings |
| 12면 | TIMES-L2-3SUB | L2 (B2) | 280–290 | L2 ABC 3-Subheading | 3 subheadings; Korean titles stay Korean |
| Briefs | TIMES-BRIEF ×N | A2-B1 | 65–77 each | — | typically 2–4 briefs |

Per-issue extras: vocabulary list per article, TG extras per
references/tg-extras.md (TIMES section), image candidates per article.

## Default run sheet: NE Times Kids

| Slot | Template | Level | Words | Notes |
|---|---|---|---|---|
| Main L2H | KIDS-L2H | A1-A2 | ~130 | |
| WHAT'S HOT | KIDS-WHATSHOT-2SUB or -3SUB | A2 | 150–170 | |
| (further slots) | confirm with user | | | Kids issues vary; ask for the week's plan |

TG extras: tg-extras.md Kids / UBER Kids sections.

## Junior / Kinder

No validated run sheets exist yet. Propose one based on the paper's level
(see leveling.md) and get explicit user approval before generating. Flag in
the issue summary that these pages used derived (not legacy-validated)
templates.

## Issue summary format (Mode B final deliverable)

| Page | Topic | Template | Level | Words (target/actual) | validate.py | Plagiarism check |
|---|---|---|---|---|---|---|

Plus a list of any pages needing editor attention (e.g., a fact that needs
human verification, a topic with thin sources).
