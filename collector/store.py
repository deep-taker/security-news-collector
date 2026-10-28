"""Supabase(PostgREST) 접근. 환경변수가 없으면 시험 모드(파일 출력)로 동작."""
import json
import os

import requests

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")


def enabled() -> bool:
    return bool(SUPABASE_URL and SUPABASE_KEY)


def _headers(extra=None):
    h = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    if extra:
        h.update(extra)
    return h


def insert_ignore(table: str, rows: list, conflict: str):
    """중복(conflict 열)은 건너뛰고 새로 들어간 행만 돌려준다."""
    if not rows:
        return []
    r = requests.post(
        f"{SUPABASE_URL}/rest/v1/{table}?on_conflict={conflict}",
        headers=_headers({"Prefer": "resolution=ignore-duplicates,return=representation"}),
        data=json.dumps(rows, ensure_ascii=False, default=str).encode("utf-8"),
        timeout=60,
    )
    r.raise_for_status()
    return r.json()


def upsert(table: str, rows: list, conflict: str):
    if not rows:
        return []
    r = requests.post(
        f"{SUPABASE_URL}/rest/v1/{table}?on_conflict={conflict}",
        headers=_headers({"Prefer": "resolution=merge-duplicates,return=minimal"}),
        data=json.dumps(rows, ensure_ascii=False, default=str).encode("utf-8"),
        timeout=60,
    )
    r.raise_for_status()


def insert(table: str, rows: list):
    if not rows:
        return
    r = requests.post(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers=_headers({"Prefer": "return=minimal"}),
        data=json.dumps(rows, ensure_ascii=False, default=str).encode("utf-8"),
        timeout=60,
    )
    r.raise_for_status()


def patch(table: str, match: dict, values: dict):
    r = requests.patch(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers=_headers({"Prefer": "return=minimal"}),
        params=match,
        data=json.dumps(values, ensure_ascii=False, default=str).encode("utf-8"),
        timeout=30,
    )
    r.raise_for_status()


def select(table: str, params: dict, page_size: int = 1000):
    """조건에 맞는 모든 행을 페이지 단위로 읽는다. params에 limit이 있으면 그 개수까지만 (한 번 요청)."""
    out, start = [], 0
    cap = int(params["limit"]) if "limit" in params else None
    params = {k: v for k, v in params.items() if k != "limit"}
    while True:
        size = page_size if cap is None else min(page_size, cap - len(out))
        if size <= 0:
            return out
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers=_headers({"Range-Unit": "items", "Range": f"{start}-{start + size - 1}"}),
            params=params,
            timeout=60,
        )
        if r.status_code == 416:      # 범위 밖 = 더 읽을 행 없음
            return out
        r.raise_for_status()
        batch = r.json()
        out.extend(batch)
        if len(batch) < size:
            return out
        start += size


def rpc(fn: str, payload: dict | None = None):
    r = requests.post(
        f"{SUPABASE_URL}/rest/v1/rpc/{fn}",
        headers=_headers(),
        data=json.dumps(payload or {}, ensure_ascii=False, default=str).encode("utf-8"),
        timeout=120,
    )
    r.raise_for_status()
    return r.json() if r.content else None
