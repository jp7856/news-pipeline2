"""ResearcherAgent (Agent 0, P0-1) — 기사 작성 전 실시간 리서치.

흐름: 뉴스 검색 → 상위 2~4건 본문 수집 → Writer 컨텍스트로 주입.
출처는 실제 fetch한 기사 URL만 기록한다.

[변경 이력]
- 최초: Google Custom Search Engine (CSE) 사용
- 임시 변경: Google CSE 403 차단으로 NewsAPI.org로 교체
- 복귀: Google CSE 키 교체 후 정상화 — CSE 우선, 실패 시 NewsAPI 폴백
"""

import logging
from typing import Callable

import requests
from bs4 import BeautifulSoup

from config import GOOGLE_CSE_API_KEY, GOOGLE_CSE_ID, NEWSAPI_KEY, ANTHROPIC_API_KEY, CLAUDE_MODEL
from agents.token_meter import make_client
from models import ResearchResult, SourceDoc

logger = logging.getLogger(__name__)

CSE_URL = "https://www.googleapis.com/customsearch/v1"
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

        # 2) 검색으로 추가 출처 수집
        query = self._build_query(topic, section)
        for item in self._search(query):
            if len(sources) >= MAX_SOURCES:
                break
            url = item["url"]
            if url in seen_urls:
                continue
            doc = self._fetch(url)
            if doc and self._is_relevant(doc, query):
                sources.append(doc)
                seen_urls.add(url)
                self._log(f"[Agent0] 출처 수집: {doc.title[:40]}")
            elif doc:
                self._log(f"[Agent0] 무관 출처 제외: {doc.title[:40]}")

        if not sources:
            note = "관련 뉴스 출처를 찾지 못했습니다. Writer가 자체 지식으로 작성합니다."
            self._log("[Agent0] 관련 출처 없음 — Writer 자체 작성으로 진행")
            return ResearchResult(success=True, sources=[], note=note)

        self._log(f"[Agent0] 리서치 완료 — 출처 {len(sources)}건 확보")
        return ResearchResult(success=True, sources=sources)

    # ------------------------------------------------------------------

    _SECTION_EN = {
        "정치": "politics", "경제": "economy", "사회": "society",
        "세계": "world", "과학": "science", "기술": "technology",
        "환경": "environment", "건강": "health", "스포츠": "sports",
        "교육": "education", "문화": "culture", "엔터테인먼트": "entertainment",
        "비즈니스": "business", "사람": "people",
    }

    def _build_query(self, topic: str, section: str) -> str:
        base = topic.strip()
        if self._is_korean(base):
            base = self._translate_to_english(base)
        return base

    def _is_korean(self, text: str) -> bool:
        return any("가" <= c <= "힣" for c in text)

    def _translate_to_english(self, text: str) -> str:
        try:
            client = make_client(ANTHROPIC_API_KEY)
            msg = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=60,
                messages=[{
                    "role": "user",
                    "content": (
                        "Translate this Korean word/phrase to English for a news search query. "
                        "Reply with only the English translation, no explanation:\n" + text
                    ),
                }],
            )
            translated = msg.content[0].text.strip()
            self._log(f"[Agent0] 검색어 번역: {text} → {translated}")
            return translated
        except Exception as e:
            self._log(f"[Agent0] 번역 실패, 원문 사용: {e}")
            return text

    def _search(self, query: str) -> list[dict]:
        """CSE 우선 검색. 실패하거나 키 미설정 시 NewsAPI 폴백."""
        # ── Google CSE ──────────────────────────────────────────────
        if GOOGLE_CSE_API_KEY and GOOGLE_CSE_ID:
            results = self._search_cse(query)
            if results:
                return results
            self._log("[Agent0] CSE 결과 없음 — NewsAPI 폴백")
        else:
            self._log("[Agent0] CSE 키 미설정 — NewsAPI 사용")

        # ── NewsAPI 폴백 ─────────────────────────────────────────────
        return self._search_newsapi(query)

    def _search_cse(self, query: str) -> list[dict]:
        try:
            self._log(f"[Agent0] Google CSE 검색: {query}")
            resp = requests.get(
                CSE_URL,
                params={
                    "key": GOOGLE_CSE_API_KEY,
                    "cx": GOOGLE_CSE_ID,
                    "q": query,
                    "num": MAX_SOURCES + 2,
                },
                timeout=10,
            )
            if resp.status_code >= 400:
                self._log(f"[Agent0] CSE 오류 ({resp.status_code}): {resp.text[:200]}")
                return []
            items = resp.json().get("items", [])
            results = [{"url": it["link"], "title": it.get("title", "")}
                       for it in items if it.get("link")]
            self._log(f"[Agent0] CSE 결과 {len(results)}건")
            return results
        except Exception as e:
            self._log(f"[Agent0] CSE 오류 (무시하고 계속): {e}")
            return []

    # 교육용 신뢰 도메인 (NewsAPI 폴백 시 우선 적용)
    _SAFE_DOMAINS = (
        "bbc.com,reuters.com,apnews.com,nationalgeographic.com,"
        "smithsonianmag.com,sciencenews.org,newscientist.com,"
        "theguardian.com,npr.org,time.com,scientificamerican.com"
    )

    def _search_newsapi(self, query: str) -> list[dict]:
        if not NEWSAPI_KEY:
            self._log("[Agent0] NEWSAPI_KEY 미설정")
            return []
        try:
            self._log(f"[Agent0] NewsAPI 검색: {query}")
            candidates = self._fetch_newsapi(query, domains=self._SAFE_DOMAINS)
            relevant = self._title_filter(candidates, query)
            self._log(f"[Agent0] NewsAPI 교육 도메인: {len(candidates)}건 → 제목 필터 후 {len(relevant)}건")

            if len(relevant) < 2:
                all_candidates = self._fetch_newsapi(query, domains=None)
                all_relevant = self._title_filter(all_candidates, query)
                self._log(f"[Agent0] NewsAPI 전체 도메인 재시도: {len(all_candidates)}건 → {len(all_relevant)}건")
                seen = {r["url"] for r in relevant}
                for item in all_relevant:
                    if item["url"] not in seen:
                        relevant.append(item)
                        seen.add(item["url"])
            return relevant
        except Exception as e:
            self._log(f"[Agent0] NewsAPI 오류 (무시하고 계속): {e}")
            return []

    def _fetch_newsapi(self, query: str, domains: str | None) -> list[dict]:
        params = {
            "apiKey": NEWSAPI_KEY,
            "q": query,
            "language": "en",
            "sortBy": "relevancy",
            "pageSize": MAX_SOURCES * 3,
        }
        if domains:
            params["domains"] = domains
        resp = requests.get(NEWSAPI_URL, params=params, timeout=10)
        if resp.status_code >= 400:
            self._log(f"[Agent0] NewsAPI 오류 ({resp.status_code}): {resp.text[:200]}")
            return []
        articles = resp.json().get("articles", [])
        return [{"url": a["url"], "title": a.get("title", "")}
                for a in articles if a.get("url")]

    def _title_filter(self, candidates: list[dict], query: str) -> list[dict]:
        keywords = [w.lower() for w in query.split() if len(w) > 2]
        if not keywords:
            return candidates
        return [item for item in candidates
                if any(kw in item.get("title", "").lower() for kw in keywords)]

    def _is_relevant(self, doc: SourceDoc, query: str) -> bool:
        keywords = [w.lower() for w in query.split() if len(w) > 2]
        if not keywords:
            return True
        combined = (doc.title + " " + doc.text[:800]).lower()
        matches = sum(1 for kw in keywords if kw in combined)
        return matches >= max(1, len(keywords) // 2)

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
