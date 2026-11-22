"""Gemini API 공통 호출 모듈 (한 줄 요약 · 칼럼 필자 · 브리핑 작성).

무료 등급 한도(RPM · TPM · KST 기준 RPD)를 넘지 않도록 60초 슬라이딩 윈도우 조절,
429 원인 분기(분당 한도 대기 재시도 vs 일일 한도 예비 모델 전환), 사전 토큰 추정을 지원한다.
"""
from datetime import datetime, timedelta, timezone
import json
import math
import os
from pathlib import Path
import re
import tempfile
import time

import requests

API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_MODEL = "gemini-3.5-flash-lite"
FALLBACK_MODEL = ""
DEFAULT_503_WAITS = (60.0, 180.0, 360.0, 600.0)   # 1분 -> 3분 -> 6분 -> 10분
SINGLE_MAX_TOKENS = int(os.environ.get("LLM_SINGLE_TPM_LIMIT", "170000"))
COUNT_TOKENS_MIN_CHARS = 30000

try:
    from zoneinfo import ZoneInfo
    KST = ZoneInfo("Asia/Seoul")
except Exception:
    KST = timezone(timedelta(hours=9))

# 무료 등급 공식 한도의 약 80% 안전선 (환경 변수로 상한 조정 가능)
MODEL_LIMITS = {
    "gemini-3.5-flash-lite": {"rpm": 12, "tpm": 200000, "rpd": 460},
}
DEFAULT_LIMIT = {"rpm": 12, "tpm": 200000, "rpd": 460}

_UNAVAILABLE_RE = re.compile(r"503|UNAVAILABLE|high demand", re.I)
_RATE_QUOTA_RE = re.compile(r"429|RESOURCE_EXHAUSTED|quota exceeded|rate limit", re.I)
_PAYMENT_RE = re.compile(r'prepayment credits|payment_required|"code":\s*402|status:\s*402', re.I)
_RETRY_SEC_RE = re.compile(r"retry\s+(?:in|after)\s+(\d+(?:\.\d+)?)s", re.I)
_DAILY_QUOTA_RE = re.compile(r"free_tier_requests|per day|daily", re.I)
_TPM_QUOTA_RE = re.compile(r"input_token_count|tokens per minute|per minute", re.I)
_TRANSIENT_RE = re.compile(r"HTTP 5\d\d|Timeout|ConnectionError|RemoteDisconnected", re.I)


class QuotaExhaustedError(requests.RequestException):
    """무료 API 분당/일일 한도 또는 과부하로 모든 모델 후보가 소진됨."""


class PaymentError(requests.RequestException):
    """선불 크레딧 소진 등 결제 오류(402)로 재시도 불가."""


def enabled() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY"))


def kst_day(now_ts: float | None = None) -> str:
    """한국 시각(KST) 기준 일자 문자열(YYYY-MM-DD)."""
    dt = datetime.fromtimestamp(now_ts if now_ts is not None else time.time(), KST)
    return dt.strftime("%Y-%m-%d")


def default_state_path() -> Path:
    env = os.environ.get("GEMINI_QUOTA_STATE")
    if env:
        return Path(env)
    base = os.environ.get("RUNNER_TEMP") or tempfile.gettempdir()
    return Path(base) / "snc_gemini_quota_state.json"


def model_limits(model_id: str) -> dict:
    base = dict(MODEL_LIMITS.get(model_id, DEFAULT_LIMIT))
    if os.environ.get("LLM_RPM_LIMIT"):
        base["rpm"] = int(os.environ["LLM_RPM_LIMIT"])
    if os.environ.get("LLM_TPM_LIMIT"):
        base["tpm"] = int(os.environ["LLM_TPM_LIMIT"])
    if os.environ.get("LLM_RPD_LIMIT"):
        base["rpd"] = int(os.environ["LLM_RPD_LIMIT"])
    return base


def estimate_tokens(system: str, user: str) -> int:
    """비ASCII(한글) 1.25토큰, ASCII 3.5자당 1토큰 + 여유 400토큰으로 보수 추정."""
    s = f"{system or ''}\n{user or ''}"
    non_ascii = sum(1 for ch in s if ord(ch) > 127)
    ascii_len = len(s) - non_ascii
    return math.ceil(non_ascii * 1.25 + ascii_len / 3.5) + 400


def count_tokens(system: str, user: str, *, model: str | None = None) -> tuple[int, bool]:
    """무료 `:countTokens` API로 정확한 입력 토큰 수 측정(RPD/TPM 미소모). 실패 시 추정값 폴백."""
    model_id = model or os.environ.get("SUMMARY_MODEL") or DEFAULT_MODEL
    fallback = estimate_tokens(system, user)
    if not enabled() or os.environ.get("LLM_DISABLE_COUNT_TOKENS") == "1":
        return fallback, False
    payload: dict = {"contents": [{"role": "user", "parts": [{"text": str(user or "")}]}]}
    if system:
        payload["systemInstruction"] = {"parts": [{"text": str(system)}]}
    try:
        r = requests.post(
            f"{API_BASE}/{model_id}:countTokens",
            timeout=(10, 20),
            headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"], "content-type": "application/json"},
            json=payload,
        )
        if getattr(r, "status_code", 200) < 400:
            body = r.json()
            total = body.get("totalTokens")
            if isinstance(total, int) and total > 0:
                return total, True
    except Exception:
        pass
    return fallback, False


def load_quota_state(state_path: Path | str, now_ts: float | None = None) -> dict:
    now = now_ts if now_ts is not None else time.time()
    day = kst_day(now)
    st = {}
    p = Path(state_path)
    try:
        if p.exists():
            loaded = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                st = loaded
    except Exception:
        st = {}
    if st.get("kstDay") != day:
        st = {"kstDay": day, "rpd": {}, "window": {}}
    rpd = st.get("rpd") if isinstance(st.get("rpd"), dict) else {}
    raw_win = st.get("window") if isinstance(st.get("window"), dict) else {}
    window = {}
    for m, entries in raw_win.items():
        if isinstance(entries, list):
            window[m] = [
                x for x in entries
                if isinstance(x, dict) and isinstance(x.get("ts"), (int, float)) and (now - x["ts"]) < 65.0
            ]
    return {"kstDay": day, "rpd": rpd, "window": window}


def save_quota_state(state_path: Path | str, st: dict) -> None:
    try:
        p = Path(state_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def record_call_usage(state_path: Path | str, model_id: str, tokens: int, now_ts: float | None = None) -> dict:
    now = now_ts if now_ts is not None else time.time()
    st = load_quota_state(state_path, now)
    st["rpd"][model_id] = int(st["rpd"].get(model_id, 0)) + 1
    win = [x for x in st["window"].get(model_id, []) if (now - x["ts"]) < 65.0]
    win.append({"ts": now, "tokens": max(0, int(tokens or 0))})
    st["window"][model_id] = win
    save_quota_state(state_path, st)
    return st


def wait_for_budget(
    model_id: str,
    est_tokens: int,
    *,
    state_path: Path | str | None = None,
    limits: dict | None = None,
    sleep_fn=None,
    now_fn=None,
    wait_cap_s: float | None = None,
) -> dict:
    """60초 슬라이딩 윈도우(RPM/TPM)와 KST 일일 RPD 예산 안에서 호출 가능 시점까지 대기."""
    p = Path(state_path) if state_path else default_state_path()
    lim = dict(model_limits(model_id))
    if limits:
        lim.update(limits)
    do_sleep = sleep_fn or time.sleep
    now = now_fn or time.time

    for _ in range(10):
        t_now = now()
        st = load_quota_state(p, t_now)
        used_rpd = int(st["rpd"].get(model_id, 0))
        if used_rpd >= lim["rpd"]:
            return {"ok": False, "reason": "RPD", "used_rpd": used_rpd, "limit_rpd": lim["rpd"]}

        win = [x for x in st["window"].get(model_id, []) if (t_now - x["ts"]) < 60.0]
        cur_rpm = len(win)
        cur_tpm = sum(int(x.get("tokens") or 0) for x in win)
        need_rpm = cur_rpm >= lim["rpm"]
        need_tpm = bool(win) and (cur_tpm + est_tokens > lim["tpm"])
        if not need_rpm and not need_tpm:
            return {"ok": True, "used_rpd": used_rpd, "cur_rpm": cur_rpm, "cur_tpm": cur_tpm}

        wait_until = win[0]["ts"] + 61.0
        if not need_rpm and need_tpm:
            acc = cur_tpm
            for item in win:
                acc -= int(item.get("tokens") or 0)
                wait_until = item["ts"] + 61.0
                if acc + est_tokens <= lim["tpm"]:
                    break
        wait_s = max(1.0, wait_until - t_now)
        if wait_cap_s is not None:
            wait_s = min(wait_cap_s, wait_s)
        print(
            f"[quota-pacer] {model_id} 한도 보호 대기 {wait_s:.1f}초 "
            f"(최근60초 {cur_rpm}/{lim['rpm']}회, {cur_tpm}+{est_tokens}/{lim['tpm']}토큰, KST 일일 {used_rpd}/{lim['rpd']}회)"
        )
        do_sleep(wait_s)
    return {"ok": True}


def is_tpm_limit(msg: str) -> bool:
    if _DAILY_QUOTA_RE.search(msg):
        return False
    if _TPM_QUOTA_RE.search(msg):
        return True
    m = _RETRY_SEC_RE.search(msg)
    return bool(m and float(m.group(1)) <= 90.0)


def extract_retry_wait_sec(msg: str, cap_s: float | None = None) -> float:
    m = _RETRY_SEC_RE.search(msg)
    raw = (math.ceil(float(m.group(1))) + 5) if m else 65
    clamped = float(min(75, max(40, raw)))
    return min(cap_s, clamped) if cap_s is not None else clamped


def unavailable_waits(waits: tuple[float, ...] | list[float] | None = None) -> tuple[float, ...]:
    """503 서버 과부하 시 재시도 대기 시간(초) 목록. 기본값 1분 -> 3분 -> 6분 -> 10분."""
    if waits is not None:
        return tuple(float(w) for w in waits)
    raw = (os.environ.get("LLM_503_WAITS") or "").strip()
    if not raw:
        return DEFAULT_503_WAITS
    out = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        val = float(part)
        if val >= 0:
            out.append(val)
    return tuple(out)


def _sanitize_err(err: Exception | str) -> str:
    msg = str(err or "")
    key = os.environ.get("GEMINI_API_KEY", "")
    if key:
        msg = msg.replace(key, "***")
    return msg


def _post_generate(
    model_id: str,
    system: str,
    user: str,
    max_tokens: int,
    *,
    response_mime_type: str | None = "application/json",
    thinking_level: str | None = None,
) -> dict:
    gen_cfg: dict = {"maxOutputTokens": max_tokens}
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
    status = getattr(r, "status_code", 200)
    if isinstance(status, int) and status >= 400:
        err_text = (getattr(r, "text", "") or "")[:600]
        try:
            err_json = r.json()
            err_msg = (err_json.get("error") or {}).get("message") or err_text
        except Exception:
            err_msg = err_text
        exc = requests.HTTPError(f"HTTP {status}: {err_msg}", response=r)
        raise exc
    try:
        r.raise_for_status()
    except requests.HTTPError as e:
        resp_text = (getattr(getattr(e, "response", None), "text", "") or "")[:600]
        if resp_text and resp_text not in str(e):
            raise requests.HTTPError(f"{e} {resp_text}", response=e.response) from e
        raise
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


def complete(
    system: str,
    user: str,
    max_tokens: int,
    *,
    model: str | None = None,
    fallback_model: str | None = FALLBACK_MODEL,
    response_mime_type: str | None = "application/json",
    thinking_level: str | None = None,
    use_count_tokens: bool | None = None,
    state_path: Path | str | None = None,
    retry_503_waits: tuple[float, ...] | list[float] | None = None,
    sleep_fn=None,
    now_fn=None,
) -> dict:
    """Gemini generateContent 호출 (한도 조절 · 503/429 대기 재시도 포함).

    반환: {"text": str, "in_tok": int, "out_tok": int, "truncated": bool, "finish_reason": str}
    - 도구·검색·코드 실행은 넣지 않는다(외부 기사 지시문 주입 방지).
    - 안전 필터 등으로 후보 응답이 비어 있으면 예외 없이 text=""로 반환해 호출 측이 묶음 실패로 처리한다.
    """
    primary = model or os.environ.get("SUMMARY_MODEL") or DEFAULT_MODEL
    fb = os.environ.get("FALLBACK_MODEL", fallback_model or "") if fallback_model is not None else ""
    models = [primary]
    if fb and fb != primary:
        models.append(fb)

    p = Path(state_path) if state_path else default_state_path()
    do_sleep = sleep_fn or time.sleep
    now = now_fn or time.time
    use_exact = use_count_tokens if use_count_tokens is not None else (len(system or "") + len(user or "") >= COUNT_TOKENS_MIN_CHARS)
    waits_503 = unavailable_waits(retry_503_waits)

    last_err: Exception | None = None
    quota_exhausted = False
    for m_idx, m in enumerate(models):
        est_tok = count_tokens(system, user, model=m)[0] if use_exact else estimate_tokens(system, user)
        tpm_retried = False
        unavailable_idx = 0
        transient_retried = False
        while True:
            budget = wait_for_budget(m, est_tok, state_path=p, sleep_fn=do_sleep, now_fn=now)
            if not budget.get("ok"):
                quota_exhausted = True
                last_err = QuotaExhaustedError(f"{m} KST 일일 안전 예산({budget['used_rpd']}/{budget['limit_rpd']}) 도달")
                if m_idx + 1 < len(models):
                    print(f"[quota-pacer] {last_err} - 다음 예비 모델 확인")
                else:
                    print(f"[quota-pacer] {last_err}")
                break
            try:
                res = _post_generate(
                    m,
                    system,
                    user,
                    max_tokens,
                    response_mime_type=response_mime_type,
                    thinking_level=thinking_level,
                )
                actual_in = res["in_tok"] if res["in_tok"] > 0 else est_tok
                record_call_usage(p, m, actual_in, now())
                if m_idx > 0:
                    print(f"[llm] 예비 모델({m}) 전환 성공")
                return res
            except requests.RequestException as e:
                msg = _sanitize_err(e)
                last_err = e
                status = getattr(getattr(e, "response", None), "status_code", None)
                if status == 402 or _PAYMENT_RE.search(msg):
                    raise PaymentError(f"결제 오류(402): {msg[:250]}") from e
                is_503 = status == 503 or bool(_UNAVAILABLE_RE.search(msg))
                if is_503:
                    if unavailable_idx < len(waits_503):
                        wait_s = waits_503[unavailable_idx]
                        unavailable_idx += 1
                        print(
                            f"[llm] {m} 서버 일시 과부하(503) - "
                            f"{wait_s:.0f}초 대기 후 재시도 ({unavailable_idx}/{len(waits_503)}): {msg[:120]}"
                        )
                        do_sleep(wait_s)
                        continue
                    quota_exhausted = True
                    if m_idx + 1 < len(models):
                        print(f"[llm] {m} 서버 일시 과부하(503) 재시도 소진 - 예비 모델 전환 확인")
                    else:
                        print(f"[llm] {m} 서버 일시 과부하(503) {len(waits_503)}회 재시도 후에도 응답 불가")
                    break
                if status == 429 or _RATE_QUOTA_RE.search(msg):
                    record_call_usage(p, m, est_tok, now())
                    if not tpm_retried and is_tpm_limit(msg):
                        tpm_retried = True
                        wait_s = extract_retry_wait_sec(msg)
                        print(f"[llm] {m} 분당 한도(TPM) 감지 - {wait_s:.0f}초 대기 후 같은 모델 재시도")
                        do_sleep(wait_s)
                        continue
                    quota_exhausted = True
                    if m_idx + 1 < len(models):
                        print(f"[llm] {m} 일일 한도(429) 감지({msg[:140]}) - 예비 모델 전환 확인")
                    else:
                        print(f"[llm] {m} 일일 한도(429) 도달({msg[:140]})")
                    break
                is_transient = (
                    isinstance(e, (requests.Timeout, requests.ConnectionError))
                    or (isinstance(status, int) and status >= 500)
                    or bool(_TRANSIENT_RE.search(msg))
                )
                if not transient_retried and is_transient:
                    transient_retried = True
                    print(f"[llm] {m} 일시 오류로 3초 후 1회 재시도: {msg[:140]}")
                    do_sleep(3.0)
                    continue
                raise

    if quota_exhausted:
        raise QuotaExhaustedError(_sanitize_err(last_err or "무료 Gemini API 한도 초과 또는 일시 과부하"))
    if last_err:
        raise last_err
    raise QuotaExhaustedError("무료 Gemini API 한도 초과 또는 일시 과부하")
