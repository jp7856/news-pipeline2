#!/usr/bin/env python3
"""Validate an NE Times article draft.

Checks:
  1. Word count (Microsoft Word standard: whitespace-delimited tokens)
  2. Citation artifacts left by LLMs (e.g. "위키백과+1", "SBS 뉴스" inline tags)
  3. Long verbatim overlap with source text (optional, --sources)
  4. Source URL liveness (optional, --check-urls)

Usage:
  python validate.py draft.txt --min 270 --max 280
  python validate.py draft.txt --min 270 --max 280 --sources sources.txt --check-urls

Exit code 0 = all checks passed, 1 = at least one failure.
The draft file should contain ONLY the article body (headline optional via
--include-headline; by default the first line is treated as the headline and
excluded from the count, matching production practice — pass --count-all to
count every line).
"""
import argparse
import re
import sys
import unicodedata


def ms_word_count(text: str) -> int:
    """Microsoft Word counts contiguous non-whitespace runs as words."""
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


def find_artifacts(text: str):
    hits = []
    for pat, label in ARTIFACT_PATTERNS:
        for m in re.finditer(pat, text):
            hits.append((label, m.group(0)))
    return hits


def ngram_overlap(article: str, source: str, n: int = 8):
    """Return verbatim n-gram (default 8-word) sequences shared with source."""
    def norm_tokens(t):
        t = unicodedata.normalize("NFKC", t.lower())
        return re.findall(r"[a-z0-9']+", t)

    a_tok, s_tok = norm_tokens(article), norm_tokens(source)
    s_grams = {tuple(s_tok[i:i + n]) for i in range(max(0, len(s_tok) - n + 1))}
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


def check_urls(urls):
    import urllib.request
    results = []
    for u in urls:
        try:
            req = urllib.request.Request(u, method="HEAD",
                                         headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as r:
                results.append((u, r.status < 400, r.status))
        except Exception as e:
            results.append((u, False, str(e)[:60]))
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("draft")
    ap.add_argument("--min", type=int, required=True)
    ap.add_argument("--max", type=int, required=True)
    ap.add_argument("--sources", help="file with source article text for overlap check")
    ap.add_argument("--check-urls", action="store_true",
                    help="HEAD-request every http(s) URL found in --sources file")
    ap.add_argument("--count-all", action="store_true",
                    help="count every line incl. first (default: first line = headline, excluded)")
    args = ap.parse_args()

    text = open(args.draft, encoding="utf-8").read().strip()
    lines = text.splitlines()
    body = text if args.count_all else "\n".join(lines[1:]).strip()
    # subheadings are part of the body count, matching MS Word behavior
    ok = True

    wc = ms_word_count(body)
    in_range = args.min <= wc <= args.max
    ok &= in_range
    print(f"[{'PASS' if in_range else 'FAIL'}] word count: {wc} "
          f"(target {args.min}–{args.max}"
          f"{'' if args.count_all else ', headline excluded'})")

    artifacts = find_artifacts(body)
    if artifacts:
        ok = False
        print(f"[FAIL] citation artifacts found ({len(artifacts)}):")
        for label, frag in artifacts:
            print(f"   - {frag!r}  ({label})")
    else:
        print("[PASS] no citation artifacts")

    if args.sources:
        src = open(args.sources, encoding="utf-8").read()
        overlaps = ngram_overlap(body, src)
        if overlaps:
            ok = False
            print(f"[FAIL] verbatim overlap with source (≥8 consecutive words):")
            for o in overlaps:
                print(f"   - \"{o}\"")
        else:
            print("[PASS] no long verbatim overlap with source text")
        if args.check_urls:
            urls = re.findall(r"https?://\S+", src)
            for u, alive, status in check_urls(urls):
                tag = "PASS" if alive else "WARN"
                if not alive:
                    print(f"[{tag}] source URL unreachable ({status}): {u}")
                else:
                    print(f"[{tag}] source URL ok: {u}")

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
