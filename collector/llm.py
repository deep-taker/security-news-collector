"""Gemini API 공통 호출 모듈 (한 줄 요약 · 칼럼 필자 · 브리핑 작성)."""
import os

import requests

API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_MODEL = "gemini-3.5-flash-lite"


def enabled() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY"))


def complete(
    system: str,
    user: str,
    max_tokens: int,
    *,
    model: str | None = None,
    response_mime_type: str | None = "application/json",
    thinking_level: str | None = None,
) -> dict:
    """Gemini generateContent 호출.

    반환: {"text": str, "in_tok": int, "out_tok": int, "truncated": bool, "finish_reason": str}
    - 도구·검색·코드 실행은 넣지 않는다(외부 기사 지시문 주입 방지).
    - 안전 필터 등으로 후보 응답이 비어 있으면 예외 없이 text=""로 반환해 호출 측이 묶음 실패로 처리한다.
    """
    model_id = model or os.environ.get("SUMMARY_MODEL") or DEFAULT_MODEL
    gen_cfg = {"maxOutputTokens": max_tokens}
    if response_mime_type:
        gen_cfg["responseMimeType"] = response_mime_type
    if thinking_level:
        gen_cfg["thinkingConfig"] = {"thinkingLevel": thinking_level}

    r = requests.post(
        f"{API_BASE}/{model_id}:generateContent",
        timeout=(10, 90),
        headers={
            "x-goog-api-key": os.environ["GEMINI_API_KEY"],
            "content-type": "application/json",
        },
        json={
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": gen_cfg,
        },
    )
    r.raise_for_status()
    body = r.json()
    cand = (body.get("candidates") or [{}])[0]
    parts = (cand.get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if isinstance(p, dict) and not p.get("thought"))
    finish = cand.get("finishReason") or (body.get("promptFeedback") or {}).get("blockReason") or ""
    usage = body.get("usageMetadata") or {}
    in_tok = int(usage.get("promptTokenCount") or 0)
    out_tok = int(usage.get("candidatesTokenCount") or 0) + int(usage.get("thoughtsTokenCount") or 0)
    return {
        "text": text,
        "in_tok": in_tok,
        "out_tok": out_tok,
        "truncated": finish == "MAX_TOKENS",
        "finish_reason": finish,
    }
