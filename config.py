import os
from dotenv import load_dotenv

load_dotenv(override=True)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-sonnet-4-6"

GOOGLE_SHEETS_CREDENTIALS_JSON = os.getenv("GOOGLE_SHEETS_CREDENTIALS_JSON", "credentials.json")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")

GOOGLE_CSE_API_KEY = os.getenv("GOOGLE_CSE_API_KEY", "")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID", "")
UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY", "VLRkU7wWplDXzMjkBFFqvhVrR_orC10qFcHOApNkrTc")

MAX_ARTICLES_PER_RUN = int(os.getenv("MAX_ARTICLES_PER_RUN", "10"))

# ------------------------------------------------------------------
# 오케스트레이터 시스템 페르소나 (모든 서브에이전트 공유 — 프롬프트 캐싱)
# ------------------------------------------------------------------
SYSTEM_PROMPT = """You are a writer and editor of an English education for children and teens. \
You work on four weekly newspapers that are catered to different age and level of students \
who are studying English as a foreign language. \
The lowest is called NE Times Kinder and it is for kindergarteners and early elementary school \
students, and the language level is at CEFR level of A1 or lower. \
The next newspaper is called NE Times Kids and it is for elementary school students studying \
at a CEFR level of around A2 or A1-A2. \
The third newspaper is called NE Times Junior and it is for high elementary and low middle school \
students, and the CEFR level is around A2 or A2-B1. \
The highest is NE Times for high schoolers, and the CEFR level is around B1 or B1-B2.

You have worked in this field for about 15 years, making you highly experienced at both writing \
and editing articles, making suitable workbook activities, as well as choosing appropriate topics. \
You see the value in making English articles and content in that they can be helpful to students \
in increasing English skills, expanding knowledge about the world, indirectly experiencing how \
concepts are explained in English, and being exposed to a variety of information and perspectives."""

# ------------------------------------------------------------------
# 레벨별 신문 설정
# ------------------------------------------------------------------
LEVEL_CONFIG: dict[str, dict] = {
    "kinder": {
        "newspaper":        "NE Times Kinder",
        "cefr":             "A1 or lower",
        "target":           "kindergarteners and early elementary school students (ages 5–8)",
        "word_count_range": "80–120",
        "paragraph_count":  "3–4",
    },
    "kids": {
        "newspaper":        "NE Times Kids",
        "cefr":             "A2 / A1-A2",
        "target":           "elementary school students (ages 9–12)",
        "word_count_range": "150–200",
        "paragraph_count":  "4–5",
    },
    "junior": {
        "newspaper":        "NE Times Junior",
        "cefr":             "A2 / A2-B1",
        "target":           "high elementary and low middle school students (ages 11–14)",
        "word_count_range": "200–280",
        "paragraph_count":  "5–6",
    },
    "times": {
        "newspaper":        "NE Times",
        "cefr":             "B1 / B1-B2",
        "target":           "high school students (ages 15–18)",
        "word_count_range": "280–380",
        "paragraph_count":  "6–7",
    },
}

# ------------------------------------------------------------------
# 워크북 포맷 8종 (원문: 02_타임즈 워크북 프롬프트)
# PAGE_CONFIG의 workbook_format 필드가 아래 키 중 하나를 가리킨다.
# ------------------------------------------------------------------
WORKBOOK_FORMATS = {
    "L1_MCQ":             "LEVEL 1 Multiple Choice Question Version",
    "L1_TF":              "LEVEL 1 True-False Version",
    "L2_ABC":             "Level 2 ABC",
    "L2_ABC_3SUB":        "LEVEL 2 ABC – 3 Subheading Version",
    "L2_AB_SYNONYM":      "LEVEL 2 AB – Synonym Version",
    "L2_AB_ANTONYM":      "LEVEL 2 AB – Antonym Version",
    "L3_THREE_SEQUENCE":  "LEVEL 3 – Three Sequence Version",
    "L3_MATCH_BLANKS":    "LEVEL 3 – Match the Words with Blanks Version",
}

# ------------------------------------------------------------------
# 지면 세분화 설정 (P1-1) — 원문: references/run-sheets.md · leveling.md ·
# article-templates.md. 신문 → 지면 → {난이도·CEFR·단어수·소제목·워크북포맷·구조}
# leveling.md 운영기준 반영: Times L1=B1, L2=B2, L3=C1 (레거시 C2 폐기).
# ------------------------------------------------------------------
PAGE_CONFIG: dict[str, list[dict]] = {
    "times": [
        {
            "page": "2면", "template": "TIMES-L2-NOSUB",
            "internal_level": "L2", "cefr": "B2",
            "word_min": 270, "word_max": 280, "subheadings": 0,
            "workbook_format": "L2_AB_SYNONYM",
            "structure": "Paragraphs only, no subheadings. Slots in order: (1) the phenomenon/news with its key record or figure, (2) concrete examples/cases, (3) causes incl. policy, (4) future plans of the responsible body.",
        },
        {
            "page": "3-1면", "template": "TIMES-L1-STANDARD",
            "internal_level": "L1", "cefr": "A2-B1",
            "word_min": 190, "word_max": 200, "subheadings": 0,
            "workbook_format": "L1_MCQ",
            "structure": "Paragraphs. Slots: (1) the news, (2) profile/background of subject, (3) responses and expectations, (4) one brief quote if available.",
        },
        {
            "page": "3-2면", "template": "TIMES-L1-MINI",
            "internal_level": "L1", "cefr": "A2-B1",
            "word_min": 90, "word_max": 110, "subheadings": 0,
            "workbook_format": None,
            "structure": "~100 words. Slots: (1) the news and key content, (2) why it happened, (3) response/expectations if available.",
        },
        {
            "page": "4면", "template": "TIMES-L3",
            "internal_level": "L3", "cefr": "C1",
            "word_min": 290, "word_max": 310, "subheadings": 0,
            "workbook_format": "L3_THREE_SEQUENCE",
            "structure": "~300 words, no subheadings. Slots: (1) the decision/event + details + implementation, (2) reason and current state with figures, (3) reactions pros/cons, (4) other actors considering the same (omit if none). Weight toward slots 1–2.",
        },
        {
            "page": "5면", "template": "TIMES-L1-SHORT",
            "internal_level": "L1", "cefr": "B1",
            "word_min": 135, "word_max": 140, "subheadings": 0,
            "workbook_format": "L1_TF",
            "structure": "135–140 words, no subheadings. Slots: (1) the news, (2) details and reason, (3) specifics (what/which/who), (4) responses.",
        },
        {
            "page": "8면", "template": "TIMES-L2-2SUB",
            "internal_level": "L2", "cefr": "B2",
            "word_min": 280, "word_max": 290, "subheadings": 2,
            "workbook_format": "L2_ABC",
            "structure": "~45-word intro, then one subheaded section per item (2 items), each ~120 words in ~4 short paragraphs: background → description → reason for selection → how it will be used.",
        },
        {
            "page": "12면", "template": "TIMES-L2-3SUB",
            "internal_level": "L2", "cefr": "B2",
            "word_min": 280, "word_max": 290, "subheadings": 3,
            "workbook_format": "L2_ABC_3SUB",
            "structure": "40–45-word intro, then one subheaded section per item (3 items), each ~80 words in ~2 paragraphs: basic info → what it is about → one distinct point of interest. Keep Korean titles in Korean.",
        },
        {
            "page": "Briefs", "template": "TIMES-BRIEF",
            "internal_level": "L1", "cefr": "A2-B1",
            "word_min": 65, "word_max": 77, "subheadings": 0,
            "workbook_format": None,
            "structure": "Single paragraph, 65–77 words. Straightforward news-brief style, relevant info only, no color. Headline 3–6 words present tense, no period.",
        },
    ],
    "kids": [
        {
            "page": "Main L2H", "template": "KIDS-L2H",
            "internal_level": "L2H", "cefr": "A1-A2",
            "word_min": 120, "word_max": 140, "subheadings": 0,
            "workbook_format": "L1_MCQ",
            "structure": "~130 words. Each paragraph exactly two sentences. Explain any concept a child wouldn't know.",
        },
        {
            "page": "WHAT'S HOT", "template": "KIDS-WHATSHOT-3SUB",
            "internal_level": "L3", "cefr": "A2",
            "word_min": 150, "word_max": 170, "subheadings": 3,
            "workbook_format": "L1_TF",
            "structure": "20–25-word intro, then three subheaded sections, one per item, each 2 paragraphs / 40–50 words. Two-sentence paragraphs.",
        },
    ],
    "junior": [
        {
            "page": "기본", "template": "JUNIOR-STANDARD",
            "internal_level": "Standard", "cefr": "A2-B1",
            "word_min": 200, "word_max": 280, "subheadings": 0,
            "workbook_format": "L1_MCQ",
            "structure": "Derived from Times-L1 lowered one notch. Short paragraphs, one idea each. Sentence length between Kids and Times L1.",
        },
    ],
    "kinder": [
        {
            "page": "기본", "template": "KINDER-STANDARD",
            "internal_level": "기본", "cefr": "A1 or lower",
            "word_min": 60, "word_max": 90, "subheadings": 0,
            "workbook_format": None,
            "structure": "Max ~80 words. Sentences ≤8 words, present tense dominant, concrete visual topics only.",
        },
    ],
}


def get_page_config(paper: str, page: str | None = None) -> dict:
    """신문(paper)과 지면(page)에 해당하는 지면 설정을 반환한다.
    page 미지정 시 해당 신문의 첫 지면을 기본값으로 사용한다."""
    pages = PAGE_CONFIG.get(paper, [])
    if not pages:
        # 폴백: LEVEL_CONFIG 기반 단어수
        return {
            "page": "기본", "template": f"{paper.upper()}-DEFAULT",
            "internal_level": "기본", "cefr": LEVEL_CONFIG.get(paper, {}).get("cefr", ""),
            "word_min": 150, "word_max": 300, "subheadings": 0,
            "workbook_format": "L1_MCQ", "structure": "",
        }
    if page:
        for p in pages:
            if p["page"] == page:
                return p
    return pages[0]


# ------------------------------------------------------------------
# Google Sheets 컬럼 순서
# ------------------------------------------------------------------
SHEET_COLUMNS = [
    "ID", "생성일시", "레벨", "섹션", "토픽",
    "기사본문", "어휘", "출처",
    "표절검사통과", "수정제안수",
    "크로스워드생성수", "워크북세트수", "상태",
]
