"""Agent 4: Google Sheets 저장 — ContentPackage를 스프레드시트에 기록한다."""

import json
import logging
import os
from typing import Callable

import gspread
from google.oauth2.service_account import Credentials

from config import GOOGLE_SHEETS_CREDENTIALS_JSON, GOOGLE_SHEET_ID
from models import ContentPackage

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

SHEET_COLUMNS = [
    "생성일시", "레벨", "섹션", "토픽", "단어수",
    "기사(영문)", "기사(한국어)", "요약(한국어)",
    "어휘", "출처", "표절검사", "이미지URL",
    "크로스워드", "워크북Set1", "워크북Set2",
]


class WorksheetAgent:
    def __init__(self, log_callback: Callable[[str], None] | None = None):
        self._log = log_callback or (lambda msg: logger.info(msg))
        self._sheet = None

    def run(self, package: ContentPackage) -> tuple[ContentPackage, str]:
        """
        ContentPackage를 Google Sheets에 저장한다.
        Returns: (package, sheet_url)
        """
        self._log("[Agent4] Google Sheets 저장 시작")
        sheet_url = ""
        try:
            sheet = self._get_sheet()
            self._ensure_header(sheet)
            row = self._package_to_row(package)
            sheet.append_row(row, value_input_option="USER_ENTERED")
            sheet_url = f"https://docs.google.com/spreadsheets/d/{GOOGLE_SHEET_ID}"
            self._log(f"[Agent4] 저장 완료 → {sheet_url}")
        except Exception as e:
            self._log(f"[Agent4] 저장 오류: {e}")
        return package, sheet_url

    # ------------------------------------------------------------------

    def _get_sheet(self) -> gspread.Worksheet:
        if self._sheet is not None:
            return self._sheet

        # Railway env var는 JSON 문자열, 로컬은 파일 경로 둘 다 지원
        creds_val = GOOGLE_SHEETS_CREDENTIALS_JSON
        try:
            creds_dict = json.loads(creds_val)
            creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        except (json.JSONDecodeError, TypeError):
            # 파일 경로로 시도
            creds = Credentials.from_service_account_file(creds_val, scopes=SCOPES)

        gc = gspread.authorize(creds)
        spreadsheet = gc.open_by_key(GOOGLE_SHEET_ID)
        self._sheet = spreadsheet.sheet1
        return self._sheet

    def _ensure_header(self, sheet: gspread.Worksheet) -> None:
        first_row = sheet.row_values(1)
        if first_row != SHEET_COLUMNS:
            sheet.insert_row(SHEET_COLUMNS, index=1)

    def _package_to_row(self, pkg: ContentPackage) -> list:
        from datetime import datetime

        crossword = json.dumps(
            [{"word": c.word, "ko": c.korean_definition,
              "b1": c.sentence_b1, "b1b2": c.sentence_b1_b2}
             for c in pkg.crossword_sentences],
            ensure_ascii=False
        )

        def wb_json(ws):
            return json.dumps({
                "vocab": ws.vocabulary_activity,
                "true_false": ws.true_false,
                "comprehension": ws.comprehension_questions,
                "discussion": ws.discussion_questions,
            }, ensure_ascii=False)

        wb1 = wb_json(pkg.workbook_sets[0]) if len(pkg.workbook_sets) > 0 else ""
        wb2 = wb_json(pkg.workbook_sets[1]) if len(pkg.workbook_sets) > 1 else ""

        return [
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            pkg.level.value,
            pkg.section.value,
            pkg.topic,
            pkg.article.word_count,
            pkg.article.text,
            pkg.article.text_ko,
            pkg.article.summary_ko,
            ", ".join(pkg.article.vocabulary),
            "\n".join(pkg.article.sources),
            "PASS" if pkg.plagiarism_report.passed else "WARNING",
            pkg.image_url,
            crossword,
            wb1,
            wb2,
        ]
