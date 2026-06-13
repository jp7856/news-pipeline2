from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Any


class ArticleStatus(str, Enum):
    COLLECTED = "수집완료"
    TRANSLATED = "번역완료"
    IMAGE_FOUND = "이미지완료"
    SHEET_SAVED = "시트저장완료"
    APPROVED = "검수통과"
    REJECTED = "검수거부"
    PUBLISHED = "발행완료"
    NEEDS_REVIEW = "검수필요"   # 게이트 미통과 — 편집자 확인 필요, 다운스트림 보류
    ERROR = "오류"


class Level(str, Enum):
    KINDER = "kinder"    # 유치~초등저학년
    KIDS = "kids"        # 초등고학년~중등
    JUNIOR = "junior"    # 중등
    TIMES = "times"      # 고등이상


class Section(str, Enum):
    POLITICS      = "정치"
    ECONOMY       = "경제"
    BUSINESS      = "비즈니스"
    SOCIETY       = "사회"
    WORLD         = "세계"
    SCIENCE       = "과학"
    TECHNOLOGY    = "기술"
    ENVIRONMENT   = "환경"
    HEALTH        = "건강"
    SPORTS        = "스포츠"
    EDUCATION     = "교육"
    CULTURE       = "문화"
    ENTERTAINMENT = "엔터테인먼트"
    PEOPLE        = "인물"


@dataclass
class Article:
    id: str
    title: str
    url: str
    source: str
    level: Level
    section: Section
    collected_at: datetime = field(default_factory=datetime.now)

    # 원문 본문 (일부)
    content_en: str = ""

    # Agent 2: 번역
    title_ko: str = ""
    summary_en: str = ""
    summary_ko: str = ""

    # Agent 3: 이미지
    image_url: str = ""

    # Agent 5: 검수
    status: ArticleStatus = ArticleStatus.COLLECTED
    review_notes: str = ""

    # Google Sheets 행 번호 (저장 후 업데이트용)
    sheet_row: Optional[int] = None


# ============================================================
# Agent 1 — 콘텐츠 제작 결과 모델
# ============================================================

@dataclass
class VocabItem:
    """어휘 1개 + CEFR 근거 (P2-1, 원문: 어휘리스트 마스터 프롬프트)"""
    word: str            # 원형 (base form)
    cefr: str            # 예: "B2"
    meaning_ko: str      # 한국어 뜻 (1~2개, 콤마+공백 구분)


@dataclass
class ArticleResult:
    """WriterAgent가 생성한 기사"""
    text: str                          # 완성된 기사 본문 (영어)
    vocabulary: list[str]              # 핵심 어휘 단어 리스트 (하위호환)
    sources: list[str]                 # 참고 URL 목록 (실제 fetch된 기사 URL만)
    word_count: int = 0

    # P2-1: 어휘 상세 (8~14개, CEFR 근거·한국어 뜻, 등장 순서)
    vocabulary_detail: list[VocabItem] = field(default_factory=list)

    # Agent 2: 번역 결과
    text_ko: str = ""                  # 한국어 번역 본문
    summary_ko: str = ""               # 한국어 요약 (2~4문장)

    def __post_init__(self):
        if not self.word_count and self.text:
            self.word_count = len(self.text.split())

    def vocab_formatted(self) -> str:
        """vocab-rules.md 출력 형식: 'word 뜻 / word 뜻 ... / Total: N words'"""
        if not self.vocabulary_detail:
            return ", ".join(self.vocabulary)
        items = " / ".join(f"{v.word} {v.meaning_ko}" for v in self.vocabulary_detail)
        return f"{items}\nTotal: {len(self.vocabulary_detail)} words"


# ============================================================
# Agent 0 — 리서치 결과 모델 (P0-1)
# ============================================================

@dataclass
class SourceDoc:
    """실제 fetch한 출처 1건"""
    url: str
    title: str
    text: str          # 추출된 본문 (일부)


@dataclass
class ResearchResult:
    """ResearcherAgent의 수집 결과"""
    success: bool                              # 사용 가능한 출처 1건 이상 확보 여부
    sources: list[SourceDoc] = field(default_factory=list)
    note: str = ""                             # 실패/경고 사유

    @property
    def combined_text(self) -> str:
        """Writer 컨텍스트로 주입할 통합 본문"""
        parts = []
        for s in self.sources:
            parts.append(f"[SOURCE] {s.title}\nURL: {s.url}\n{s.text}")
        return "\n\n---\n\n".join(parts)

    @property
    def urls(self) -> list[str]:
        return [s.url for s in self.sources]


# ============================================================
# 검수 게이트 결과 모델 (P0-2 / P0-3)
# ============================================================

@dataclass
class ReviewReport:
    """검수 게이트(사실·시제) 결과"""
    passed: bool
    factual_issues: list[str] = field(default_factory=list)   # 사실 오류
    temporal_issues: list[str] = field(default_factory=list)  # 시제·시점 오류
    rewrite_count: int = 0                                     # 재작성 횟수
    needs_human_review: bool = False                           # 최대 재시도 후 미해결
    notes: str = ""

    @property
    def has_blocking_issues(self) -> bool:
        return bool(self.factual_issues or self.temporal_issues)


@dataclass
class EditingSuggestion:
    """EditorAgent의 개별 수정 제안"""
    original: str      # 원문 문장/구절
    suggestion: str    # 수정 제안
    reason: str        # 이유


@dataclass
class CrosswordSentencePair:
    """CrosswordAgent가 생성한 어휘별 문장 쌍"""
    word: str
    korean_definition: str
    sentence_b1: str      # B1 수준, 단어 위치에 ______ (6칸)
    sentence_b1_b2: str   # B1-B2 수준, 단어 위치에 ______


@dataclass
class WorkbookActivity:
    """워크북 1개 액티비티 (포맷별 구조가 달라 자유 형식 본문으로 담는다)"""
    label: str          # "A" / "B" / "C" / "D" / "Extra"
    title: str          # 예: "Vocabulary Synonyms"
    instruction: str    # 지시문
    body: str           # 문항·보기 등 본문 (줄바꿈 포함 텍스트)
    answer: str = ""    # 정답 키


@dataclass
class WorkbookSet:
    """WorkbookAgent가 생성한 활동지 1세트 (레거시 8종 포맷, P1-2)"""
    set_number: int                                    # 1 또는 2
    format_key: str = ""                               # WORKBOOK_FORMATS 키
    format_name: str = ""                              # 사람이 읽는 포맷명
    activities: list[WorkbookActivity] = field(default_factory=list)

    # ── 하위 호환 접근자 (기존 직렬화/렌더링 코드 보호) ──
    @property
    def comprehension_questions(self) -> list[str]:
        for a in self.activities:
            if "comprehension" in a.title.lower() or a.label.upper() == "D":
                return [ln for ln in a.body.split("\n") if ln.strip()]
        return []

    @property
    def discussion_questions(self) -> list[str]:
        return []


@dataclass
class ImageCandidate:
    """이미지 후보 1건 + 라이선스 증빙 (P1-3)"""
    url: str
    thumb: str = ""
    description: str = ""
    photographer: str = ""
    source: str = ""          # 예: "Unsplash"
    license: str = ""         # 예: "Unsplash License"
    page_url: str = ""        # 출처 페이지 (귀속 표기용)
    confirmed_date: str = ""  # 확인일 YYYY-MM-DD


@dataclass
class PlagiarismReport:
    """PlagiarismCheckAgent의 검사 결과"""
    passed: bool
    checklist: dict[str, Any]   # 8개 항목별 결과
    notes: str = ""             # 문제 있을 경우 상세 메모


@dataclass
class ContentPackage:
    """Agent 1의 최종 출력물"""
    topic: str
    level: Level
    section: Section
    article: ArticleResult
    plagiarism_report: PlagiarismReport
    editing_suggestions: list[EditingSuggestion]
    crossword_sentences: list[CrosswordSentencePair]
    workbook_sets: list[WorkbookSet]       # 반드시 2세트

    # Agent 3: 이미지 (P1-3)
    image_url: str = ""
    image_query: str = ""                                       # 주제·핵심장면 기반 검색어
    image_candidates: list[ImageCandidate] = field(default_factory=list)
    image_selected: Optional[ImageCandidate] = None             # 추천 이미지 + 라이선스 증빙

    # Agent 0: 리서치 (P0-1)
    research: Optional[ResearchResult] = None

    # 검수 게이트 (P0-2 / P0-3)
    review_report: Optional[ReviewReport] = None
    status: ArticleStatus = ArticleStatus.COLLECTED


# ============================================================
# 파이프라인 실행 모델
# ============================================================

@dataclass
class PipelineRun:
    run_id: str
    started_at: datetime = field(default_factory=datetime.now)
    finished_at: Optional[datetime] = None
    articles: list[Article] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.articles)

    @property
    def published(self) -> int:
        return sum(1 for a in self.articles if a.status == ArticleStatus.PUBLISHED)

    @property
    def failed(self) -> int:
        return sum(1 for a in self.articles if a.status == ArticleStatus.ERROR)
