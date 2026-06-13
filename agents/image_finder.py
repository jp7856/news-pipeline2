"""Agent 3: 이미지 탐색 (P1-3) — 기사 주제·핵심 장면 기반으로 검색어를 생성하고
Unsplash에서 후보를 수집해 관련성으로 추천한다. 라이선스 증빙을 기록한다.

원인 해결: F-5(검색어가 어휘 나열이라 무관한 사진 추천 — 설계 결함).
정책: references/image-licensing.md — 검색어는 vocabulary가 아니라 기사의
subject와 key scene에서 도출. 인물 사진·로고는 배제 지향.
"""

import json
import logging
from datetime import datetime
from typing import Callable

import anthropic
import requests

from config import UNSPLASH_ACCESS_KEY, ANTHROPIC_API_KEY, CLAUDE_MODEL
from models import ContentPackage, ImageCandidate
from agents.sub_agents.utils import parse_json

logger = logging.getLogger(__name__)

UNSPLASH_URL = "https://api.unsplash.com/search/photos"
CANDIDATE_COUNT = 5


class ImageFinderAgent:
    def __init__(self, log_callback: Callable[[str], None] | None = None):
        self._log = log_callback or (lambda msg: logger.info(msg))
        self._client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    def run(self, package: ContentPackage) -> ContentPackage:
        self._log("[Agent3] 이미지 탐색 시작")
        try:
            query = self._generate_query(package)
            package.image_query = query
            self._log(f"[Agent3] 주제·장면 기반 검색어: {query}")

            candidates = self._search_candidates(query)
            if not candidates:
                self._log("[Agent3] 이미지 후보를 찾지 못했습니다.")
                return package
            package.image_candidates = candidates

            best = self._pick_relevant(package, candidates)
            package.image_selected = best
            package.image_url = best.url
            self._log(
                f"[Agent3] 추천: {best.photographer} ({best.source}/{best.license}) "
                f"후보 {len(candidates)}건 중 선택"
            )
        except Exception as e:
            self._log(f"[Agent3] 이미지 탐색 오류: {e}")
        self._log("[Agent3] 이미지 탐색 완료")
        return package

    # ------------------------------------------------------------------

    def _generate_query(self, package: ContentPackage) -> str:
        """기사 주제·핵심 장면에서 영어 검색어를 생성 (어휘 나열 금지)."""
        summary = package.article.summary_ko or package.article.text[:600]
        prompt = f"""You are picking a news photo for an article. Produce ONE short English
image-search query (3-6 words) describing the article's MAIN SUBJECT or KEY SCENE
— what a photo should literally show. Do NOT just concatenate vocabulary words.
Avoid identifiable individual people, logos, and trademarked characters.

Topic: {package.topic}
Section: {package.section.value}
Article summary: {summary[:800]}

Respond in this exact JSON format:
{{"query": "short visual search phrase"}}"""
        try:
            msg = self._client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=120,
                messages=[{"role": "user", "content": prompt}],
            )
            data = parse_json(msg.content[0].text)
            q = (data.get("query") or "").strip()
            if q:
                return q
        except Exception as e:
            self._log(f"[Agent3] 검색어 생성 실패, 폴백 사용: {e}")
        # 폴백: 토픽 + 섹션
        return f"{package.topic} {package.section.value}".strip()

    def _search_candidates(self, query: str) -> list[ImageCandidate]:
        if not UNSPLASH_ACCESS_KEY:
            return []
        resp = requests.get(
            UNSPLASH_URL,
            params={"query": query, "per_page": CANDIDATE_COUNT, "orientation": "landscape"},
            headers={"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"},
            timeout=10,
        )
        resp.raise_for_status()
        today = datetime.now().strftime("%Y-%m-%d")
        out = []
        for r in resp.json().get("results", []):
            out.append(ImageCandidate(
                url=r["urls"]["regular"],
                thumb=r["urls"].get("thumb", ""),
                description=r.get("description") or r.get("alt_description") or "",
                photographer=(r.get("user") or {}).get("name", ""),
                source="Unsplash",
                license="Unsplash License (commercial OK, attribution appreciated)",
                page_url=(r.get("links") or {}).get("html", ""),
                confirmed_date=today,
            ))
        return out

    def _pick_relevant(self, package: ContentPackage, candidates: list[ImageCandidate]) -> ImageCandidate:
        """후보 설명을 보고 기사 주제와 가장 잘 맞는 1건을 고른다."""
        if len(candidates) == 1:
            return candidates[0]
        listing = "\n".join(
            f"{i}: {c.description or '(no description)'}" for i, c in enumerate(candidates)
        )
        prompt = f"""Choose the image whose description best matches the article subject
and would read clearly as a news photo for it. Avoid images centered on an
identifiable individual person or a logo.

Topic: {package.topic}
Section: {package.section.value}

Candidates:
{listing}

Respond in this exact JSON format:
{{"index": 0}}"""
        try:
            msg = self._client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=60,
                messages=[{"role": "user", "content": prompt}],
            )
            idx = int(parse_json(msg.content[0].text).get("index", 0))
            if 0 <= idx < len(candidates):
                return candidates[idx]
        except Exception as e:
            self._log(f"[Agent3] 관련성 판정 실패, 첫 후보 사용: {e}")
        return candidates[0]
