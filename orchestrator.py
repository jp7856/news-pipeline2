"""오케스트레이터 — 토픽을 받아 Agent 1(콘텐츠 제작)부터 순차적으로 파이프라인을 실행한다.

사용법:
    orchestrator = Orchestrator()
    result = orchestrator.run(
        topic="Climate change and young activists",
        level=Level.JUNIOR,
        section=Section.ENVIRONMENT,
    )
"""

import logging
import uuid
from datetime import datetime
from typing import Callable

from agents import ContentProducerAgent
from agents.translator import TranslatorAgent
from agents.image_finder import ImageFinderAgent
from agents.worksheet import WorksheetAgent
from models import ContentPackage, Level, Section, ArticleStatus

logger = logging.getLogger(__name__)


class Orchestrator:
    def __init__(self, log_callback: Callable[[str], None] | None = None):
        self._log = log_callback or (lambda msg: logger.info(msg))
        self._sheet_url = ""

    def run(
        self,
        topic: str,
        level: Level,
        section: Section,
        source_url: str = "",
        page: str = "",
    ) -> ContentPackage:
        """
        단건 콘텐츠 제작 파이프라인을 실행한다.

        Args:
            topic   : 기사 주제 (자유 텍스트 또는 뉴스 URL)
            level   : Level.KINDER / KIDS / JUNIOR / TIMES
            section : Section.SCIENCE / ENVIRONMENT 등
        """
        run_id = str(uuid.uuid4())[:8]
        start = datetime.now()
        today = start.strftime("%Y-%m-%d")   # P0-3: 시제 검증 기준일
        self._log(f"=== Pipeline Start (run_id: {run_id}) ===")
        self._log(f"    Topic   : {topic}")
        self._log(f"    Level   : {level.value}")
        self._log(f"    Section : {section.value}")
        self._log(f"    Today   : {today}")
        self._log("")

        # ── Agent 1: 콘텐츠 제작 (리서치+게이트 포함) ─────────────
        producer = ContentProducerAgent(log_callback=self._log)
        package = producer.run(topic, level, section, source_url=source_url, today=today, page=page)

        # ── 게이트 미통과 시 다운스트림 보류 (P0-2) ───────────────
        if package.status == ArticleStatus.NEEDS_REVIEW:
            self._log("")
            self._log("=== Pipeline Halted: NEEDS REVIEW ===")
            rr = package.review_report
            if rr:
                for issue in rr.factual_issues:
                    self._log(f"    [사실오류] {issue}")
                for issue in rr.temporal_issues:
                    self._log(f"    [시제오류] {issue}")
                if rr.notes:
                    self._log(f"    사유: {rr.notes}")
            self._log("    → 번역·이미지·시트 저장을 보류합니다. 편집자 확인 필요.")
            return package, ""

        # ── Agent 2: 한국어 번역 ──────────────────────────────────
        translator = TranslatorAgent(log_callback=self._log)
        package = translator.run(package)

        # ── Agent 3: 이미지 탐색 ──────────────────────────────────
        image_finder = ImageFinderAgent(log_callback=self._log)
        package = image_finder.run(package)

        # ── Agent 4: Google Sheets 저장 ───────────────────────────
        worksheet = WorksheetAgent(log_callback=self._log)
        package, sheet_url = worksheet.run(package)
        self._sheet_url = sheet_url

        # ── 결과 요약 ─────────────────────────────────────────────
        duration = (datetime.now() - start).seconds
        self._log("")
        self._log(f"=== Pipeline Complete ({duration}s) ===")
        self._log(f"    Article    : {package.article.word_count} words")
        self._log(f"    Vocabulary : {len(package.article.vocabulary)} words")
        self._log(f"    Sources    : {len(package.article.sources)}")
        self._log(f"    Plagiarism : {'PASS' if package.plagiarism_report.passed else 'WARNING'}")
        if package.review_report:
            self._log(f"    Review     : 사실·시제 통과 (재작성 {package.review_report.rewrite_count}회)")
        self._log(f"    Edits      : {len(package.editing_suggestions)} suggestions")
        self._log(f"    Crossword  : {len(package.crossword_sentences)} pairs")
        self._log(f"    Workbook   : {len(package.workbook_sets)} sets")
        self._log(f"    Korean     : {'완료' if package.article.text_ko else '없음'}")
        self._log(f"    Image      : {'발견' if package.image_url else '없음'}")
        self._log(f"    Sheets     : {'저장완료' if self._sheet_url else '저장안됨'}")

        return package, self._sheet_url

    def run_issue(
        self,
        topics: dict[str, str],
        level: Level,
        section: Section,
    ) -> list[tuple[str, ContentPackage, str]]:
        """1회분(complete set) 배치 생성 (P1-1).

        topics : {지면명: 토픽} 매핑. 지정한 지면만 생성한다.
        Returns: [(지면, ContentPackage, sheet_url), ...]
        run sheet의 각 지면을 run()으로 1건씩 생성하고 요약을 로그로 남긴다.
        """
        from config import PAGE_CONFIG

        pages = PAGE_CONFIG.get(level.value, [])
        results: list[tuple[str, ContentPackage, str]] = []
        self._log(f"=== Issue Batch Start: {level.value} ({len(topics)}개 지면) ===")

        for pcfg in pages:
            page_name = pcfg["page"]
            if page_name not in topics:
                continue
            topic = topics[page_name]
            self._log(f"\n--- [{page_name}] {topic[:50]} ---")
            pkg, url = self.run(topic, level, section, page=page_name)
            results.append((page_name, pkg, url))

        # 1회분 요약표
        self._log("\n=== Issue Summary ===")
        self._log("지면 | 단어수 | 상태 | 표절")
        for page_name, pkg, _ in results:
            status = pkg.status.value if hasattr(pkg.status, "value") else str(pkg.status)
            plag = "PASS" if pkg.plagiarism_report.passed else "WARN"
            self._log(f"  {page_name} | {pkg.article.word_count} | {status} | {plag}")
        return results


def print_result(pkg: ContentPackage) -> None:
    """ContentPackage 결과물을 읽기 좋게 출력한다."""
    import sys, io
    # Windows cp949 인코딩 문제 방지
    if sys.stdout.encoding and sys.stdout.encoding.lower().startswith("cp"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    sep = "-" * 60

    print(f"\n{'=' * 60}")
    print(f"  NE Times Content Package")
    print(f"  Topic   : {pkg.topic}")
    print(f"  Level   : {pkg.level.value}")
    print(f"  Section : {pkg.section.value}")
    print(f"{'=' * 60}")

    # 기사
    print(f"\n[ARTICLE] ({pkg.article.word_count} words)")
    print(sep)
    print(pkg.article.text)
    print(sep)

    # 어휘
    print(f"\n[VOCABULARY] {len(pkg.article.vocabulary)} words")
    for w in pkg.article.vocabulary:
        print(f"  - {w}")

    # 출처
    print(f"\n[SOURCES] {len(pkg.article.sources)} links")
    for s in pkg.article.sources:
        print(f"  - {s}")

    # 표절 검사
    print(f"\n[PLAGIARISM CHECK] {'PASS' if pkg.plagiarism_report.passed else 'WARNING'}")
    for key, val in pkg.plagiarism_report.checklist.items():
        status = "PASS" if val.get("pass") else "FAIL"
        print(f"  [{status}] {key}: {val.get('note', '')[:80]}")

    # 수정 제안
    print(f"\n[EDITING SUGGESTIONS] {len(pkg.editing_suggestions)} items")
    for i, s in enumerate(pkg.editing_suggestions, 1):
        print(f"  {i}. \"{s.original[:60]}...\"")
        print(f"     -> {s.suggestion[:60]}...")
        print(f"     Reason: {s.reason}")

    # 크로스워드
    print(f"\n[CROSSWORD SENTENCES] {len(pkg.crossword_sentences)} pairs")
    for c in pkg.crossword_sentences:
        print(f"  {c.word} ({c.korean_definition})")
        print(f"    B1   : {c.sentence_b1}")
        print(f"    B1-B2: {c.sentence_b1_b2}")

    # 워크북
    for ws in pkg.workbook_sets:
        print(f"\n[WORKBOOK SET {ws.set_number}] ({ws.format_name or ws.format_key})")
        for a in ws.activities:
            print(f"  {a.label}. {a.title}: {a.body[:80]}...")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    result = Orchestrator().run(
        topic="Climate change and young activists",
        level=Level.JUNIOR,
        section=Section.ENVIRONMENT,
    )
    print_result(result)
