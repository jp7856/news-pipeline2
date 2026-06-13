"""검증 유틸리티 — ne-times-issue 스킬 scripts/validate.py 로직 이식.

- 단어수 (Microsoft Word 기준: 공백 구분 토큰)
- LLM 인용 아티팩트 탐지 ("위키백과+1", "[1]" 등)
- 출처 원문과의 장문 축자 중복 (8단어 연속)
- 출처 URL 생존 확인 (HEAD)
"""

import re
import unicodedata
import urllib.request


def ms_word_count(text: str) -> int:
    """MS Word는 공백으로 구분된 연속 비공백 토큰을 단어로 센다."""
    return len(text.split())


ARTIFACT_PATTERNS = [
    (r"[가-힣A-Za-z]+\+\d+", "citation artifact like '위키백과+1'"),
    (r"\[\d+\]", "bracketed citation number like [1]"),
    (r"\((?:source|Source|출처)[::]?\s*[^)]*\)", "inline (source: ...) note"),
    (r"(SBS 뉴스|ZUM 뉴스|위키백과|네이버 뉴스)(?=\s|$)",
     "Korean outlet name pasted into body text"),
    (r"【[^】]*】", "【...】 bracket artifact"),
    (r"turn\d+(search|news|view)\d+", "model citation token"),
]


def find_artifacts(text: str) -> list[tuple[str, str]]:
    hits = []
    for pat, label in ARTIFACT_PATTERNS:
        for m in re.finditer(pat, text):
            hits.append((label, m.group(0)))
    return hits


def ngram_overlap(article: str, source: str, n: int = 8) -> list[str]:
    """출처와 공유하는 축자 n-gram(기본 8단어) 시퀀스 반환."""
    def norm_tokens(t):
        t = unicodedata.normalize("NFKC", t.lower())
        return re.findall(r"[a-z0-9']+", t)

    a_tok, s_tok = norm_tokens(article), norm_tokens(source)
    if len(s_tok) < n:
        return []
    s_grams = {tuple(s_tok[i:i + n]) for i in range(len(s_tok) - n + 1)}
    hits, i = [], 0
    while i <= len(a_tok) - n:
        if tuple(a_tok[i:i + n]) in s_grams:
            j = i + n
            while j < len(a_tok) and tuple(a_tok[j - n + 1:j + 1]) in s_grams:
                j += 1
            hits.append(" ".join(a_tok[i:j]))
            i = j
        else:
            i += 1
    return hits


def check_url_alive(url: str, timeout: int = 10) -> bool:
    try:
        req = urllib.request.Request(
            url, method="HEAD", headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status < 400
    except Exception:
        return False


def word_count_in_range(text: str, lo: int, hi: int) -> tuple[bool, int]:
    wc = ms_word_count(text)
    return (lo <= wc <= hi, wc)
