"""ResearcherAgent (Agent 0, P0-1) — 기사 작성 전 실시간 리서치.

흐름: 뉴스 검색 → 상위 2~4건 본문 수집 → Writer 컨텍스트로 주입.
출처는 실제 fetch한 기사 URL만 기록한다. 출처 미확보 시 success=False로
반환하여 파이프라인이 생성을 중단하도록 한다.

원인 해결: F-1(실시간 웹 리서치 부재). config의 GOOGLE_CSE_API_KEY/
GOOGLE_CSE_ID와 기존 의존성 BeautifulSoup4를 사용한다.
"""

import logging
from typing import Callable

import requests
from bs4 import BeautifulSoup

from config import GOOGLE_CSE_API_KEY, GOOGLE_CSE_ID
from models import ResearchResult, SourceDoc

logger = logging.getLogger(__name__)

CSE_URL = "https://www.googleapis.com/customsearch/v1"
HEADERS = {"User-Agent": "Mozilla/5.0"}

MIN_BODY_CHARS = 200      # 본문으로 인정할 최소 길이
MAX_SOURCES = 4
MAX_BODY_CHARS = 2500     # 출처당 본문 최대 길이 (토큰 절약)


class ResearcherAgent:
    def __init__(self, log_callback: Callable[[str], None] | None = None):
        self._log = log_callback or (lambda msg: logger.info(msg))

    def run(self, topic: str, section: str = "", source_url: str = "") -> ResearchResult:
        self._log("[Agent0] 실시간 리서치 시작")
        sources: list[SourceDoc] = []
        seen_urls: set[str] = set()

        # 1) 사용자가 링크를 제공했으면 우선 수집
        if source_url:
            doc = self._fetch(source_url)
            if doc:
                sources.append(doc)
                seen_urls.add(source_url)
                self._log(f"[Agent0] 제공 링크 수집: {doc.title[:40]}")

        # 2) 검색으로 추가 출처 수집 (corroboration)
        query = self._build_query(topic, section)
        for url in self._search(query):
            if len(sources) >= MAX_SOURCES:
                break
            if url in seen_urls:
                continue
            doc = self._fetch(url)
            if doc:
                sources.append(doc)
                seen_urls.add(url)
                self._log(f"[Agent0] 출처 수집: {doc.title[:40]}")

        if not sources:
            note = (
                "사용 가능한 출처를 확보하지 못했습니다. "
                "(GOOGLE_CSE_API_KEY/GOOGLE_CSE_ID 미설정이거나 검색 결과 없음, "
                "또는 기사 링크를 직접 입력해 주세요.)"
            )
            self._log(f"[Agent0] 리서치 실패 — {note}")
            return ResearchResult(success=False, sources=[], note=note)

        self._log(f"[Agent0] 리서치 완료 — 출처 {len(sources)}건 확보")
        return ResearchResult(success=True, sources=sources)

    # ------------------------------------------------------------------

    def _build_query(self, topic: str, section: str) -> str:
        # URL이 토픽으로 들어온 경우 검색어로 부적절 → 그대로 두되 news 키워드 추가
        base = topic.strip()
        return f"{base} {section} news".strip()

    def _search(self, query: str) -> list[str]:
        if not GOOGLE_CSE_API_KEY or not GOOGLE_CSE_ID:
            return []
        try:
            resp = requests.get(
                CSE_URL,
                params={
                    "key": GOOGLE_CSE_API_KEY,
                    "cx": GOOGLE_CSE_ID,
                    "q": query,
                    "num": MAX_SOURCES + 2,
                    "safe": "active",
                },
                timeout=10,
            )
            if resp.status_code >= 400:
                # Google 오류 사유를 본문에서 추출 (403 원인 진단용)
                reason = ""
                try:
                    err = resp.json().get("error", {})
                    reason = err.get("message", "") or str(err.get("errors", ""))
                except Exception:
                    reason = resp.text[:200]
                self._log(f"[Agent0] 검색 거부 ({resp.status_code}): {reason}")
                return []
            items = resp.json().get("items", [])
            return [it.get("link", "") for it in items if it.get("link")]
        except Exception as e:
            self._log(f"[Agent0] 검색 오류 (무시하고 계속): {e}")
            return []

    def _fetch(self, url: str) -> SourceDoc | None:
        try:
            resp = requests.get(url, timeout=10, headers=HEADERS)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()

            title = (soup.title.get_text(strip=True) if soup.title else url)[:120]
            paragraphs = [
                p.get_text(strip=True)
                for p in soup.find_all("p")
                if len(p.get_text(strip=True)) > 40
            ]
            body = "\n".join(paragraphs)
            if len(body) < MIN_BODY_CHARS:
                return None
            return SourceDoc(url=url, title=title, text=body[:MAX_BODY_CHARS])
        except Exception as e:
            self._log(f"[Agent0] 수집 실패 ({url[:50]}): {e}")
            return None
