"""WriterAgent — 토픽을 받아 레벨에 맞는 NE Times 기사를 작성한다."""

import logging
from typing import Callable

import anthropic

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, SYSTEM_PROMPT, LEVEL_CONFIG
from models import ArticleResult, Level, Section, VocabItem
from agents.sub_agents.utils import parse_json

logger = logging.getLogger(__name__)

# NE Times 포맷 참고 URL
NETIMES_URL = "https://www.netimes.co.kr"


class WriterAgent:
    def __init__(
        self,
        client: anthropic.Anthropic,
        log_callback: Callable[[str], None] | None = None,
    ):
        self._client = client
        self._log = log_callback or (lambda msg: logger.info(msg))

    def run(
        self,
        topic: str,
        level: Level,
        section: Section,
        reference_format: str = "",
        source_content: str = "",
        today: str = "",
        revision_notes: str = "",
        page_cfg: dict | None = None,
        variant: str = "",
    ) -> ArticleResult:
        """
        topic : 기사 주제 또는 뉴스 URL
        level : 신문 레벨 (kinder/kids/junior/times)
        section : 섹션 (과학/환경 등)
        reference_format : netimes.co.kr에서 가져온 포맷 샘플 텍스트
        source_content : ResearcherAgent가 수집한 출처 본문 (사실 근거)
        today : 오늘 날짜 (YYYY-MM-DD) — 시제 검증용 (P0-3)
        revision_notes : 재작성 시 게이트가 지적한 수정 사항 (P0-2)
        page_cfg : 지면 설정 (P1-1) — 단어수 범위·구조·CEFR·소제목 수
        """
        self._log(f"[Writer] 기사 작성 시작 — [{level.value}] {topic[:50]}")
        cfg = LEVEL_CONFIG[level.value]

        # P1-1: 지면 설정이 있으면 단어수·CEFR·구조를 지면 기준으로 덮어쓴다
        if page_cfg:
            word_range = f"{page_cfg['word_min']}-{page_cfg['word_max']}"
            cefr = page_cfg.get("cefr") or cfg["cefr"]
            sub = page_cfg.get("subheadings", 0)
            para_hint = (
                f"Use exactly {sub} subheadings."
                if sub else "Paragraphs only, no subheadings."
            )
            structure_hint = (
                f"\n\nPage: {page_cfg.get('page','')} ({page_cfg.get('template','')}). "
                f"Required structure:\n{page_cfg.get('structure','')}"
            )
        else:
            word_range = cfg["word_count_range"]
            cefr = cfg["cefr"]
            para_hint = f"{cfg['paragraph_count']} paragraphs of roughly equal size"
            structure_hint = ""

        format_hint = (
            f"\n\nFormat reference from NE Times:\n{reference_format[:800]}"
            if reference_format
            else ""
        )
        source_hint = (
            f"\n\nResearched source material (use ONLY these facts — do NOT invent or "
            f"rely on prior knowledge; do NOT copy sentences verbatim):\n{source_content[:6000]}"
            if source_content
            else ""
        )
        # P0-3: 시제·시점 검증 지시
        temporal_hint = (
            f"\n\nTODAY'S DATE IS {today}. Critical temporal rule: compare every event "
            f"date in the source material against today. An event that has ALREADY "
            f"happened must be written in PAST tense with its actual outcome (from the "
            f"sources). Never describe a finished event as upcoming (no \"is coming\", "
            f"\"will be held\" for past events). Future events use future tense."
            if today
            else ""
        )
        # P0-2: 재작성 시 게이트 지적 사항 반영
        revision_hint = (
            f"\n\n[REVISION REQUIRED] The previous draft was rejected by the review gate "
            f"for these issues. Fix every one:\n{revision_notes}"
            if revision_notes
            else ""
        )

        variant_hint = ""
        if variant == "lively":
            variant_hint = ("\n\nVersion style: LIVELY — natural, engaging, vivid tone "
                            "that draws the reader in (while staying within the CEFR level).")
        elif variant == "strict":
            variant_hint = ("\n\nVersion style: LEVEL-STRICT — prioritize strict CEFR fidelity "
                            "and controlled vocabulary/sentence complexity over flair.")

        prompt = f"""You are writing an article for {cfg['newspaper']}.
{source_hint}{temporal_hint}{revision_hint}{structure_hint}{variant_hint}

Topic: {topic}
Section: {section.value}
Target readers: {cfg['target']}
CEFR level: {cefr}
Target word count: {word_range} words (Microsoft Word standard — count strictly)
Paragraphs: {para_hint}
{format_hint}

Instructions:
1. Base every fact, figure, name, and date ONLY on the researched source material
   above. Do not add information that is not supported by the sources.
2. Write an article suitable for the readers' age and comprehension level.
3. Include relevant vocabulary naturally in the text.
4. Add one or two points that spark curiosity or deeper interest.
5. Include background explanations where needed for younger readers.
6. Write in a tone and style appropriate to {cfg['newspaper']}.
7. Select 8-14 key vocabulary words worth learning at this paper's CEFR band
   (slightly above the article's base level; exclude proper nouns and words
   students already know). List them in ORDER OF FIRST APPEARANCE in the article.
   For each: the dictionary BASE FORM (e.g. hosted→host), its CEFR label, and a
   1-2 sense Korean meaning matching the article context.
8. For "sources", list ONLY the source URLs provided in the researched material
   above — do not invent or add decorative URLs.

Respond in this exact JSON format:
{{
  "article": "<full article text with paragraphs separated by \\n\\n>",
  "vocabulary": [
    {{"word": "host", "cefr": "B1", "meaning_ko": "개최하다"}},
    {{"word": "venue", "cefr": "B1", "meaning_ko": "경기장, 장소"}}
  ],
  "sources": ["https://...", "https://...", "https://..."]
}}

CRITICAL JSON RULES:
- Do NOT use double quotation marks (") inside any text field values.
- Replace any in-text double quotes with single quotes (') for dialogue or emphasis.
- Use only \\n\\n to separate paragraphs inside the "article" field."""

        data = self._call_claude(prompt)

        article_text = data.get("article", "")
        raw_vocab = data.get("vocabulary", [])
        sources = data.get("sources", [])

        # P2-1: dict 형식(신규) / str 리스트(구형) 모두 수용
        vocab_detail = []
        vocab_words = []
        for v in raw_vocab:
            if isinstance(v, dict):
                vocab_detail.append(VocabItem(
                    word=v.get("word", ""),
                    cefr=v.get("cefr", ""),
                    meaning_ko=v.get("meaning_ko", ""),
                ))
                vocab_words.append(v.get("word", ""))
            elif isinstance(v, str):
                vocab_words.append(v)

        result = ArticleResult(
            text=article_text,
            vocabulary=vocab_words,
            sources=sources,
            vocabulary_detail=vocab_detail,
        )
        self._log(
            f"[Writer] 완료 — {result.word_count}단어 / "
            f"어휘 {len(result.vocabulary)}개 / 출처 {len(result.sources)}개"
        )
        return result

    def extract_vocabulary(self, text: str, level: Level) -> tuple[list[str], list[VocabItem]]:
        """편집/대안 본문에서 어휘 8~14개를 재추출한다 (P2-2/P2-3 재생성용)."""
        cfg = LEVEL_CONFIG[level.value]
        prompt = f"""Select 8-14 key vocabulary words from the article below, worth learning
at {cfg['newspaper']} level (CEFR {cfg['cefr']}; exclude proper nouns). List them in
order of first appearance. For each give the dictionary BASE FORM, CEFR label, and a
1-2 sense Korean meaning matching the context.

Article:
\"\"\"
{text}
\"\"\"

Respond in this exact JSON format (no double quotes inside values):
{{"vocabulary": [{{"word": "host", "cefr": "B1", "meaning_ko": "개최하다"}}]}}"""
        try:
            data = self._call_claude(prompt)
        except Exception:
            return [], []
        words, detail = [], []
        for v in data.get("vocabulary", []):
            if isinstance(v, dict) and v.get("word"):
                detail.append(VocabItem(v.get("word", ""), v.get("cefr", ""), v.get("meaning_ko", "")))
                words.append(v["word"])
        return words, detail

    def _call_claude(self, prompt: str) -> dict:
        message = self._client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2048,
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": prompt}],
        )
        return parse_json(message.content[0].text)
