"""Agent 3: 이미지 탐색 — Unsplash API로 기사 관련 이미지를 자동 선택한다."""

import logging
from typing import Callable

import requests

from config import UNSPLASH_ACCESS_KEY
from models import ContentPackage

logger = logging.getLogger(__name__)

UNSPLASH_URL = "https://api.unsplash.com/search/photos"


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

    def _build_query(self, package: ContentPackage) -> str:
        # 영어 어휘가 있으면 우선 사용 (한국어 토픽은 Unsplash 검색 안 됨)
        if package.article.vocabulary:
            keywords = " ".join(package.article.vocabulary[:4])
            return keywords
        # 폴백: 토픽이 영어인 경우
        return package.topic

    def _search_image(self, query: str) -> str | None:
        if not UNSPLASH_ACCESS_KEY:
            return None
        resp = requests.get(
            UNSPLASH_URL,
            params={"query": query, "per_page": 1, "orientation": "landscape"},
            headers={"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"},
            timeout=10,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if results:
            return results[0]["urls"]["regular"]
        return None
