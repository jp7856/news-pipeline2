# News Pipeline 2 - NE Times 콘텐츠 제작 자동화 시스템

## 📋 프로젝트 개요

**NE Times** 영어 교육용 뉴스 파이프라인 시스템입니다. 이 프로젝트는 주어진 토픽을 받아 자동으로 영어 기사를 작성하고, 레벨별로 번역·편집·검수하며, 이미지 삽입, 워크북 생성, 크로스워드 제작 등을 거쳐 최종 콘텐츠를 Google Sheets에 저장하는 완전 자동화 파이프라인입니다.

### 핵심 목표
- 📰 **다양한 레벨의 영어 학습자용 뉴스 콘텐츠 자동 생성**
- 🤖 **AI 에이전트 기반 파이프라인 오케스트레이션**
- 📊 **Google Sheets 기반 콘텐츠 관리**
- 🎨 **웹 대시보드를 통한 사용자 친화적 인터페이스**

---

## 🏢 프로젝트 구조

```
news-pipeline2/
├── config.py                 # 설정 파일 (API 키, 모델, 레벨별 설정)
├── models.py                 # 데이터 모델 (Article, ArticleResult, ContentPackage 등)
├── orchestrator.py           # 오케스트레이터 (파이프라인 조율)
├── requirements.txt          # Python 의존성
├── runtime.txt               # Python 런타임 버전
├── Procfile                  # Railway 배포 설정 (web: python dashboard/app.py)
├── claude.md                 # 프로젝트 문서 (이 파일)
├── agents/                   # 메인 에이전트 모듈
│   ├── __init__.py
│   ├── content_producer.py   # Agent 1: 콘텐츠 제작 코디네이터
│   ├── translator.py         # Agent 2: 한국어 번역
│   ├── image_finder.py       # Agent 3: 이미지 탐색 (Unsplash API)
│   ├── reviewer.py           # Agent 5: 검수 및 승인
│   ├── worksheet.py          # Agent 4: Google Sheets 저장
│   └── sub_agents/           # 세부 서브 에이전트
│       ├── __init__.py
│       ├── writer.py         # Sub-Agent 1: 기사 작성
│       ├── plagiarism_checker.py  # Sub-Agent 1-2: 표절 검사
│       ├── editor.py         # Sub-Agent 1-3: 편집 제안
│       ├── crossword.py      # Sub-Agent 1-4: 크로스워드 생성
│       ├── workbook.py       # Sub-Agent 1-5: 워크북 세트 생성 (레거시 8종 포맷)
│       ├── researcher.py     # Sub-Agent 0: 실시간 리서치 (P0-1)
│       ├── validation.py     # 단어수·인용·URL 검증 (스킬 validate.py 이식)
│       └── utils.py          # 유틸리티 함수 (robust JSON 파서)
├── dashboard/                # 웹 대시보드
│   ├── app.py                # Flask 애플리케이션
│   ├── static/               # CSS, JavaScript 정적 자산
│   └── templates/
│       └── index.html        # 메인 UI 템플릿
```

---

## 🔧 설정 (config.py)

### API 키 및 환경 변수

```python
ANTHROPIC_API_KEY      # Claude API 키 (필수)
CLAUDE_MODEL           # "claude-sonnet-4-6" 사용
GOOGLE_SHEETS_CREDENTIALS_JSON  # Google Sheets 인증
GOOGLE_SHEET_ID        # 대상 Google Sheet ID
GOOGLE_CSE_API_KEY     # Google Custom Search API
GOOGLE_CSE_ID          # Google Custom Search Engine ID
UNSPLASH_ACCESS_KEY    # Unsplash 이미지 검색 API
```

### 레벨별 신문 설정 (LEVEL_CONFIG)

| 레벨 | 신문명 | CEFR 수준 | 대상 연령 | 단어 수 | 단락 수 |
|------|--------|---------|----------|--------|--------|
| kinder | NE Times Kinder | A1 이하 | 5~8세 (유치원~초등저) | 80~120 | 3~4 |
| kids | NE Times Kids | A2/A1-A2 | 9~12세 (초등고학년) | 150~200 | 4~5 |
| junior | NE Times Junior | A2/A2-B1 | 11~14세 (중학생) | 200~280 | 5~6 |
| times | NE Times | L1=B1 / L2=B2 / L3=C1 (leveling.md 기준) | 15~18세 (고등학생) | 지면별 (PAGE_CONFIG) | 지면별 |

### 시스템 프롬프트 (SYSTEM_PROMPT)

모든 서브 에이전트가 공유하는 15년 경력 영어 교육 전문가 페르소나 정의 (프롬프트 캐싱 활용)

### Google Sheets 컬럼 순서 (SHEET_COLUMNS)

```
[ID, 생성일시, 레벨, 섹션, 토픽, 기사본문, 어휘, 출처, 
 표절검사통과, 수정제안수, 크로스워드생성수, 워크북세트수, 상태]
```

---

## 📦 데이터 모델 (models.py)

### Article (기사 메타데이터)
- `id`: 고유 식별자
- `title`: 기사 제목
- `url`: 원본 URL
- `source`: 출처
- `level`: Level 이넘 (kinder/kids/junior/times)
- `section`: Section 이넘 (정치/경제/과학 등)
- `content_en`: 영어 본문
- `image_url`: 이미지 URL
- `status`: ArticleStatus 이넘 (수집완료/번역완료/검수통과/발행완료 등)

### ArticleResult (에이전트 생성 결과)
- `text`: 완성된 영어 기사 본문
- `vocabulary`: 핵심 어휘 5~8개 리스트
- `sources`: 참고 URL 목록
- `word_count`: 단어 수
- `text_ko`: 한국어 번역 본문
- `summary_ko`: 한국어 요약 (2~4문장, 레벨별)

### ContentPackage (전체 콘텐츠 패키지)
```python
topic: str                          # 기사 주제
level: Level                        # 레벨
section: Section                    # 섹션
article: ArticleResult             # 완성된 기사
image_url: str                     # 이미지 URL
plagiarism_report: PlagiarismReport # 표절 검사 결과
editing_suggestions: list[EditingSuggestion]  # 편집 제안
crossword_sentences: list[CrosswordPair]      # 크로스워드 문제
workbook_sets: list[dict]          # 워크북 세트
```

### Enums
- **ArticleStatus**: COLLECTED, TRANSLATED, IMAGE_FOUND, SHEET_SAVED, APPROVED, REJECTED, PUBLISHED, ERROR
- **Level**: KINDER, KIDS, JUNIOR, TIMES
- **Section**: POLITICS, ECONOMY, BUSINESS, SOCIETY, WORLD, SCIENCE, TECHNOLOGY, ENVIRONMENT, HEALTH, SPORTS, EDUCATION, CULTURE, ENTERTAINMENT, PEOPLE

---

## 🔄 오케스트레이터 (orchestrator.py)

### 파이프라인 흐름

```
Orchestrator.run(topic, level, section, source_url)
    ↓
[Agent 1: ContentProducerAgent]
    ├─ WriterAgent: 영어 기사 작성
    ├─ PlagiarismCheckerAgent: 표절 검사
    ├─ EditorAgent: 편집 제안 생성
    └─ (병렬) CrosswordAgent + WorkbookAgent
    ↓
[Agent 2: TranslatorAgent]
    └─ 한국어 번역 및 요약 생성
    ↓
[Agent 3: ImageFinderAgent]
    └─ Unsplash API로 이미지 검색
    ↓
[Agent 4: WorksheetAgent]
    └─ Google Sheets에 저장
    ↓
Return: ContentPackage + Sheet URL
```

### 주요 메서드

```python
run(topic: str, level: Level, section: Section, source_url: str = "") 
    → (ContentPackage, sheet_url: str)
```

- **topic**: 기사 주제 또는 뉴스 URL
- **level**: 레벨 (KINDER/KIDS/JUNIOR/TIMES)
- **section**: 섹션 (정치/경제/과학 등)
- **source_url**: 참고 뉴스 링크 (선택)

### 로깅 콜백
파이프라인 실행 중 실시간 로그를 수집하기 위해 `log_callback` 함수 지원

---

## 🤖 에이전트 상세

### Agent 1: ContentProducerAgent (agents/content_producer.py)

**역할**: 콘텐츠 제작 파이프라인의 코디네이터

**워크플로우**:
```
WriterAgent → PlagiarismCheckerAgent → EditorAgent
                    ↓
        (병렬) CrosswordAgent + WorkbookAgent
```

**입력**: topic, level, section, source_url
**출력**: ContentPackage (기사, 표절 검사, 편집 제안, 크로스워드, 워크북)

### Agent 2: TranslatorAgent (agents/translator.py)

**역할**: 영어 기사를 레벨별 한국어로 번역

**레벨별 번역 스타일**:
- **kinder**: 유치원~초등 저학년, 아주 쉬운 단어, 한 문장 15단어 이내
- **kids**: 초등 고학년~중학교 1학년, 중학 교과서 수준 어휘
- **junior**: 중학생, 표준 한국어 뉴스 기사체
- **times**: 고등학생 이상, 격식체 신문 기사 문체

**생성 결과**:
- `text_ko`: 한국어 번역 본문
- `summary_ko`: 레벨별 요약 (2~4문장)

### Agent 3: ImageFinderAgent (agents/image_finder.py)

**역할**: Unsplash API를 통해 기사 관련 이미지 자동 검색

**검색 전략**:
1. 기사의 핵심 어휘 (vocabulary) 활용
2. 요청 실패 시 토픽 텍스트 사용
3. 성공 시 고해상도 이미지 URL 저장

### Agent 4: WorksheetAgent (agents/worksheet.py)

**역할**: Google Sheets에 완성된 콘텐츠 저장

**저장 데이터**:
- ID, 생성일시, 레벨, 섹션, 토픽
- 영어 기사, 한국어 번역
- 어휘, 출처, 이미지
- 표절 검사 결과, 편집 제안 수
- 크로스워드, 워크북 생성 수
- 상태

### Agent 5: ReviewerAgent (agents/reviewer.py)

**역할**: 최종 검수 및 승인 (선택 사항)

---

## 🌐 웹 대시보드 (dashboard/app.py)

### Flask 애플리케이션 구조

```python
GET  /              # 메인 UI 로드
POST /api/run       # 파이프라인 실행 시작
GET  /api/status    # 실행 상태 조회
```

### 기능
- ✅ 토픽, 레벨, 섹션 선택 후 파이프라인 실행
- ✅ WebSocket을 통한 실시간 로그 스트리밍
- ✅ 생성된 콘텐츠 미리보기
- ✅ Google Sheets 링크 제공

### 실시간 통신
- **Socket.IO** 사용으로 클라이언트와 서버 간 실시간 로그 전송
- 각 에이전트의 진행 상황을 브라우저에서 라이브 모니터링

---

## 📋 서브 에이전트 (agents/sub_agents/)

### WriterAgent
- Claude를 통해 주제에 맞는 영어 뉴스 기사 작성
- 레벨별 단어 수, 단락 수 준수
- 어휘 추출 및 출처 기록

### PlagiarismCheckerAgent
- 생성된 기사의 표절 검사
- 고유성(originality) 점수 반환
- 경고 또는 통과 판정

### EditorAgent
- 기사 품질 검토
- 문법, 명확성, 교육성에 대한 수정 제안 생성
- EditingSuggestion 리스트 반환

### CrosswordAgent
- 기사 내용 기반 크로스워드 문제 생성
- 질문과 답변 쌍 생성
- 학습 보조 자료로 활용

### WorkbookAgent
- 기사 내용을 바탕으로 워크북 연습 세트 생성
- 어휘 채우기, 문제 풀이, 이해도 평가 등
- 다양한 활동 유형 포함

---

## 🛠️ 기술 스택

| 항목 | 기술 |
|------|------|
| AI 모델 | Anthropic claude-sonnet-4-6 |
| 웹 프레임워크 | Flask, Flask-SocketIO |
| 외부 API | Unsplash, Google Sheets, Google Custom Search |
| 인증 | google-auth, gspread |
| 데이터 처리 | BeautifulSoup4, lxml |
| 배포 | Railway (Procfile 기반, GitHub 자동 배포) |

---

## 📦 의존성 (requirements.txt)

```
anthropic>=0.40.0         # Claude API
flask>=3.0.0              # 웹 프레임워크
flask-socketio>=5.3.6     # WebSocket 통신
python-dotenv>=1.0.0      # 환경 변수 관리
requests>=2.31.0          # HTTP 요청
beautifulsoup4>=4.12.0    # HTML 파싱
lxml>=5.0.0               # XML/HTML 처리
gspread>=6.0.0            # Google Sheets API
google-auth>=2.0.0        # Google 인증
```

---

## 🚀 사용 방법

### 1. 환경 설정

```bash
# .env 파일 생성
ANTHROPIC_API_KEY=sk_...
GOOGLE_SHEET_ID=...
UNSPLASH_ACCESS_KEY=...
GOOGLE_CSE_API_KEY=...
GOOGLE_CSE_ID=...
```

### 2. 의존성 설치

```bash
pip install -r requirements.txt
```

### 3. 파이프라인 실행 (Python)

```python
from orchestrator import Orchestrator
from models import Level, Section

orchestrator = Orchestrator()
result, sheet_url = orchestrator.run(
    topic="Climate change and young activists",
    level=Level.JUNIOR,
    section=Section.ENVIRONMENT,
)

print(f"Sheet URL: {sheet_url}")
print(f"Article: {result.article.text}")
```

### 4. 웹 대시보드 시작

```bash
python dashboard/app.py
```

브라우저에서 `http://localhost:5000` 접속

---

## 📊 Google Sheets 연동

### 인증 설정
1. Google Cloud Console에서 서비스 계정 생성
2. `credentials.json` 생성 및 프로젝트 디렉토리에 배치
3. Google Sheet 공유 설정 (서비스 계정 이메일)

### 자동 저장
- 파이프라인 실행 후 자동으로 Google Sheets에 신규 행 추가
- 스프레드시트에서 실시간 콘텐츠 관리 가능

---

## 🔍 디버깅 및 로깅

### 로그 확인
- 파이프라인 각 단계별 로그 출력
- WebSocket 연결 시 대시보드에서 실시간 모니터링

### 주요 로그 메시지
```
=== Pipeline Start (run_id: xxxx) ===
[Agent1] 콘텐츠 제작 시작
[Agent1-WriterAgent] 기사 작성 중...
[Agent2] 한국어 번역 시작
[Agent3] 이미지 탐색 시작
[Agent4] Google Sheets 저장
=== Pipeline Complete (xxxs) ===
```

---

## 📈 향후 개선 사항

- [ ] 다국어 지원 (일본어, 중국어 등)
- [ ] 레벨별 커스터마이제이션 강화
- [ ] 음성 생성 (TTS) 통합
- [ ] 사용자 피드백 기반 개선
- [ ] 배치 처리 (여러 토픽 동시 처리)
- [ ] 콘텐츠 품질 메트릭 대시보드
- [ ] API 엔드포인트 문서화 (OpenAPI/Swagger)

---

## 🔗 배포

### Railway 배포

```bash
# Procfile 이미 구성됨 (web: python dashboard/app.py)
# GitHub master 푸시 시 Railway가 자동 재배포
git push origin master

# 환경변수는 Railway 대시보드 Variables 탭에서 설정:
#   ANTHROPIC_API_KEY, GOOGLE_SHEETS_CREDENTIALS_JSON, GOOGLE_SHEET_ID,
#   GOOGLE_CSE_API_KEY, GOOGLE_CSE_ID, UNSPLASH_ACCESS_KEY
```

---

## 📝 라이선스 및 귀속

- 프로젝트: NE Times Content Pipeline
- AI Model: Anthropic Claude
- 이미지 API: Unsplash
- 번역 및 편집: Claude AI

---

## 👨‍💻 개발 참고사항

### 코드 구조
- 각 에이전트는 독립적인 모듈로 구성
- 에이전트 간 통신은 ContentPackage를 통한 데이터 전달
- Anthropic 클라이언트는 에이전트 간 공유 (API 호출 최적화)

### 확장 가능성
- 새로운 에이전트 추가 시 `agents/` 디렉토리에 모듈 생성
- `Orchestrator`의 `run()` 메서드에 새로운 에이전트 단계 추가
- ContentPackage 데이터 모델 확장 가능

### 성능 최적화
- 프롬프트 캐싱을 통해 SYSTEM_PROMPT 재사용
- 크로스워드와 워크북 생성을 병렬 처리
- WebSocket을 통한 효율적인 실시간 통신

---

마지막 수정: 2026년 6월 10일
