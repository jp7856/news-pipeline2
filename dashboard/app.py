"""웹 대시보드 — 토픽 입력 → 콘텐츠 제작 파이프라인 실행 → 결과 확인."""

import sys
import threading
import logging
from datetime import datetime
from pathlib import Path

from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, join_room

sys.path.insert(0, str(Path(__file__).parent.parent))
from orchestrator import Orchestrator
from models import ContentPackage, Level, Section

app = Flask(__name__)
app.config["SECRET_KEY"] = "news-pipeline-secret"
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
socketio = SocketIO(app, cors_allowed_origins="*")


@app.after_request
def add_no_cache(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

logger = logging.getLogger(__name__)

# sid → 현재 실행 중 여부
_running: dict[str, bool] = {}

# sid → 중단 요청 플래그 (협조적 취소)
_cancel: dict[str, bool] = {}

# 전체 히스토리 (모두 보기용)
_history: list[dict] = []


class PipelineCancelled(Exception):
    """사용자가 실행 중 파이프라인을 중단했을 때 발생."""


def _make_emit_log(sid: str):
    """로그 콜백 생성 — 호출 시점마다 중단 요청을 확인해 협조적으로 취소한다."""
    def emit_log(msg: str):
        if _cancel.get(sid):
            raise PipelineCancelled()
        socketio.emit("log", {"message": msg}, to=sid)
    return emit_log


@app.route("/")
def index():
    from config import PAGE_CONFIG
    levels = [{"value": lv.value, "label": lv.value.upper()} for lv in Level]
    sections = [{"value": sc.value, "label": sc.value} for sc in Section]
    # 신문별 지면 목록 (P1-1) — 프론트에서 레벨 선택 시 지면 드롭다운 갱신
    pages = {
        paper: [
            {"page": p["page"], "label": f"{p['page']} · {p['internal_level']}/{p['cefr']} · {p['word_min']}-{p['word_max']}w"}
            for p in plist
        ]
        for paper, plist in PAGE_CONFIG.items()
    }
    return render_template("index.html", levels=levels, sections=sections, pages=pages)


@app.route("/api/run", methods=["POST"])
def api_run():
    data = request.json
    sid = data.get("sid", "")
    topic = data.get("topic", "").strip()
    level_str = data.get("level", "junior")
    section_str = data.get("section", "환경")
    source_url = data.get("source_url", "").strip()
    page = data.get("page", "").strip()

    if not topic and not source_url:
        return jsonify({"error": "Topic or source URL is required."}), 400
    if not topic:
        topic = source_url  # URL만 있으면 URL을 토픽으로 사용
    if _running.get(sid):
        return jsonify({"error": "Pipeline already running."}), 409

    try:
        level = Level(level_str)
        section = Section(section_str)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    _running[sid] = True
    thread = threading.Thread(
        target=_run_pipeline, args=(sid, topic, level, section, source_url, page), daemon=True
    )
    thread.start()
    return jsonify({"message": "Pipeline started"})


@app.route("/api/stop", methods=["POST"])
def api_stop():
    """실행 중 파이프라인 중단 요청 — 다음 로그 시점에 협조적으로 취소된다."""
    data = request.json or {}
    sid = data.get("sid", "")
    if _running.get(sid):
        _cancel[sid] = True
        return jsonify({"message": "stopping"})
    return jsonify({"message": "not running"})


@app.route("/api/regenerate", methods=["POST"])
def api_regenerate():
    """확정 본문(버전 선택 P2-2 / 편집 반영 P2-3)으로 다운스트림 재생성."""
    data = request.json
    sid = data.get("sid", "")
    final_text = (data.get("final_text") or "").strip()
    topic = (data.get("topic") or "").strip()
    level_str = data.get("level", "junior")
    section_str = data.get("section", "환경")
    page = data.get("page", "").strip()
    sources = data.get("sources") or []

    if not final_text:
        return jsonify({"error": "final_text is required."}), 400
    if _running.get(sid):
        return jsonify({"error": "Pipeline already running."}), 409
    try:
        level = Level(level_str)
        section = Section(section_str)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    _running[sid] = True

    def _job():
        try:
            orchestrator = Orchestrator(log_callback=_make_emit_log(sid))
            pkg, sheet_url = orchestrator.rebuild_and_run(
                topic, level, section, final_text, page=page, sources=sources
            )
            result = _serialize(pkg, sheet_url)
            _history.append({
                "idx": len(_history),
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "topic": topic, "level": level.value, "section": section.value,
                "result": result,
            })
            from agents.token_meter import meter
            socketio.emit("pipeline_done", {"result": result, "usage": meter.snapshot()}, to=sid)
        except PipelineCancelled:
            socketio.emit("pipeline_stopped", {}, to=sid)
        except Exception as e:
            socketio.emit("pipeline_error", {"error": str(e)}, to=sid)
        finally:
            _running.pop(sid, None)
            _cancel.pop(sid, None)

    threading.Thread(target=_job, daemon=True).start()
    return jsonify({"message": "Rebuild started"})


@app.route("/api/revise", methods=["POST"])
def api_revise():
    """AI 어시스턴트 — 수정 지시 또는 질문을 받아 처리.
    - 수정 요청: 기사 본문을 수정하고 revised_text 반환
    - 질문: 기사에 대한 답변만 반환 (revised_text 없음)
    """
    data = request.json
    article_text = (data.get("article_text") or "").strip()
    instruction = (data.get("instruction") or "").strip()
    level_str = data.get("level", "junior")

    if not article_text:
        return jsonify({"error": "article_text is required."}), 400
    if not instruction:
        return jsonify({"error": "instruction is required."}), 400

    try:
        level = Level(level_str)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    try:
        from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, LEVEL_CONFIG
        from agents.token_meter import make_client
        cfg = LEVEL_CONFIG.get(level.value, {})
        client = make_client(ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2000,
            system=f"You are an expert editor for {cfg.get('newspaper','an educational newspaper')} targeting {cfg.get('target','')} at CEFR {cfg.get('cefr','')}. Answer in Korean.",
            messages=[{
                "role": "user",
                "content": (
                    f"Article:\n{article_text}\n\n"
                    f"User: {instruction}\n\n"
                    "Determine if this is a REVISION REQUEST or a QUESTION.\n"
                    "- If REVISION: respond with JSON {\"type\":\"revision\",\"message\":\"변경 내용 한 줄 요약\",\"revised_text\":\"전체 수정된 기사\"}\n"
                    "- If QUESTION: respond with JSON {\"type\":\"answer\",\"message\":\"답변 내용\"}\n"
                    "Respond ONLY with valid JSON."
                ),
            }],
        )
        import json as _json
        raw = msg.content[0].text.strip()
        # JSON 파싱
        try:
            result = _json.loads(raw)
        except Exception:
            # JSON 파싱 실패 시 답변으로 처리
            result = {"type": "answer", "message": raw}
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/publish", methods=["POST"])
def api_publish():
    """발행 — 최종 콘텐츠를 ne-times-site 레포의 articles.json에 커밋한다.
    GitHub Pages가 정적 파일을 그대로 서빙하므로 사이트에 즉시 반영된다."""
    import json as _json
    import base64
    import requests as _rq
    from config import GITHUB_TOKEN, GITHUB_SITE_REPO

    data = request.json or {}
    result = data.get("result")
    if not result or not result.get("article"):
        return jsonify({"error": "발행할 기사 데이터(result)가 없습니다."}), 400
    if not GITHUB_TOKEN:
        return jsonify({"error": "GITHUB_TOKEN 미설정 — Railway 환경변수에 GitHub 토큰을 넣어주세요."}), 500

    art_in = result.get("article", {})
    article = {
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "topic": result.get("topic", ""),
        "level": result.get("level", ""),
        "section": result.get("section", ""),
        "image_url": result.get("image_url", ""),
        "article": {
            "text": art_in.get("text", ""),
            "text_ko": art_in.get("text_ko", ""),
            "summary_ko": art_in.get("summary_ko", ""),
            "word_count": art_in.get("word_count", 0),
            "vocabulary": art_in.get("vocabulary", []),
        },
    }

    url = f"https://api.github.com/repos/{GITHUB_SITE_REPO}/contents/articles.json"
    headers = {"Authorization": f"Bearer {GITHUB_TOKEN}",
               "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28"}
    try:
        # 1) 기존 articles.json 읽기 (없으면 새로 생성)
        g = _rq.get(url, headers=headers, timeout=10)
        if g.status_code == 200:
            payload = g.json()
            sha = payload.get("sha")
            raw = base64.b64decode(payload.get("content", "")).decode("utf-8").strip()
            arr = _json.loads(raw) if raw else []
            if not isinstance(arr, list):
                arr = []
        elif g.status_code == 404:
            sha, arr = None, []
        else:
            return jsonify({"error": f"GitHub 읽기 실패 ({g.status_code}): {g.text[:200]}"}), 500

        arr.append(article)

        # 2) 커밋
        new_content = base64.b64encode(
            _json.dumps(arr, ensure_ascii=False, indent=1).encode("utf-8")
        ).decode("ascii")
        body = {"message": f"publish: {article['topic'][:60]}", "content": new_content}
        if sha:
            body["sha"] = sha
        p = _rq.put(url, headers=headers, json=body, timeout=15)
        if p.status_code in (200, 201):
            return jsonify({"ok": True, "count": len(arr),
                            "site": "https://jp7856.github.io/ne-times-site/"})
        return jsonify({"error": f"GitHub 커밋 실패 ({p.status_code}): {p.text[:200]}"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/usage")
def api_usage():
    """누적 토큰 사용량·비용 (서버 기동 이후)."""
    from agents.token_meter import meter
    return jsonify(meter.snapshot())


@app.route("/api/health/sheets")
def api_health_sheets():
    """구글시트 저장 실연결 진단 — 실제 시트 open을 시도하고 정확한 오류를 보고한다.
    서비스계정 이메일을 함께 반환하여 어떤 계정을 시트에 공유해야 하는지 알려준다."""
    import json as _json
    from config import GOOGLE_SHEETS_CREDENTIALS_JSON, GOOGLE_SHEET_ID
    _sid = (GOOGLE_SHEET_ID or "").strip()
    out = {"sheet_id_set": bool(_sid),
           "sheet_id": _sid,
           "sheet_url": (f"https://docs.google.com/spreadsheets/d/{_sid}" if _sid else None),
           "service_account_email": None, "step": None, "ok": False, "error": None}
    try:
        # 1) 자격증명 파싱 + 서비스계정 이메일 추출
        out["step"] = "credentials"
        creds_val = (GOOGLE_SHEETS_CREDENTIALS_JSON or "").strip()
        try:
            out["service_account_email"] = _json.loads(creds_val).get("client_email")
        except Exception:
            pass

        # 2) 실제 시트 open + 첫 행 읽기 시도
        out["step"] = "open_sheet"
        from agents.worksheet import WorksheetAgent
        agent = WorksheetAgent()
        sheet = agent._get_sheet()
        out["step"] = "read"
        title = sheet.title
        rows = len(sheet.get_all_values())
        out.update({"ok": True, "step": "done", "worksheet_title": title, "row_count": rows})
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
    return jsonify(out)


@app.route("/api/health")
def api_health():
    """배포 진단 — 환경변수 설정 여부만 보고 (값은 노출하지 않음)."""
    import os
    keys = [
        "ANTHROPIC_API_KEY", "SERPER_API_KEY", "NEWSAPI_KEY",
        "GOOGLE_SHEETS_CREDENTIALS_JSON", "GOOGLE_SHEET_ID", "UNSPLASH_ACCESS_KEY",
    ]
    status = {k: bool(os.getenv(k, "").strip()) for k in keys}
    return jsonify({
        "ok": True,
        "env": status,
        "research_ready": status["SERPER_API_KEY"] or status["NEWSAPI_KEY"],
        "sheets_ready": status["GOOGLE_SHEETS_CREDENTIALS_JSON"] and status["GOOGLE_SHEET_ID"],
    })


@app.route("/api/history")
def api_history():
    return jsonify(_history)


@app.route("/api/history/<int:idx>")
def api_history_item(idx):
    if idx < 0 or idx >= len(_history):
        return jsonify({"error": "Not found"}), 404
    return jsonify(_history[idx])


def _run_pipeline(sid: str, topic: str, level: Level, section: Section, source_url: str = "", page: str = ""):
    try:
        orchestrator = Orchestrator(log_callback=_make_emit_log(sid))
        # Phase 1만 실행 — 기사 초안 작성 후 사용자가 확인
        pkg = orchestrator.run_phase1(topic, level, section, source_url=source_url, page=page)
        result = _serialize(pkg, "")

        # 초안 완료 이벤트 (draft_done) — 이후 작업은 사용자가 [이후 작업 진행] 클릭 후 진행
        from agents.token_meter import meter
        socketio.emit("draft_done", {"result": result, "usage": meter.snapshot()}, to=sid)
    except PipelineCancelled:
        socketio.emit("pipeline_stopped", {}, to=sid)
    except Exception as e:
        socketio.emit("log", {"message": f"FATAL ERROR: {e}"}, to=sid)
        socketio.emit("pipeline_error", {"error": str(e)}, to=sid)
    finally:
        _running.pop(sid, None)
        _cancel.pop(sid, None)


def _serialize(pkg: ContentPackage, sheet_url: str = "") -> dict:
    return {
        "topic": pkg.topic,
        "level": pkg.level.value,
        "section": pkg.section.value,
        "article": {
            "text": pkg.article.text,
            "text_ko": pkg.article.text_ko,
            "summary_ko": pkg.article.summary_ko,
            "word_count": pkg.article.word_count,
            "vocabulary": pkg.article.vocabulary,
            "vocabulary_detail": [
                {"word": v.word, "cefr": v.cefr, "meaning_ko": v.meaning_ko}
                for v in pkg.article.vocabulary_detail
            ],
            "sources": pkg.article.sources,
        },
        "plagiarism": {
            "passed": pkg.plagiarism_report.passed,
            "checklist": pkg.plagiarism_report.checklist,
            "notes": pkg.plagiarism_report.notes,
        },
        "editing": [
            {"original": s.original, "suggestion": s.suggestion, "reason": s.reason}
            for s in pkg.editing_suggestions
        ],
        "crossword": [
            {
                "word": c.word,
                "korean_definition": c.korean_definition,
                "sentence_b1": c.sentence_b1,
                "sentence_b1_b2": c.sentence_b1_b2,
            }
            for c in pkg.crossword_sentences
        ],
        "workbook": [
            {
                "set_number": w.set_number,
                "format_key": w.format_key,
                "format_name": w.format_name,
                "activities": [
                    {"label": a.label, "title": a.title, "instruction": a.instruction,
                     "body": a.body, "answer": a.answer}
                    for a in w.activities
                ],
            }
            for w in pkg.workbook_sets
        ],
        "image_url": pkg.image_url,
        "image_query": pkg.image_query,
        "image_selected": ({
            "photographer": pkg.image_selected.photographer,
            "source": pkg.image_selected.source,
            "license": pkg.image_selected.license,
            "page_url": pkg.image_selected.page_url,
            "confirmed_date": pkg.image_selected.confirmed_date,
        } if pkg.image_selected else None),
        "image_candidates": [
            {"url": c.url, "thumb": c.thumb, "photographer": c.photographer, "page_url": c.page_url}
            for c in pkg.image_candidates
        ],
        "sheet_url": sheet_url,
        "status": pkg.status.value if hasattr(pkg.status, "value") else str(pkg.status),
        "alternate_text": pkg.alternate_text,
        "alternate_label": pkg.alternate_label,
        "selected_variant": pkg.selected_variant,
        "research": {
            "success": pkg.research.success if pkg.research else False,
            "sources": [
                {"url": s.url, "title": s.title}
                for s in (pkg.research.sources if pkg.research else [])
            ],
            "note": pkg.research.note if pkg.research else "",
        },
        "review": ({
            "passed": pkg.review_report.passed,
            "factual_issues": pkg.review_report.factual_issues,
            "temporal_issues": pkg.review_report.temporal_issues,
            "rewrite_count": pkg.review_report.rewrite_count,
            "needs_human_review": pkg.review_report.needs_human_review,
            "notes": pkg.review_report.notes,
        } if pkg.review_report else None),
    }


if __name__ == "__main__":
    import os
    logging.basicConfig(level=logging.INFO)
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host="0.0.0.0", port=port, debug=False, allow_unsafe_werkzeug=True)
