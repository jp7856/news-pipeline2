"""토큰 사용량·비용 집계 — 모든 Claude 호출을 감싸 usage를 월별로 모은다.

make_client()로 만든 클라이언트의 messages.create() 응답 usage가 전역 meter에
자동 누적된다. 사용량은 **월(YYYY-MM) 단위로 버킷**에 쌓이며, 매월 1일이 되면
새 월 버킷이 시작되어 자동으로 0부터 다시 누적된다(월별 초기화 + 월내 지속 누적).
token_usage.json 파일에 영속화하여 서버 재기동에도 유지된다.
"""

import json
import threading
from datetime import datetime
from pathlib import Path

import anthropic

from config import (
    ANTHROPIC_API_KEY,
    PRICE_INPUT_PER_M, PRICE_OUTPUT_PER_M,
    PRICE_CACHE_WRITE_PER_M, PRICE_CACHE_READ_PER_M,
)

USAGE_FILE = Path(__file__).resolve().parent.parent / "token_usage.json"


def _month_key() -> str:
    return datetime.now().strftime("%Y-%m")


class TokenMeter:
    def __init__(self):
        self._lock = threading.Lock()
        self._months: dict[str, dict] = {}   # "YYYY-MM" -> 집계
        self._load()

    @staticmethod
    def _blank() -> dict:
        return {"calls": 0, "input_tokens": 0, "output_tokens": 0,
                "cache_write_tokens": 0, "cache_read_tokens": 0}

    # ------------------------------------------------------------------
    # Google Sheets 영속화 (Railway ephemeral 파일시스템 대응)
    # ------------------------------------------------------------------

    @staticmethod
    def _get_token_sheet():
        """'token_usage' 탭 반환 — 없으면 생성."""
        import json as _json
        from config import GOOGLE_SHEETS_CREDENTIALS_JSON, GOOGLE_SHEET_ID
        import gspread
        from google.oauth2.service_account import Credentials
        SCOPES = ["https://www.googleapis.com/auth/spreadsheets",
                  "https://www.googleapis.com/auth/drive"]
        creds_val = (GOOGLE_SHEETS_CREDENTIALS_JSON or "").strip()
        if creds_val.startswith("{"):
            info = _json.loads(creds_val)
        else:
            from pathlib import Path as _P
            info = _json.loads(_P(creds_val).read_text(encoding="utf-8"))
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
        gc = gspread.authorize(creds)
        ss = gc.open_by_key(GOOGLE_SHEET_ID)
        try:
            return ss.worksheet("token_usage")
        except gspread.exceptions.WorksheetNotFound:
            ws = ss.add_worksheet(title="token_usage", rows=2, cols=1)
            ws.update("A1", [["{}"]],value_input_option="RAW")
            return ws

    def _load_from_sheets(self) -> dict:
        ws = self._get_token_sheet()
        raw = ws.acell("A1").value or "{}"
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}

    def _save_to_sheets(self) -> None:
        ws = self._get_token_sheet()
        ws.update("A1", [[json.dumps(self._months, ensure_ascii=False)]],
                  value_input_option="RAW")

    # ------------------------------------------------------------------

    def _load(self) -> None:
        # 1) 로컬 파일 우선
        try:
            if USAGE_FILE.exists():
                data = json.loads(USAGE_FILE.read_text(encoding="utf-8"))
                if isinstance(data, dict) and data:
                    self._months = data
                    return
        except Exception:
            pass
        # 2) 로컬 없으면 구글 시트에서 복원
        try:
            self._months = self._load_from_sheets()
        except Exception:
            self._months = {}

    def _save(self) -> None:
        # 로컬 파일
        try:
            USAGE_FILE.write_text(
                json.dumps(self._months, ensure_ascii=False, indent=1), encoding="utf-8"
            )
        except Exception:
            pass
        # 구글 시트 백업 (best-effort)
        try:
            self._save_to_sheets()
        except Exception:
            pass

    def add(self, usage) -> None:
        if usage is None:
            return
        with self._lock:
            m = self._months.setdefault(_month_key(), self._blank())
            m["calls"] += 1
            m["input_tokens"] += getattr(usage, "input_tokens", 0) or 0
            m["output_tokens"] += getattr(usage, "output_tokens", 0) or 0
            m["cache_write_tokens"] += getattr(usage, "cache_creation_input_tokens", 0) or 0
            m["cache_read_tokens"] += getattr(usage, "cache_read_input_tokens", 0) or 0
            self._save()

    @staticmethod
    def _total(m: dict) -> int:
        return (m["input_tokens"] + m["output_tokens"]
                + m["cache_write_tokens"] + m["cache_read_tokens"])

    @staticmethod
    def _cost(m: dict) -> float:
        return (
            m["input_tokens"] / 1_000_000 * PRICE_INPUT_PER_M
            + m["output_tokens"] / 1_000_000 * PRICE_OUTPUT_PER_M
            + m["cache_write_tokens"] / 1_000_000 * PRICE_CACHE_WRITE_PER_M
            + m["cache_read_tokens"] / 1_000_000 * PRICE_CACHE_READ_PER_M
        )

    def snapshot(self) -> dict:
        """이번 달 누적값 (대시보드 우측 표시용)."""
        with self._lock:
            mk = _month_key()
            m = self._months.get(mk, self._blank())
            return {
                "month": mk,
                "calls": m["calls"],
                "input_tokens": m["input_tokens"],
                "output_tokens": m["output_tokens"],
                "cache_write_tokens": m["cache_write_tokens"],
                "cache_read_tokens": m["cache_read_tokens"],
                "total_tokens": self._total(m),
                "cost_usd": round(self._cost(m), 4),
            }

    def monthly(self) -> list[dict]:
        """월별 집계 목록 (그래프용, 오름차순)."""
        with self._lock:
            out = []
            for mk in sorted(self._months):
                m = self._months[mk]
                out.append({
                    "month": mk,
                    "calls": m["calls"],
                    "total_tokens": self._total(m),
                    "cost_usd": round(self._cost(m), 4),
                })
            return out


# 전역 미터 (월별 버킷 + 파일 영속화)
meter = TokenMeter()


class _MeteredMessages:
    def __init__(self, inner):
        self._inner = inner

    def create(self, *args, **kwargs):
        resp = self._inner.create(*args, **kwargs)
        try:
            meter.add(getattr(resp, "usage", None))
        except Exception:
            pass
        return resp

    def __getattr__(self, name):
        return getattr(self._inner, name)


class MeteredAnthropic:
    """anthropic.Anthropic 래퍼 — messages.create 응답 usage를 전역 meter에 누적."""
    def __init__(self, **kwargs):
        self._client = anthropic.Anthropic(**kwargs)
        self.messages = _MeteredMessages(self._client.messages)

    def __getattr__(self, name):
        return getattr(self._client, name)


def make_client(api_key: str | None = None) -> MeteredAnthropic:
    return MeteredAnthropic(api_key=api_key or ANTHROPIC_API_KEY)
