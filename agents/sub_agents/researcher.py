"""ResearcherAgent (Agent 0, P0-1) — 기사 작성 전 실시간 리서치.

흐름: 뉴스 검색 → 상위 2~4건 본문 수집 → Writer 컨텍스트로 주입.
출처는 실제 fetch한 기사 URL만 기록한다. 출처 미확보 시 success=False로
반환하여 파이프라인이 생성을 중단하도록 한다.

[변경 이력]
- 최초: Google Custom Search Engine (CSE) 사용
- 변경: Google CSE API가 Google 계정 수준에서 지속 차단(403)되어
  NewsAPI.org로 교체. 동일한 실시간 뉴스 검색 기능 제공.
"""

import logging
from typing import Callable

import requests
from bs4 import BeautifulSoup

from config import NEWSAPI_KEY
from models import ResearchResult, SourceDoc

logger = logging.getLogger(__name__)

NEWSAPI_URL = "https://newsapi.org/v2/everything"
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

        # 2) NewsAPI로 추가 출처 수집
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
                "(NEWSAPI_KEY 미설정이거나 검색 결과 없음, "
                "또는 기사 링크를 직접 입력해 주세요.)"
            )
            self._log(f"[Agent0] 리서치 실패 — {note}")
            return ResearchResult(success=False, sources=[], note=note)

        self._log(f"[Agent0] 리서치 완료 — 출처 {len(sources)}건 확보")
        return ResearchResult(success=True, sources=sources)

    # ------------------------------------------------------------------

    def _build_query(self, topic: str, section: str) -> str:
        base = topic.strip()
        return f"{base} {section}".strip()

    def _search(self, query: str) -> list[str]:
        if not NEWSAPI_KEY:
            self._log("[Agent0] NEWSAPI_KEY 미설정")
            return []
        try:
            self._log("[Agent0] GSE 검색 차단으로 newsapi.org로 변경")
            resp = requests.get(
                NEWSAPI_URL,
                params={
                    "apiKey": NEWSAPI_KEY,
                    "q": query,
                    "language": "en",
                    "sortBy": "publishedAt",
                    "pageSize": MAX_SOURCES + 2,
                },
                timeout=10,
            )
            if resp.status_code >= 400:
                self._log(f"[Agent0] NewsAPI 오류 ({resp.status_code}): {resp.text[:200]}")
                return []
            articles = resp.json().get("articles", [])
            urls = [a.get("url", "") for a in articles if a.get("url")]
            self._log(f"[Agent0] 검색 결과 {len(urls)}건 수신")
            return urls
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
