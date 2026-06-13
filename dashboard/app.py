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

# 전체 히스토리 (모두 보기용)
_history: list[dict] = []


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
        def emit_log(msg: str):
            socketio.emit("log", {"message": msg}, to=sid)

        orchestrator = Orchestrator(log_callback=emit_log)
        pkg, sheet_url = orchestrator.run(topic, level, section, source_url=source_url, page=page)
        result = _serialize(pkg, sheet_url)

        # 히스토리에 저장
        entry = {
            "idx": len(_history),
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "topic": topic,
            "level": level.value,
            "section": section.value,
            "result": result,
        }
        _history.append(entry)

        # 요청한 사람에게만 결과 전송
        socketio.emit("pipeline_done", {"result": result}, to=sid)
    except Exception as e:
        socketio.emit("log", {"message": f"FATAL ERROR: {e}"}, to=sid)
        socketio.emit("pipeline_error", {"error": str(e)}, to=sid)
    finally:
        _running.pop(sid, None)


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
        "sheet_url": sheet_url,
        "status": pkg.status.value if hasattr(pkg.status, "value") else str(pkg.status),
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
