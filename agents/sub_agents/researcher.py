"""ResearcherAgent (Agent 0, P0-1) — 기사 작성 전 실시간 리서치.

흐름: 뉴스 검색 → 상위 2~4건 본문 수집 → Writer 컨텍스트로 주입.
출처는 실제 fetch한 기사 URL만 기록한다. 출처 미확보 시 success=False로
반환하여 파이프라인이 생성을 중단하도록 한다.

[변경 이력]
- 최초: Google Custom Search Engine (CSE) 사용
- 변경: Google CSE API가 403 오류(This project does not have the access to
  Custom Search JSON API)로 지속 차단되어 duckduckgo-search 라이브러리로
  교체. API 키 불필요, 동일한 검색 결과 반환.
"""

import logging
from typing import Callable

import requests
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS

from models import ResearchResult, SourceDoc

logger = logging.getLogger(__name__)

HEADERS = {"User-Agent": "Mozilla/5.0"}

MIN_BODY_CHARS = 200
MAX_SOURCES = 4
MAX_BODY_CHARS = 2500


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

        # 2) DuckDuckGo 검색으로 추가 출처 수집
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
                "(검색 결과 없음, 또는 기사 링크를 직접 입력해 주세요.)"
            )
            self._log(f"[Agent0] 리서치 실패 — {note}")
            return ResearchResult(success=False, sources=[], note=note)

        self._log(f"[Agent0] 리서치 완료 — 출처 {len(sources)}건 확보")
        return ResearchResult(success=True, sources=sources)

    # ------------------------------------------------------------------

    def _build_query(self, topic: str, section: str) -> str:
        base = topic.strip()
        # 한국어 토픽이면 영어 검색을 위해 "in English" 키워드 추가
        if self._is_korean(base):
            return f"{base} news 2024 2025"
        return f"{base} {section} news".strip()

    def _search(self, query: str) -> list[str]:
        try:
            self._log("[Agent0] DuckDuckGo 검색 중 (Google CSE → DDG로 변경)")
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=MAX_SOURCES + 2, region="wt-wt"))
            return [r.get("href", "") for r in results if r.get("href")]
        except Exception as e:
            self._log(f"[Agent0] 검색 오류 (무시하고 계속): {e}")
            return []

    def _is_korean(self, text: str) -> bool:
        return any("가" <= c <= "힣" for c in text)

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
