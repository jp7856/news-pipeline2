# News Pipeline 2 - NE Times 콘텐츠 제작 자동화 시스템

## 📋 프로젝트 개요

**NE Times** 영어 교육용(어린이·청소년) 뉴스 파이프라인 시스템입니다. 토픽을 받아 실시간 리서치 기반으로 영어 기사를 작성하고, 검수 게이트를 통과시킨 뒤 번역·이미지·워크북·크로스워드를 생성하여 Google Sheets에 저장하고, 최종적으로 발행 사이트(GitHub Pages)에 게시합니다.

### 핵심 목표
- 📰 레벨·지면별 영어 학습 콘텐츠 자동 생성 (어린이·청소년 대상, 안전성 우선)
- 🤖 실시간 리서치 + 검수 게이트 기반 파이프라인 오케스트레이션
- 📊 Google Sheets 저장 + GitHub Pages 발행
- 🎨 2단계(초안 확인 → 이후 작업) 웹 대시보드

> 본 문서는 2026-06-16 기준 실제 코드와 일치하도록 갱신되었습니다.

---

## 🏢 프로젝트 구조

```
news-pipeline2/
├── config.py                 # 설정 (API 키, 모델, PAGE_CONFIG, WORKBOOK_FORMATS)
├── models.py                 # 데이터 모델 (ArticleResult, ContentPackage, VocabItem 등)
├── orchestrator.py           # 오케스트레이터 (run / run_phase1 / rebuild_and_run / run_issue)
├── requirements.txt
├── Procfile                  # Railway: web: python dashboard/app.py
├── CLAUDE.md
├── agents/
│   ├── content_producer.py   # Agent 1: 콘텐츠 제작 코디네이터 (게이트 포함)
│   ├── translator.py         # Agent 2: 한국어 번역
│   ├── image_finder.py       # Agent 3: 이미지 탐색 (Claude 쿼리 생성 + Unsplash)
│   ├── reviewer.py           # Agent 5: 사실·시제 검수 (정규 단계, 게이트)
│   ├── worksheet.py          # Agent 4: Google Sheets 저장 (+ CSV 백업)
│   └── sub_agents/
│       ├── researcher.py     # Agent 0: 실시간 리서치 (Serper + NewsAPI)
│       ├── writer.py         # 기사 작성 (2버전, 날짜·시제 주입)
│       ├── plagiarism_checker.py  # 표절 검사 (게이트)
│       ├── editor.py         # 교정 제안
│       ├── crossword.py      # 크로스워드 생성
│       ├── workbook.py       # 워크북 생성 (레거시 8종 포맷)
│       ├── validation.py     # 단어수(MS Word 기준)·인용·URL 검증
│       └── utils.py          # robust JSON 파서 (5단계 폴백)
├── dashboard/
│   ├── app.py                # Flask + Socket.IO 앱
│   └── templates/index.html  # 단일 페이지 대시보드 (인라인 JS)
└── sheet_backups/            # 시트 저장 실패 시 CSV 백업 (로컬/임시)
```

---

## 🔧 설정 (config.py)

### API 키 및 환경 변수

```python
ANTHROPIC_API_KEY               # Claude API 키 (필수)
CLAUDE_MODEL = "claude-sonnet-4-6"
SERPER_API_KEY                  # Serper.dev (Google 검색) — 리서치 1순위
NEWSAPI_KEY                     # NewsAPI.org — 리서치 폴백
GOOGLE_SHEETS_CREDENTIALS_JSON  # 서비스계정 JSON "전체 내용"(문자열) — 파일 경로 아님
GOOGLE_SHEET_ID                 # 저장 대상 스프레드시트 ID
UNSPLASH_ACCESS_KEY             # Unsplash 이미지 검색
GITHUB_TOKEN                    # 발행용 — ne-times-site 레포 contents 쓰기 권한
GITHUB_SITE_REPO                # 기본값 "jp7856/ne-times-site"
```

> ⚠️ **Google CSE(GOOGLE_CSE_API_KEY/ID)는 폐기**되었습니다. GCP 프로젝트 권한 문제(403)로
> 동작하지 않아 **Serper.dev + NewsAPI**로 대체했습니다. 리서치는 어린이 교육에 적합한
> 도메인(National Geographic Kids, Smithsonian, BBC Bitesize, Britannica 등)을 우선 검색하고,
> 결과 부족 시 일반 교육 키워드로 재시도하며 쇼핑·SNS 도메인은 차단합니다.

### 레벨·지면 설정 — PAGE_CONFIG (P1-1)

`LEVEL_CONFIG`(신문 4종 단위)는 기본 메타로 유지하되, 실제 생성 규격은 **PAGE_CONFIG**가
신문 → 지면 → `{internal_level(L1/L2/L3), cefr, word_min/max, subheadings, workbook_format, structure}`로
정의합니다. Times는 8개 지면(2면·3-1면·3-2면·4면·5면·8면·12면·Briefs)을 지원합니다.
단어수는 `validation.py`의 MS Word 기준 카운트로 기계 검증하며, 미달 시 게이트가 재작성을 지시합니다.

CEFR 기준(leveling.md): Times L1=B1, L2=B2, L3=C1.

### 워크북 8종 — WORKBOOK_FORMATS (P1-2)

`L1_MCQ, L1_TF, L2_ABC, L2_ABC_3SUB, L2_AB_SYNONYM, L2_AB_ANTONYM, L3_THREE_SEQUENCE,
L3_MATCH_BLANKS`. 지면 설정(`workbook_format`)에 따라 자동 선택됩니다.

### Google Sheets 컬럼 (worksheet.py SHEET_COLUMNS)

```
생성일시, 레벨, 섹션, 토픽, 단어수, 기사(영문), 기사(한국어), 요약(한국어),
어휘, 출처, 표절검사, 이미지URL, 이미지출처, 이미지라이선스, 이미지확인일,
크로스워드, 워크북Set1, 워크북Set2
```

---

## 📦 데이터 모델 (models.py 주요 필드)

### ArticleResult
`text, text_ko, summary_ko, word_count, vocabulary(list[str]), vocabulary_detail(list[VocabItem]), sources`

### VocabItem (P2-1)
`word(원형), cefr, meaning_ko` — 어휘 8~14개, 등장순서, CEFR 근거.

### ContentPackage
`topic, level, section, article, plagiarism_report, review_report, editing_suggestions,
crossword_sentences, workbook_sets, image_url/image_selected/image_candidates,
alternate_text/alternate_label/selected_variant(P2-2), research, status`

### ArticleStatus
`COLLECTED, TRANSLATED, IMAGE_FOUND, SHEET_SAVED, APPROVED, NEEDS_REVIEW(검수필요),
REJECTED, PUBLISHED, ERROR`

---

## 🔄 오케스트레이터 (orchestrator.py)

대시보드는 **2단계**로 동작합니다.

### Phase 1 — `run_phase1()` (초안)
```
Agent 0 리서치 → Writer 2버전(생동감형/레벨엄수형)
  → [게이트 루프] 표절 + 사실·시제 검수(Agent 5) + 단어수
      · 미통과 시 최대 3회 자동 재작성
      · 3회 후에도 안전 항목(사실·시제·표절) 미해결 → NEEDS_REVIEW 중단
  → Editor 교정 제안 → (통과 후) Crossword · Workbook
→ draft_done (초안 표시, 번역·이미지·시트는 보류)
```

### Phase 2 — `rebuild_and_run()` (이후 작업 진행)
```
확정 본문(편집/AI수정/버전선택 반영) → rebuild()
  · 표절 재검사 + Agent 5 검수 재실행(최종본 기준, NEEDS_REVIEW 가능)
  · 어휘·교정·크로스워드·워크북 재생성
→ Agent 2 번역 → Agent 3 이미지 → Agent 4 Google Sheets 저장
```

### 기타 메서드
- `run()` — 단건 풀 파이프라인 (Phase 1+2 일괄, 비대화형/배치용)
- `run_issue(topics, level, section)` — 1회분(지면별) 배치 생성 (P1-1)

> **오류 전파 차단(P0-2 ③, F-3 해소):** Crossword·Workbook은 더 이상 Editor와 병렬이 아니라
> **게이트 통과 후 순차 실행**되며, 번역·워크북은 항상 최종 수정본 기준으로 생성됩니다.

---

## 🤖 에이전트 상세

| 에이전트 | 역할 | 핵심 |
|---|---|---|
| **Agent 0 ResearcherAgent** | 실시간 리서치 (P0-1) | Serper(Google)→NewsAPI 폴백, 교육 도메인 우선, 제목·본문 관련성 필터, 실제 fetch URL만 출처 기록 |
| **Agent 1 ContentProducer** | 제작 코디네이터 | Writer→게이트(표절·검수·단어수)→교정→크로스워드·워크북 |
| **Agent 2 TranslatorAgent** | 한국어 번역 | 레벨별 문체, `text_ko` + `summary_ko` |
| **Agent 3 ImageFinderAgent** | 이미지 (P1-3) | Claude가 주제·핵심 장면으로 검색어 생성(어휘 나열 폐기), 후보 5건, 관련성 선별, 라이선스·확인일 로그 |
| **Agent 4 WorksheetAgent** | 시트 저장 (P1-4) | env JSON 자격증명, 실패 시 `sheet_backups/` CSV 백업 |
| **Agent 5 ReviewerAgent** | 사실·시제 검수 (P0-2/P0-3) | **정규 단계(게이트)**, 오늘 날짜 대비 시제 검증, 불일치 시 재작성 트리거 |

### Writer (sub_agents/writer.py)
- 기사 2버전 생성(생동감형 추천 / 레벨엄수형 대안) — P2-2
- 프롬프트에 **오늘 날짜 주입** + 과거 이벤트 과거형 서술 규칙 — P0-3
- **콘텐츠 안전 규칙**: 폭력·시체·나체·성인 주제 금지(어린이·청소년 대상). 출처가 부적절·무관하면 자체 지식으로 안전하게 작성
- 어휘 8~14개(원형·CEFR·등장순) — P2-1

---

## 🌐 웹 대시보드 (dashboard/app.py + index.html)

### 엔드포인트
```
GET  /                    # 대시보드 UI
POST /api/run             # Phase 1 실행 (초안) → draft_done
POST /api/stop            # 실행 중 협조적 취소 (러닝 배지 클릭)
POST /api/regenerate      # Phase 2: 확정 본문으로 재생성+번역+이미지+시트
POST /api/revise          # AI 어시스턴트: 수정 지시(본문 갱신) 또는 질문(답변)
POST /api/publish         # 발행: ne-times-site/articles.json에 커밋
GET  /api/usage           # 누적 토큰·비용
GET  /api/health          # 환경변수 설정 여부
GET  /api/health/sheets   # 구글시트 실연결 진단 + 서비스계정 이메일 보고
GET  /api/history         # 생성 이력
GET  /api/history/<idx>   # 단건 이력
```

### Socket.IO 이벤트
`log`(실시간 로그) · `draft_done`(Phase 1 완료) · `pipeline_done`(Phase 2 완료) ·
`pipeline_error` · `pipeline_stopped`(사용자 중단)

### UI 흐름
1. 토픽·레벨·섹션·지면 선택 → **Generate** → Phase 1
2. 초안 + 하단 **체크포인트 배너**: `이후 작업 진행 ▶` / `취소` / **AI 수정**(수정·질문, 로그 기록)
3. 기사 본문 **직접 편집(contenteditable)** 가능, **버전 토글**(P2-2), **교정 제안 적용/거부**(P2-3)
4. 탭: Article · 한국어 · Plagiarism · Editing · Crossword · Workbook · 이미지 V1 · 이미지 V2 · **검수**(Agent 5 결과)
5. Phase 2 완료 후 **📊 시트 열기** + **📰 발행하기** 노출
6. 러닝 배지: 진행 중 hover 시 빨강 + 클릭하여 중단

---

## 📰 발행 (GitHub Pages 연동)

- **사이트:** https://jp7856.github.io/ne-times-site/ (레포 `jp7856/ne-times-site`)
- 사이트는 레포의 **정적 `articles.json`**을 직접 fetch하여 렌더 (별도 서버 불필요)
- 대시보드 **발행하기** → `/api/publish` → GitHub Contents API로 `articles.json`에 기사 append 커밋
- 검수 미통과(NEEDS_REVIEW) 기사는 발행 전 확인창 표시 (교육용 안전장치)
- `GITHUB_TOKEN`(ne-times-site contents 쓰기 권한) 필요

---

## 🚀 사용·배포

```bash
pip install -r requirements.txt
python dashboard/app.py        # http://localhost:5000
```

### Railway 배포
```
# Procfile: web: python dashboard/app.py
# master 푸시 시 자동 재배포
# Variables(필수): ANTHROPIC_API_KEY, SERPER_API_KEY, NEWSAPI_KEY,
#   GOOGLE_SHEETS_CREDENTIALS_JSON(JSON 전체), GOOGLE_SHEET_ID,
#   UNSPLASH_ACCESS_KEY, GITHUB_TOKEN
# 배포 URL(v2): web-production-d55ca.up.railway.app
```

> Railway 디스크는 임시이므로 `sheet_backups/` CSV는 재배포 시 사라집니다.
> 영구 보관은 Google Sheets 저장 성공이 전제입니다(서비스계정을 시트에 편집자로 공유).

---

## 🛠️ 기술 스택

| 항목 | 기술 |
|---|---|
| AI 모델 | Anthropic claude-sonnet-4-6 |
| 웹 | Flask, Flask-SocketIO |
| 외부 API | Serper.dev, NewsAPI, Unsplash, Google Sheets, GitHub Contents API |
| 인증/처리 | google-auth, gspread, BeautifulSoup4, lxml, requests |
| 배포 | Railway (Procfile, GitHub 자동 배포) |

---

마지막 수정: 2026년 6월 16일 (현재 아키텍처 일괄 반영 — 2단계 파이프라인, Serper/NewsAPI 리서치, 검수 게이트 정규화, 발행 연동)
