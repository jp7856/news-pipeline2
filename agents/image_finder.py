"""Agent 3: 이미지 탐색 — Google Custom Search API로 기사 관련 이미지를 찾는다."""

import logging
from typing import Callable

import requests

from config import GOOGLE_CSE_API_KEY, GOOGLE_CSE_ID
from models import ContentPackage

logger = logging.getLogger(__name__)

SEARCH_URL = "https://www.googleapis.com/customsearch/v1"


class ImageFinderAgent:
    def __init__(self, log_callback: Callable[[str], None] | None = None):
        self._log = log_callback or (lambda msg: logger.info(msg))

    def run(self, package: ContentPackage) -> ContentPackage:
        self._log("[Agent3] 이미지 탐색 시작")
        query = self._build_query(package)
        self._log(f"[Agent3] 검색어: {query}")
        try:
            url = self._search_image(query)
            if url:
                package.image_url = url
                self._log(f"[Agent3] 이미지 발견: {url[:80]}...")
            else:
                self._log("[Agent3] 이미지를 찾지 못했습니다.")
        except Exception as e:
            self._log(f"[Agent3] 이미지 탐색 오류: {e}")
        self._log("[Agent3] 이미지 탐색 완료")
        return package

    # ------------------------------------------------------------------

    def _build_query(self, package: ContentPackage) -> str:
        """topic + 섹션으로 뉴스형 이미지 검색어를 구성한다."""
        return f"{package.topic} {package.section.value} news"

    def _search_image(self, query: str) -> str | None:
        if not GOOGLE_CSE_API_KEY or not GOOGLE_CSE_ID:
            return None

        params = {
            "key": GOOGLE_CSE_API_KEY,
            "cx": GOOGLE_CSE_ID,
            "q": query,
            "searchType": "image",
            "num": 1,
            "safe": "active",
            "imgType": "news",
        }
        resp = requests.get(SEARCH_URL, params=params, timeout=10)
        resp.raise_for_status()
        items = resp.json().get("items", [])
        if items:
            return items[0].get("link", "")
        return None
