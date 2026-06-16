"""WorkbookAgent — 기사 기반 워크북 활동지를 레거시 8종 포맷으로 생성한다 (P1-2).

지면(PAGE_CONFIG)이 지정한 workbook_format에 따라 skill_assets의
workbook-formats.md에서 해당 포맷 정의를 로드하여 프롬프트로 사용한다.
페르소나 규칙에 따라 이해·토론 문제는 2세트를 생성한다.
"""

import logging
import re
from pathlib import Path
from typing import Callable

import anthropic

from config import CLAUDE_MODEL, SYSTEM_PROMPT, LEVEL_CONFIG, WORKBOOK_FORMATS
from models import ArticleResult, WorkbookSet, WorkbookActivity, Level
from agents.sub_agents.utils import parse_json_loose as parse_json

logger = logging.getLogger(__name__)

FORMATS_MD = (
    Path(__file__).resolve().parent.parent.parent
    / "skill_assets" / "ne-times-issue" / "references" / "workbook-formats.md"
)


def load_format_spec(format_key: str) -> tuple[str, str]:
    """workbook-formats.md에서 해당 포맷 섹션 본문을 추출한다.
    Returns: (format_name, spec_text). 실패 시 ('', '')."""
    name = WORKBOOK_FORMATS.get(format_key, "")
    if not name or not FORMATS_MD.exists():
        return name, ""
    text = FORMATS_MD.read_text(encoding="utf-8")
    # [Workbook format: <name>] ~ 다음 [Workbook ...] 헤더 직전까지.
    # 줄 시작(^) 기준으로 한정해 상단 목차(TOC) 항목("1. [Workbook...")은 제외.
    headers = list(re.finditer(r"^\[Workbook [Ff]ormat:[^\]]*\]", text, re.MULTILINE))
    for i, m in enumerate(headers):
        header = m.group(0)
        if name.lower() in header.lower():
            start = m.end()
            end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
            return name, text[start:end].strip()
    return name, ""


class WorkbookAgent:
    def __init__(
        self,
        client: anthropic.Anthropic,
        log_callback: Callable[[str], None] | None = None,
    ):
        self._client = client
        self._log = log_callback or (lambda msg: logger.info(msg))

    def run(
        self,
        article: ArticleResult,
        level: Level,
        format_key: str | None = None,
    ) -> list[WorkbookSet]:
        cfg = LEVEL_CONFIG[level.value]
        # 포맷 미지정 시 레벨 기반 폴백
        if not format_key:
            format_key = self._default_format(level)
        format_name, spec = load_format_spec(format_key)
        self._log(f"[Workbook] 포맷 [{format_name or format_key}] 2세트 생성 시작")

        vocab_list = ", ".join(article.vocabulary) if article.vocabulary else "N/A"
        spec_block = (
            f"\n\nFOLLOW THIS EXACT WORKBOOK FORMAT SPEC:\n\"\"\"\n{spec}\n\"\"\""
            if spec else ""
        )

        prompt = f"""Create TWO complete sets of workbook activities for the article below,
for {cfg['newspaper']} students (CEFR {cfg['cefr']}, {cfg['target']}).
{spec_block}

Key vocabulary from the article: {vocab_list}

Rules:
- Produce the four activities (A/B/C/D) exactly as the format spec defines, plus
  the Extra Activity (phrasal verbs) if the spec includes one.
- Activity D is always Comprehension + Discussion questions.
- Make Set 1 and Set 2 distinct (no overlapping answers/content).
- Include the answer key for each activity that has answers.

Article:
\"\"\"
{article.text}
\"\"\"

Respond in this exact JSON format (no double quotes inside string values):
{{
  "workbook_sets": [
    {{
      "set_number": 1,
      "activities": [
        {{"label": "A", "title": "...", "instruction": "...", "body": "...", "answer": "..."}},
        {{"label": "B", "title": "...", "instruction": "...", "body": "...", "answer": "..."}},
        {{"label": "C", "title": "...", "instruction": "...", "body": "...", "answer": "..."}},
        {{"label": "D", "title": "Comprehension and Discussion", "instruction": "...", "body": "Comprehension:\\n1...\\nDiscussion:\\n1...", "answer": ""}},
        {{"label": "Extra", "title": "Phrasal Verbs", "instruction": "...", "body": "...", "answer": "..."}}
      ]
    }},
    {{"set_number": 2, "activities": [ ... ]}}
  ]
}}"""

        data = self._call_claude(prompt)
        sets = []
        for i, s in enumerate(data.get("workbook_sets", [])):
            activities = [
                WorkbookActivity(
                    label=a.get("label", ""),
                    title=a.get("title", ""),
                    instruction=a.get("instruction", ""),
                    body=a.get("body", ""),
                    answer=a.get("answer", ""),
                )
                for a in s.get("activities", [])
            ]
            sets.append(WorkbookSet(
                set_number=s.get("set_number", i + 1),
                format_key=format_key,
                format_name=format_name,
                activities=activities,
            ))

        self._log(f"[Workbook] 완료 — {len(sets)}세트 / 포맷 {format_name or format_key}")
        return sets

    # ------------------------------------------------------------------

    def _default_format(self, level: Level) -> str:
        return {
            Level.KINDER: "L1_TF",
            Level.KIDS:   "L1_MCQ",
            Level.JUNIOR: "L1_MCQ",
            Level.TIMES:  "L2_ABC",
        }.get(level, "L1_MCQ")

    def _call_claude(self, prompt: str) -> dict:
        message = self._client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=4000,
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": prompt}],
        )
        return parse_json(message.content[0].text)
