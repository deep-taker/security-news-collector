"""백업: Supabase Storage(비공개 보관함 'backups').
저장소 공개 전환으로 GitHub 보조 백업(data/backup/)은 중단 (사용자 결정 2026-10-27 — 공개 저장소에 기사 전체를 올리지 않음).

매일 06시판 준비 때 실행 (daily.py maintenance):
  1) 변경분: 전날(KST) 새로 수집됐거나 분류가 바뀐 기사 + 그날 갱신된 사건 + 그날 브리핑 + 매체 목록
     → Storage daily/YYYY/MM/YYYY-MM-DD.jsonl.gz  (60일 보관)
  2) 전체 사본: 일요일(weekly, 8개 보관)·매월 1일(monthly, 12개 보관), 보관함에 사본이 하나도 없을 때
     → Storage weekly/YYYY-MM-DD/<표>.partN.jsonl.gz + manifest.json
  3) 용량 상한 (사용자 결정: 전체 사용 가능 용량의 90%까지만)
     - Storage: 무료 1GB의 90% = 900MB, 파일 1개 50MB의 90% = 45MB (40MB에서 파일 분할)
     - 상한을 넘으면 오래된 것부터 정리: 변경분 → 주간 → 월간 (각각 최신 전체 사본 1개와 그 뒤 변경분은 항상 남김)

모든 결과는 backup_runs 표에 기록되고, 실패·용량 경고는 대시보드 '수집 상태'에 표시된다.
레코드 형식: 한 줄에 {"t": "<표 이름>", "r": {행}}
"""
import gzip
import hashlib
import io
import json
import os
import re
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

from . import store
from .parsers import KST

BUCKET = "backups"
TABLES = ("sources", "events", "articles", "briefings", "security_events")   # 복구 순서 (외래 키)
STORAGE_LIMIT = int(os.environ.get("BACKUP_STORAGE_LIMIT", 900 * 1000 * 1000))   # 1GB × 90% (시험용 덮어쓰기 가능)
FILE_LIMIT = 45 * 1000 * 1000             # 50MB × 90%
PART_ROTATE = int(os.environ.get("BACKUP_PART_ROTATE", 40 * 1000 * 1000))   # 이 크기를 넘으면 다음 파일로 분할
KEEP = {"daily": 60, "weekly": 8, "monthly": 12}
GITHUB_DIR = Path("data/backup")   # 옛 보조 백업 폴더 (쓰지 않음, 복구 도구 --from github가 로컬 사본을 읽을 때만)


# ---------- Storage REST ----------
def _h(extra=None):
    h = {"apikey": store.SUPABASE_KEY, "Authorization": f"Bearer {store.SUPABASE_KEY}"}
    h.update(extra or {})
    return h


def upload(path: str, data: bytes, content_type="application/gzip"):
    if len(data) > FILE_LIMIT:
        raise ValueError(f"{path}: {len(data)}바이트 — 파일 상한 {FILE_LIMIT} 초과")
    r = requests.post(f"{store.SUPABASE_URL}/storage/v1/object/{BUCKET}/{path}", data=data, timeout=120,
                      headers=_h({"Content-Type": content_type, "x-upsert": "true"}))
    r.raise_for_status()


def download(path: str) -> bytes:
    r = requests.get(f"{store.SUPABASE_URL}/storage/v1/object/authenticated/{BUCKET}/{path}", headers=_h(), timeout=120)
    r.raise_for_status()
    return r.content


def remove(paths: list):
    for i in range(0, len(paths), 100):
        r = requests.delete(f"{store.SUPABASE_URL}/storage/v1/object/{BUCKET}", timeout=60,
                            headers=_h({"Content-Type": "application/json"}), json={"prefixes": paths[i:i + 100]})
        r.raise_for_status()


def objects() -> list:
    return store.rpc("backup_objects") or []


# ---------- 내보내기 ----------
def day_window(d: date):
    start = datetime(d.year, d.month, d.day, tzinfo=KST)
    return start, start + timedelta(days=1)


def incremental_records(d: date):
    """d일(KST)에 생기거나 바뀐 것. 하루 창은 겹치지 않아 매일 파일을 이으면 빠짐이 없다."""
    s, e = (x.isoformat() for x in day_window(d))
    yield from (("sources", r) for r in store.select("sources", {"select": "*", "order": "id.asc"}))
    yield from (("events", r) for r in store.select("events", {"select": "*", "last_seen": f"gte.{d.isoformat()}", "order": "id.asc"}))
    seen = set()
    for flt in (f"(collected_at.gte.{s},collected_at.lt.{e})", f"(labeled_at.gte.{s},labeled_at.lt.{e})"):
        for r in store.select("articles", {"select": "*", "and": flt, "order": "id.asc"}):
            if r["id"] not in seen:
                seen.add(r["id"])
                yield "articles", r
    yield from (("briefings", r) for r in store.select("briefings", {"select": "*", "date": f"eq.{d.isoformat()}"}))
    yield from (("security_events", r) for r in store.select("security_events", {
        "select": "id,name,start_date,end_date,place,organizer,url,major,note,article_ids,first_seen,updated_at",
        "and": f"(updated_at.gte.{s},updated_at.lt.{e})", "order": "id.asc"}))


def full_records(table: str):
    order = "date.asc" if table == "briefings" else "id.asc"
    # security_events.name_key는 생성 열이라 복구 때 넣을 수 없으므로 빼고 백업
    sel = "id,name,start_date,end_date,place,organizer,url,major,note,article_ids,first_seen,updated_at" if table == "security_events" else "*"
    for r in store.select(table, {"select": sel, "order": order}):
        yield table, r


def gz_lines(records) -> tuple[bytes, int]:
    buf = io.BytesIO()
    n = 0
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as f:
        for t, r in records:
            f.write((json.dumps({"t": t, "r": r}, ensure_ascii=False, default=str) + "\n").encode())
            n += 1
    return buf.getvalue(), n


def gz_parts(records):
    """압축 크기가 PART_ROTATE를 넘으면 다음 파일로 나눈다 → [(bytes, 행 수)]."""
    parts, buf, f, n = [], None, None, 0

    def start():
        b = io.BytesIO()
        return b, gzip.GzipFile(fileobj=b, mode="wb", mtime=0)

    buf, f = start()
    for t, r in records:
        f.write((json.dumps({"t": t, "r": r}, ensure_ascii=False, default=str) + "\n").encode())
        n += 1
        if n % 200 == 0:
            f.flush()
            if buf.tell() > PART_ROTATE:
                f.close()
                parts.append((buf.getvalue(), n))
                buf, f, n = *start(), 0
    f.close()
    if n or not parts:
        parts.append((buf.getvalue(), n))
    return parts


# ---------- 용량 관리 ----------
def _kind(name):
    return name.split("/", 1)[0]


def _snapshot_key(name):
    """weekly/2026-11-01/articles.part1.jsonl.gz → ('weekly', '2026-11-01')"""
    k = _kind(name)
    if k == "daily":
        m = re.search(r"(\d{4}-\d{2}-\d{2})\.jsonl\.gz$", name)
        return k, m.group(1) if m else name
    return k, name.split("/")[1]


def complete_fulls(objs) -> set:
    """manifest.json까지 올라간 전체 사본만 '완성'으로 본다 (업로드 도중 실패한 사본은 기준본으로 쓰지 않음)."""
    return {_snapshot_key(o["name"]) for o in objs
            if _kind(o["name"]) in ("weekly", "monthly") and o["name"].endswith("/manifest.json")}


def prune(today: date, incoming: int = 0) -> dict:
    """보관 개수 정리 후 상한(90%)을 넘으면 오래된 것부터 삭제. 최신 전체 사본과 그 뒤 변경분은 남긴다.
    manifest 없는(미완성) 전체 사본은 항상 삭제한다."""
    objs = objects()
    groups = {}
    for o in objs:
        groups.setdefault(_snapshot_key(o["name"]), []).append(o)
    complete = complete_fulls(objs)
    incomplete = {key for key in groups if key[0] in ("weekly", "monthly") and key not in complete}
    by_kind = {k: sorted({key[1] for key in groups if key[0] == k and (k == "daily" or key in complete)}) for k in KEEP}
    doomed = set(incomplete)
    cutoff = (today - timedelta(days=KEEP["daily"])).isoformat()
    doomed |= {("daily", d) for d in by_kind["daily"] if d < cutoff}
    for k in ("weekly", "monthly"):
        doomed |= {(k, d) for d in by_kind[k][:-KEEP[k]]}

    fulls = sorted([(d if k == "weekly" else d + "-01", k, d) for k in ("weekly", "monthly") for d in by_kind[k]
                    if (k, d) not in doomed])
    latest_full = fulls[-1][0] if fulls else None
    used = sum(o["bytes"] for o in objs if _snapshot_key(o["name"]) not in doomed)
    # 상한 초과 시 추가 정리 순서: 최신 전체 사본 이전 변경분 → 오래된 주간 → 오래된 월간
    order = [("daily", d) for d in by_kind["daily"] if latest_full and d < latest_full]
    order += [("weekly", d) for d in by_kind["weekly"][:-1]] + [("monthly", d) for d in by_kind["monthly"][:-1]]
    for key in order:
        if used + incoming <= STORAGE_LIMIT:
            break
        if key in doomed:
            continue
        doomed.add(key)
        used -= sum(o["bytes"] for o in groups.get(key, []))
    paths = [o["name"] for key in doomed for o in groups.get(key, [])]
    if paths:
        remove(paths)
    return {"deleted_files": len(paths), "used": used, "fits": used + incoming <= STORAGE_LIMIT}


def log(target, kind, ok, files=0, nbytes=0, rows=0, used=None, limit=None, detail=None):
    print(f"[백업] {target}/{kind} {'성공' if ok else '실패'} 파일 {files} · {nbytes:,}B · {rows}행 · 사용 {used} / 상한 {limit} {detail or ''}")
    if store.enabled():
        try:
            store.insert("backup_runs", [{"target": target, "kind": kind, "ok": ok, "files": files, "bytes": nbytes,
                                          "rows_count": rows, "used_bytes": used, "limit_bytes": limit,
                                          "detail": (detail or "")[:500]}])
        except requests.RequestException as e:
            print(f"백업 기록 실패: {e}")


# ---------- 실행 ----------
def full_snapshot(prefix: str) -> tuple[int, int, int]:
    uploaded = []
    try:
        return _full_snapshot(prefix, uploaded)
    except Exception:
        try:   # 미완성 사본이 기준본으로 쓰이지 않도록 올린 조각을 지운다
            remove(uploaded)
        except requests.RequestException:
            pass   # 남아도 manifest가 없어 prune이 지움
        raise


def _full_snapshot(prefix: str, uploaded: list) -> tuple[int, int, int]:
    manifest = {"created_at": datetime.now(KST).isoformat(), "tables": {}}
    files = total = rows = 0
    for t in TABLES:
        parts = gz_parts(full_records(t))
        names = []
        for i, (data, n) in enumerate(parts, 1):
            name = f"{prefix}/{t}.part{i}.jsonl.gz"
            upload(name, data)
            uploaded.append(name)
            names.append({"file": name.split("/")[-1], "rows": n, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
            files += 1
            total += len(data)
            rows += n
        manifest["tables"][t] = names
    upload(f"{prefix}/manifest.json", json.dumps(manifest, ensure_ascii=False, indent=1).encode(), "application/json")
    return files + 1, total, rows


BACKFILL_DAYS = 7          # 최근 7일 중 빠진 변경분은 다음 백업 때 소급해 만든다
FIRST_DAY = date(2026, 10, 25)


def missing_days(today: date, have: set) -> list:
    start = max(FIRST_DAY, today - timedelta(days=BACKFILL_DAYS))
    days = [start + timedelta(days=i) for i in range((today - start).days)]
    return [d for d in days if d.isoformat() not in have]


def run(today: date):
    """today = 실행일(KST). 변경분은 전날(today-1) 기준이며, 최근 7일 중 빠진 날도 함께 만든다."""
    ok_all = True
    objs = objects() if store.enabled() else []
    have_storage = {_snapshot_key(o["name"])[1] for o in objs if _kind(o["name"]) == "daily"}
    want = sorted(set(missing_days(today, have_storage)) | {today - timedelta(days=1)})
    made = {}
    for d in want:
        made[d] = gz_lines(incremental_records(d))

    # 1) 주 백업: Storage
    for d, (data, n) in made.items():
        if d.isoformat() in have_storage and d != today - timedelta(days=1):
            continue
        rel = f"{d:%Y}/{d:%m}/{d:%Y-%m-%d}.jsonl.gz"
        try:
            p = prune(today, len(data))
            if not p["fits"]:
                raise RuntimeError("정리 후에도 90% 상한 초과")
            upload(f"daily/{rel}", data)
            note = [f"정리 {p['deleted_files']}개"] if p["deleted_files"] else []
            if d != today - timedelta(days=1):
                note.append(f"{d} 소급")
            log("storage", "daily", True, 1, len(data), n, p["used"] + len(data), STORAGE_LIMIT, " · ".join(note) or None)
        except Exception as e:
            ok_all = False
            log("storage", "daily", False, detail=f"{d}: {type(e).__name__}: {e}")

    kinds = []
    have_full = bool(complete_fulls(objects())) if store.enabled() else False
    if today.weekday() == 6 or not have_full:
        kinds.append(("weekly", f"weekly/{today.isoformat()}"))
    if today.day == 1:
        kinds.append(("monthly", f"monthly/{today:%Y-%m}"))
    for kind, prefix in kinds:
        try:
            fulls_now = [o for o in objects() if _kind(o["name"]) in ("weekly", "monthly")]
            est = sum(o["bytes"] for o in fulls_now) // max(1, len({_snapshot_key(o["name"]) for o in fulls_now}))
            p = prune(today, est)
            if not p["fits"]:
                raise RuntimeError("정리 후에도 90% 상한 초과")
            files, nbytes, rows = full_snapshot(prefix)
            used = sum(o["bytes"] for o in objects())
            log("storage", kind, used <= STORAGE_LIMIT, files, nbytes, rows, used, STORAGE_LIMIT)
            if used > STORAGE_LIMIT:
                prune(today)
        except Exception as e:
            ok_all = False
            log("storage", kind, False, detail=f"{type(e).__name__}: {e}")

    return ok_all


if __name__ == "__main__":
    import sys
    if not store.enabled():
        sys.exit("Supabase 환경변수가 없습니다.")
    sys.exit(0 if run(datetime.now(KST).date()) else 1)
