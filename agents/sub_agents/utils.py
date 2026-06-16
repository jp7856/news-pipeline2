"""공통 유틸리티 — Claude JSON 응답 파싱."""

import json
import re


def parse_json(raw: str) -> dict:
    """Claude 응답에서 JSON을 추출하고 파싱한다.

    Claude가 반환하는 JSON 내 개행문자·제어문자 등을 자동으로 수정한다.
    """
    # 마크다운 코드 블록 제거
    raw = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()

    # 중괄호 범위 추출
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start != -1 and end > start:
        raw = raw[start:end]

    # 1차 시도: 그대로 파싱
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # 2차 시도: 문자열 내 이스케이프되지 않은 제어문자 수정
    try:
        fixed = _fix_json_strings(raw)
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    # 3차 시도: 제어문자 제거 후 파싱
    try:
        aggressive = re.sub(r'[\x00-\x1f\x7f]', ' ', raw)
        return json.loads(aggressive)
    except json.JSONDecodeError:
        pass

    # 4차 시도: 문자열 값 내 이스케이프 안 된 큰따옴표를 단따옴표로 교체
    try:
        fixed = _fix_inner_quotes(raw)
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    # 5차 시도: article 필드만 정규식으로 직접 추출
    try:
        return _extract_fields_regex(raw)
    except Exception as e:
        raise ValueError(f"JSON 파싱 실패: {e}\n원본(앞 200자): {raw[:200]}") from e


def _extract_fields_regex(raw: str) -> dict:
    """JSON 파싱이 모두 실패할 때 정규식으로 주요 필드를 직접 추출한다."""
    result = {}

    # article 필드 추출
    m = re.search(r'"article"\s*:\s*"(.*?)"\s*(?:,\s*"(?:vocabulary|sources)"|\s*\})', raw, re.DOTALL)
    if m:
        result["article"] = m.group(1).replace("\\n", "\n")

    # vocabulary 배열 추출
    m = re.search(r'"vocabulary"\s*:\s*(\[.*?\])', raw, re.DOTALL)
    if m:
        try:
            result["vocabulary"] = json.loads(m.group(1))
        except Exception:
            result["vocabulary"] = []

    # sources 배열 추출
    m = re.search(r'"sources"\s*:\s*(\[.*?\])', raw, re.DOTALL)
    if m:
        try:
            result["sources"] = json.loads(m.group(1))
        except Exception:
            result["sources"] = []

    if not result.get("article"):
        raise ValueError("article 필드를 추출하지 못했습니다.")

    return result


def parse_json_loose(raw: str) -> dict:
    """parse_json과 동일하지만 5차 시도에서 article 미발견 시 에러 대신 빈 dict 반환.
    워크북·크로스워드 등 article 구조가 없는 응답에 사용."""
    try:
        return parse_json(raw)
    except ValueError:
        return {}


def _fix_inner_quotes(raw: str) -> str:
    """JSON 문자열 값 내부의 이스케이프 안 된 큰따옴표를 단따옴표로 바꾼다."""
    result = []
    in_string = False
    escape_next = False
    i = 0

    while i < len(raw):
        ch = raw[i]

        if escape_next:
            result.append(ch)
            escape_next = False
            i += 1
            continue

        if ch == "\\":
            result.append(ch)
            escape_next = True
            i += 1
            continue

        if ch == '"':
            if not in_string:
                in_string = True
                result.append(ch)
            else:
                # 다음 non-space 문자 확인
                j = i + 1
                while j < len(raw) and raw[j] == ' ':
                    j += 1
                next_ch = raw[j] if j < len(raw) else ''
                # 문자열이 정상 종료되는 경우: 다음이 :, ,, }, ] 중 하나
                if next_ch in (':', ',', '}', ']', ''):
                    in_string = False
                    result.append(ch)
                else:
                    # 내부의 따옴표 → 단따옴표로 교체
                    result.append("'")
            i += 1
            continue

        if in_string:
            if ch == "\n":
                result.append("\\n")
            elif ch == "\r":
                result.append("\\r")
            elif ch == "\t":
                result.append("\\t")
            else:
                result.append(ch)
        else:
            result.append(ch)

        i += 1

    return "".join(result)


def _fix_json_strings(raw: str) -> str:
    """JSON 문자열 값 내의 이스케이프되지 않은 개행/탭을 수정한다."""
    result = []
    in_string = False
    escape_next = False

    for ch in raw:
        if escape_next:
            result.append(ch)
            escape_next = False
        elif ch == "\\":
            result.append(ch)
            escape_next = True
        elif ch == '"':
            result.append(ch)
            in_string = not in_string
        elif in_string:
            if ch == "\n":
                result.append("\\n")
            elif ch == "\r":
                result.append("\\r")
            elif ch == "\t":
                result.append("\\t")
            else:
                result.append(ch)
        else:
            result.append(ch)

    return "".join(result)
