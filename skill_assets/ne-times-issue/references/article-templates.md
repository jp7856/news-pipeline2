# Article Templates (파라미터화 — 원문: 01_타임즈/03_키즈 기사 프롬프트)

Each template is the legacy production prompt rewritten with parameters in
`{braces}`. Fill the parameters, then write directly — do not echo the
template back to the user. Universal rules for every template:

- Count words by the Microsoft Word standard (validate with scripts/validate.py).
- Divide into paragraphs of fairly consistent size.
- Use real online sources; list them after the article.
- Do not make up information or facts.
- Keep Korean proper nouns in Korean when the topic is Korean media/culture
  and the template notes it.

---

## TIMES-L1-STANDARD (3-1면, 190–200 words)

Write a 190–200 word article about {topic}. Divide into paragraphs and use
real sources. Suitable for {audience, default: early high schoolers} at
{CEFR, default: A2-B1}.

Content slots (in order):
1. The news itself
2. Profile / background of the subject
3. Responses and expectations
4. If available, one brief quote

## TIMES-L1-SHORT (5면, 135–140 words)

Write a 135–140 word article about {topic}. Paragraphs, no subheadings.
Real sources, provided. {CEFR, default: B1}.

Content slots:
1. The news
2. Details and the reason behind it
3. Specifics (what/which/who)
4. Responses

## TIMES-L1-MINI (3-2면, ~100 words)

Write a ~100 word article about {topic}. Paragraphs; real sources (use the
provided link plus at least one more). {CEFR, default: A2-B1}.

Content slots:
1. The news and its key content
2. Why it happened / motivation
3. Response or expectations, if available

## TIMES-L2-NOSUB (2면, 270–280 words)

Write a 270–280 word article about {topic}. Paragraphs only, no subheadings.
Real sources, provided. {CEFR, default: B2}.

Content slots:
1. The phenomenon/news with its key record or figure
2. Concrete examples (places, items, cases) and what happens there
3. Causes, including policies if relevant
4. Future plans of the responsible body

## TIMES-L2-2SUB (8면, 280–290 words)

Write a 280–290 word article about {topic with exactly two named items}.
{CEFR, default: B2}. Open with a ~45-word intro paragraph, then one
subheaded section per item ({item1}, {item2}), each ~120 words in ~4 short
paragraphs covering:
1. Background/tradition of the organization
2. Description of the item
3. Reason for selection / what it expresses
4. How it will be used

## TIMES-L2-3SUB (12면, 280–290 words)

Write a 280–290 word article about {three named items}. {CEFR, default: B2}.
Open with a 40–45 word intro, then one subheaded section per item, each ~80
words in ~2 paragraphs covering:
1. Basic info (incl. platform/venue)
2. What it is about
3. One distinct point of interest — keep the three sections from feeling
   repetitive; pick a different angle for each.
Keep Korean titles in Korean (e.g. 모범택시3).

## TIMES-L3 (4면, ~300 words)

Write a ~300 word article about {topic}. Paragraphs, no subheadings. Real
sources, provided. {CEFR, default: C1}.

Content slots:
1. The decision/event, its details, how it will be implemented
2. The reason and current state (figures of decline/growth etc.)
3. Reactions, pros and cons
4. Other countries/actors considering the same — omit if none exist
Weight the article toward slots 1–2.

## TIMES-BRIEF (65–77 words)

Single paragraph, 65–77 words, about {topic}. {CEFR: A2-B1}. Straightforward
News-Brief style: relevant information only, no color. Use the provided
source link plus others. Headline: 3–6 words, present tense, no period.
(See golden-samples/briefs-instruction.md for two format examples.)

---

## KIDS-L2H (~130 words)

Write a ~130 word article about {topic}. Each paragraph exactly two
sentences. Real sources. Suitable for 6th-grade elementary (A1-A2). Include
a general explanation of any concept a child wouldn't know (e.g. "what an
exoplanet is").

## KIDS-WHATSHOT-3SUB (150–170 words)

Write a 150–170 word article about {topic with three named sub-items}, for
sixth graders at A2. Two-sentence paragraphs. Brief intro (20–25 words),
then three subheaded sections, one per item, each 2 paragraphs / 40–50
words. (Golden sample: "Top Search Words" / "Unique Rainbows".)

## KIDS-WHATSHOT-2SUB (150–170 words)

Same as above but two subheaded sections of 70–75 words each.

---

## JUNIOR-* / KINDER-* (derived)

No legacy templates exist. Build as follows and confirm structure with the
user before a full issue:
- **Junior**: take the nearest Times-L1 or Kids-L3 template; set CEFR to
  A2~A2-B1; sentence length between Kids and Times L1.
- **Kinder**: take KIDS-L2H; set CEFR to A1-or-lower; max ~80 words;
  sentences ≤8 words; concrete, visual topics only.

## Two-version drafting note

Legacy practice ran each prompt through two chatbots (Copilot = livelier,
ChatGPT = stricter level fidelity) and picked the better output. Reproduce
this by writing Version A (lively) and Version B (level-strict) yourself,
and recommending one.
