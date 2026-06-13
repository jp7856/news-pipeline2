"""Agent 1: ContentProducerAgent — NE Times 콘텐츠 제작 파이프라인 코디네이터.

개선 흐름 (P0-1/P0-2/P0-3):
  [Agent0] Researcher (실시간 리서치) ──▶ 출처 미확보 시 NEEDS_REVIEW 중단
      ↓
  Writer (출처 본문 + 오늘 날짜 기반 작성)
      ↓
  ┌─ 게이트 루프 (최대 N회) ─────────────────────────┐
  │  PlagiarismChecker  +  Reviewer(사실·시제 검증)   │
  │  둘 다 통과 → 탈출 / 아니면 지적사항으로 재작성   │
  └──────────────────────────────────────────────────┘
      ↓ (통과한 최종본 기준)
  Editor(교정 제안) → Crossword + Workbook
      ↓
  ContentPackage 반환

미해결(최대 재시도 초과) 시 status=NEEDS_REVIEW로 다운스트림(크로스워드·워크북)
생성을 보류한다.
"""

import logging
from typing import Callable

import anthropic
import requests
from bs4 import BeautifulSoup

from config import ANTHROPIC_API_KEY, get_page_config
from models import (
    ContentPackage, Level, Section, ArticleStatus, ReviewReport,
    PlagiarismReport,
)
from agents.sub_agents.validation import ms_word_count
from agents.sub_agents import (
    WriterAgent,
    PlagiarismCheckerAgent,
    EditorAgent,
    CrosswordAgent,
    WorkbookAgent,
    ResearcherAgent,
)
from agents.reviewer import ReviewerAgent

logger = logging.getLogger(__name__)

NETIMES_SAMPLE_URL = "https://www.netimes.co.kr"
MAX_REWRITES = 2   # 최초 작성 + 최대 2회 재작성 = 총 3회


class ContentProducerAgent:
    def __init__(self, log_callback: Callable[[str], None] | None = None):
        self._log = log_callback or (lambda msg: logger.info(msg))
        self._client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        self._reference_format_cache: str = ""

        # 서브에이전트 초기화 (클라이언트 공유)
        self._researcher = ResearcherAgent(log_callback=self._log)
        self._writer     = WriterAgent(self._client, log_callback=self._log)
        self._plagcheck  = PlagiarismCheckerAgent(self._client, log_callback=self._log)
        self._reviewer   = ReviewerAgent(self._client, log_callback=self._log)
        self._editor     = EditorAgent(self._client, log_callback=self._log)
        self._crossword  = CrosswordAgent(self._client, log_callback=self._log)
        self._workbook   = WorkbookAgent(self._client, log_callback=self._log)

    def run(
        self,
        topic: str,
        level: Level,
        section: Section,
        source_url: str = "",
        today: str = "",
        page: str = "",
    ) -> ContentPackage:
        page_cfg = get_page_config(level.value, page or None)
        self._log(
            f"[Agent1] 콘텐츠 제작 시작 — [{level.value}/{section.value}] "
            f"{page_cfg['page']}({page_cfg['template']}) {topic[:50]}"
        )

        reference = self._get_reference_format()

        # ── Agent 0: 실시간 리서치 (P0-1) ─────────────────────────
        research = self._researcher.run(topic, section.value, source_url=source_url)
        if not research.success:
            # 출처 미확보 → 생성 중단 (NEEDS_REVIEW)
            self._log("[Agent1] 출처 미확보로 생성 중단 — NEEDS_REVIEW")
            return self._halt_package(
                topic, level, section, research=research,
                review=ReviewReport(
                    passed=False, needs_human_review=True,
                    notes=research.note,
                ),
            )

        # ── Step 1: 기사 작성 (출처 + 오늘 날짜 + 지면 규격 기반) ──
        article = self._writer.run(
            topic, level, section,
            reference_format=reference,
            source_content=research.combined_text,
            today=today,
            page_cfg=page_cfg,
        )
        # 출처는 실제 fetch한 URL로 고정 (P0-1 수용기준 ①)
        article.sources = research.urls

        # ── Step 2: 게이트 루프 (표절 + 사실·시제 + 단어수) ───────
        plagiarism_report = None
        review_report = None
        rewrites = 0
        while True:
            plagiarism_report = self._plagcheck.run(article)
            review_report = self._reviewer.run(article, research, today)
            wc_ok, wc_note = self._check_word_count(article, page_cfg)  # P1-1

            if plagiarism_report.passed and review_report.passed and wc_ok:
                break
            if rewrites >= MAX_REWRITES:
                # 미해결 → 다운스트림 보류
                review_report.rewrite_count = rewrites
                review_report.needs_human_review = True
                self._log(f"[Agent1] {rewrites}회 재작성 후에도 미해결 — NEEDS_REVIEW")
                return self._halt_package(
                    topic, level, section,
                    article=article, research=research,
                    plagiarism=plagiarism_report, review=review_report,
                )

            rewrites += 1
            notes = self._build_revision_notes(plagiarism_report, review_report)
            if not wc_ok:
                notes = (notes + "\n" + wc_note).strip()
            self._log(f"[Agent1] 게이트 미통과 — 재작성 {rewrites}/{MAX_REWRITES}")
            article = self._writer.run(
                topic, level, section,
                reference_format=reference,
                source_content=research.combined_text,
                today=today,
                revision_notes=notes,
                page_cfg=page_cfg,
            )
            article.sources = research.urls

        review_report.rewrite_count = rewrites
        self._log(f"[Agent1] 게이트 통과 ✓ (재작성 {rewrites}회)")

        # ── Step 3: 교정 제안 (최종본 기준, 편집자용 메모) ────────
        editing_suggestions = self._editor.run(article, level)

        # ── Step 4 & 5: 크로스워드 + 워크북 (통과한 최종본 기준) ──
        crossword_sentences = self._crossword.run(article)
        workbook_sets       = self._workbook.run(
            article, level, format_key=page_cfg.get("workbook_format")
        )

        self._log(
            f"[Agent1] 완료 — 기사 {article.word_count}단어 / "
            f"표절 통과 / 사실·시제 통과 / 재작성 {rewrites}회 / "
            f"수정제안 {len(editing_suggestions)}건"
        )

        return ContentPackage(
            topic=topic,
            level=level,
            section=section,
            article=article,
            plagiarism_report=plagiarism_report,
            editing_suggestions=editing_suggestions,
            crossword_sentences=crossword_sentences,
            workbook_sets=workbook_sets,
            research=research,
            review_report=review_report,
            status=ArticleStatus.APPROVED,
        )

    # ------------------------------------------------------------------

    def _check_word_count(self, article, page_cfg: dict) -> tuple[bool, str]:
        """P1-1: 단어수를 지면 규격과 비교. 벗어나면 재조정 지시를 만든다."""
        lo, hi = page_cfg.get("word_min", 0), page_cfg.get("word_max", 10000)
        wc = ms_word_count(article.text)
        article.word_count = wc
        if lo <= wc <= hi:
            return True, ""
        if wc < lo:
            note = f"- WORD COUNT: {wc} words is too short. Expand to {lo}-{hi} words without padding."
        else:
            note = f"- WORD COUNT: {wc} words is too long. Trim to {lo}-{hi} words; cut least-essential detail."
        self._log(f"[Agent1] 단어수 {wc} (목표 {lo}-{hi}) — 재조정 필요")
        return False, note

    def _build_revision_notes(self, plag: PlagiarismReport, review: ReviewReport) -> str:
        lines = []
        if not plag.passed:
            failed = [k for k, v in plag.checklist.items() if not v.get("pass", True)]
            lines.append(f"- Plagiarism risk in: {', '.join(failed)}. {plag.notes}")
        for issue in review.factual_issues:
            lines.append(f"- FACTUAL: {issue}")
        for issue in review.temporal_issues:
            lines.append(f"- TEMPORAL: {issue}")
        return "\n".join(lines)

    def _halt_package(
        self, topic, level, section, *,
        article=None, research=None, plagiarism=None, review=None,
    ) -> ContentPackage:
        """게이트 미통과/출처 미확보 시 다운스트림을 보류한 패키지를 반환한다."""
        from models import ArticleResult
        if article is None:
            article = ArticleResult(text="", vocabulary=[], sources=[])
        if plagiarism is None:
            plagiarism = PlagiarismReport(passed=False, checklist={}, notes="검수 미완료")
        return ContentPackage(
            topic=topic,
            level=level,
            section=section,
            article=article,
            plagiarism_report=plagiarism,
            editing_suggestions=[],
            crossword_sentences=[],
            workbook_sets=[],
            research=research,
            review_report=review,
            status=ArticleStatus.NEEDS_REVIEW,
        )

    def _scrape_article(self, url: str) -> str:
        """URL에서 기사 본문을 추출한다. (ResearcherAgent로 대체됐으나 호환 유지)"""
        try:
            resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            soup = BeautifulSoup(resp.text, "lxml")
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            paragraphs = [
                p.get_text(strip=True)
                for p in soup.find_all("p")
                if len(p.get_text(strip=True)) > 40
            ]
            return "\n\n".join(paragraphs[:30])[:3000]
        except Exception as e:
            self._log(f"[Agent1] 스크래핑 실패 (무시): {e}")
            return ""

    def _get_reference_format(self) -> str:
        """netimes.co.kr에서 샘플 기사 텍스트를 가져온다 (세션 중 1회 캐시)."""
        if self._reference_format_cache:
            return self._reference_format_cache
        try:
            resp = requests.get(
                NETIMES_SAMPLE_URL, timeout=8, headers={"User-Agent": "Mozilla/5.0"}
            )
            soup = BeautifulSoup(resp.text, "lxml")
            texts = [p.get_text(strip=True) for p in soup.find_all("p") if len(p.get_text(strip=True)) > 40]
            self._reference_format_cache = "\n".join(texts[:15])
            self._log(f"[Agent1] NE Times 포맷 참고 로드 완료 ({len(texts)}개 단락)")
        except Exception as e:
            self._log(f"[Agent1] NE Times 포맷 로드 실패 (무시하고 계속): {e}")
            self._reference_format_cache = ""
        return self._reference_format_cache
