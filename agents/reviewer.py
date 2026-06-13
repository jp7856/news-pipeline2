"""Agent 5 / 검수 게이트 — 기사의 사실 정확성과 시제·시점을 검증한다 (P0-2, P0-3).

기존 'Article 발행 승인' 역할에서, content_producer 흐름 내부의 **차단 게이트**로
재설계되었다. 수집한 출처 본문과 오늘 날짜를 근거로:
  - factual_issues : 출처에 없거나 출처와 모순되는 사실 주장
  - temporal_issues: 과거 이벤트를 미래형으로 서술하는 등 시점 오류
를 찾아낸다. 하나라도 있으면 passed=False로 재작성을 유발한다.

원인 해결: F-2(사실 오류 무차단 통과), F-3(오류 다운스트림 전파).
"""

import logging
from typing import Callable

import anthropic

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, SYSTEM_PROMPT
from models import ArticleResult, ResearchResult, ReviewReport
from agents.sub_agents.utils import parse_json

logger = logging.getLogger(__name__)

REVIEW_PROMPT = """You are a fact-checking editor for an educational newspaper.
Today's date is {today}.

Verify the ARTICLE below strictly against the RESEARCHED SOURCES. Find only
real, blocking problems — not style preferences.

Check two things:

1. FACTUAL ACCURACY: every fact, figure, name, and date in the article must be
   supported by the sources. Flag any claim that is absent from the sources or
   that contradicts them. (Example of a real failure: stating a country's "first
   Winter Olympics since 1956" when an intervening one occurred.)

2. TEMPORAL CORRECTNESS: compare every event date against today ({today}). An
   event already in the past must be written in PAST tense with its actual
   outcome. Flag any past event described as upcoming/future ("is coming",
   "will be held", "are coming!") or any tense that conflicts with the date.

ARTICLE:
\"\"\"
{article}
\"\"\"

RESEARCHED SOURCES:
\"\"\"
{sources}
\"\"\"

Respond in this exact JSON format (no double quotes inside string values):
{{
  "passed": true or false,
  "factual_issues": ["specific issue 1", "..."],
  "temporal_issues": ["specific issue 1", "..."],
  "notes": "one-line summary"
}}

Set passed=false if there is ANY factual_issue or temporal_issue. If sources are
empty, flag that every non-trivial claim is unverifiable."""


class ReviewerAgent:
    def __init__(
        self,
        client: anthropic.Anthropic | None = None,
        log_callback: Callable[[str], None] | None = None,
    ):
        self._client = client or anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        self._log = log_callback or (lambda msg: logger.info(msg))

    def run(
        self,
        article: ArticleResult,
        research: ResearchResult | None,
        today: str,
    ) -> ReviewReport:
        self._log("[Review] 사실·시제 검수 시작")
        sources_text = research.combined_text if research and research.sources else "(no sources)"

        prompt = REVIEW_PROMPT.format(
            today=today,
            article=article.text,
            sources=sources_text[:8000],
        )

        try:
            data = self._call_claude(prompt)
        except Exception as e:
            # 검수 자체 실패 시 안전하게 차단(통과시키지 않음)
            self._log(f"[Review] 검수 오류 — 안전 차단: {e}")
            return ReviewReport(
                passed=False,
                factual_issues=[f"검수 실행 오류: {e}"],
                notes="review error",
            )

        factual = [s for s in data.get("factual_issues", []) if s]
        temporal = [s for s in data.get("temporal_issues", []) if s]
        passed = data.get("passed", False) and not factual and not temporal

        if passed:
            self._log("[Review] 통과 ✓ (사실·시제 이상 없음)")
        else:
            self._log(
                f"[Review] 차단 — 사실오류 {len(factual)}건 / 시제오류 {len(temporal)}건"
            )

        return ReviewReport(
            passed=passed,
            factual_issues=factual,
            temporal_issues=temporal,
            notes=data.get("notes", ""),
        )

    def _call_claude(self, prompt: str) -> dict:
        message = self._client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1200,
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": prompt}],
        )
        return parse_json(message.content[0].text)
