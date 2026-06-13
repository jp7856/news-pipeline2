"""Agent 4: Google Sheets 저장 — ContentPackage를 스프레드시트에 기록한다.

P1-4: credentials는 GOOGLE_SHEETS_CREDENTIALS_JSON(서비스계정 JSON 문자열) 우선
사용으로 통일. 저장 실패 시 로컬 CSV로 백업하여 데이터 유실을 막는다.
"""

import csv
import json
import logging
import os
from datetime import datetime
from pathlib import Path
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

# 저장 실패 시 백업 디렉토리 (프로젝트 루트/sheet_backups)
BACKUP_DIR = Path(__file__).resolve().parent.parent / "sheet_backups"

SHEET_COLUMNS = [
    "생성일시", "레벨", "섹션", "토픽", "단어수",
    "기사(영문)", "기사(한국어)", "요약(한국어)",
    "어휘", "출처", "표절검사", "이미지URL",
    "이미지출처", "이미지라이선스", "이미지확인일",   # P1-3 라이선스 증빙
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
        row = self._package_to_row(package)
        try:
            sheet = self._get_sheet()
            self._ensure_header(sheet)
            sheet.append_row(row, value_input_option="USER_ENTERED")
            sheet_url = f"https://docs.google.com/spreadsheets/d/{GOOGLE_SHEET_ID}"
            self._log(f"[Agent4] 저장 완료 → {sheet_url}")
        except Exception as e:
            # P1-4: 실패 시 로컬 CSV 백업 (데이터 유실 방지)
            self._log(f"[Agent4] 시트 저장 실패 — CSV 백업으로 전환: {e}")
            backup = self._backup_csv(row)
            if backup:
                self._log(f"[Agent4] CSV 백업 완료 → {backup}")
            else:
                self._log("[Agent4] CSV 백업도 실패 — 데이터 미저장")
        return package, sheet_url

    # ------------------------------------------------------------------

    def _get_sheet(self) -> gspread.Worksheet:
        if self._sheet is not None:
            return self._sheet

        creds = self._load_credentials()
        gc = gspread.authorize(creds)
        spreadsheet = gc.open_by_key(GOOGLE_SHEET_ID)
        self._sheet = spreadsheet.sheet1
        return self._sheet

    def _load_credentials(self) -> Credentials:
        """GOOGLE_SHEETS_CREDENTIALS_JSON(서비스계정 JSON 문자열)을 우선 사용한다.
        JSON 파싱이 안 되면 파일 경로로 간주(로컬 개발 호환)."""
        creds_val = (GOOGLE_SHEETS_CREDENTIALS_JSON or "").strip()
        if not creds_val:
            raise RuntimeError(
                "GOOGLE_SHEETS_CREDENTIALS_JSON 미설정 — Railway 환경변수에 "
                "서비스계정 JSON 전체를 넣어주세요."
            )
        try:
            creds_dict = json.loads(creds_val)
            return Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        except (json.JSONDecodeError, TypeError):
            if os.path.exists(creds_val):
                return Credentials.from_service_account_file(creds_val, scopes=SCOPES)
            raise RuntimeError(
                "GOOGLE_SHEETS_CREDENTIALS_JSON 값이 유효한 JSON도, 존재하는 파일 경로도 아닙니다."
            )

    def _backup_csv(self, row: list) -> str | None:
        """저장 실패 시 로컬 CSV에 행을 누적 기록한다."""
        try:
            BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            path = BACKUP_DIR / f"backup_{datetime.now().strftime('%Y%m%d')}.csv"
            new_file = not path.exists()
            with open(path, "a", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                if new_file:
                    writer.writerow(SHEET_COLUMNS)
                writer.writerow(row)
            return str(path)
        except Exception as e:
            logger.error(f"CSV 백업 실패: {e}")
            return None

    def _ensure_header(self, sheet: gspread.Worksheet) -> None:
        first_row = sheet.row_values(1)
        if first_row != SHEET_COLUMNS:
            sheet.insert_row(SHEET_COLUMNS, index=1)

    def _package_to_row(self, pkg: ContentPackage) -> list:
        crossword = json.dumps(
            [{"word": c.word, "ko": c.korean_definition,
              "b1": c.sentence_b1, "b1b2": c.sentence_b1_b2}
             for c in pkg.crossword_sentences],
            ensure_ascii=False
        )

        def wb_json(ws):
            return json.dumps({
                "format": ws.format_name or ws.format_key,
                "activities": [
                    {"label": a.label, "title": a.title,
                     "instruction": a.instruction, "body": a.body, "answer": a.answer}
                    for a in ws.activities
                ],
            }, ensure_ascii=False)

        wb1 = wb_json(pkg.workbook_sets[0]) if len(pkg.workbook_sets) > 0 else ""
        wb2 = wb_json(pkg.workbook_sets[1]) if len(pkg.workbook_sets) > 1 else ""

        sel = pkg.image_selected
        img_source = f"{sel.source} / {sel.photographer}" if sel else ""
        img_license = sel.license if sel else ""
        img_date = sel.confirmed_date if sel else ""

        return [
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            pkg.level.value,
            pkg.section.value,
            pkg.topic,
            pkg.article.word_count,
            pkg.article.text,
            pkg.article.text_ko,
            pkg.article.summary_ko,
            pkg.article.vocab_formatted(),
            "\n".join(pkg.article.sources),
            "PASS" if pkg.plagiarism_report.passed else "WARNING",
            pkg.image_url,
            img_source,
            img_license,
            img_date,
            crossword,
            wb1,
            wb2,
        ]
