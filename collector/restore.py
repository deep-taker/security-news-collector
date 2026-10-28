"""백업에서 DB 복구.

  python -m collector.restore                     # 주 백업: Storage 최신 전체 사본 + 그 뒤 변경분
  python -m collector.restore --from github       # 옛 보조 백업(로컬 data/backup/ 사본) 변경분을 날짜순으로 — GitHub 보조 백업은 2026-10-27 중단
  python -m collector.restore --dry-run           # 내려받아 행 수만 확인 (DB에 쓰지 않음)

읽는 곳(백업)과 쓰는 곳(복구 대상 DB)을 나눌 수 있다:
  BACKUP_URL / BACKUP_KEY  → 백업을 내려받을 Supabase (기본: SUPABASE_URL / SUPABASE_SERVICE_KEY)
  SUPABASE_URL / SUPABASE_SERVICE_KEY → 복구 대상
복구는 같은 키(id, 브리핑은 날짜+판)로 덮어쓰기라 여러 번 실행해도 결과가 같다.
"""
import argparse
import gzip
import hashlib
import json
import os
import sys
from pathlib import Path

import requests

from . import backup, store

CONFLICT = {"sources": "id", "events": "id", "articles": "id", "briefings": "date,edition", "security_events": "id"}


def _src_headers():
    key = os.environ.get("BACKUP_KEY") or store.SUPABASE_KEY
    return key, {"apikey": key, "Authorization": f"Bearer {key}"}


def _src_url():
    return (os.environ.get("BACKUP_URL") or store.SUPABASE_URL).rstrip("/")


def src_objects():
    key, h = _src_headers()
    r = requests.post(f"{_src_url()}/rest/v1/rpc/backup_objects", headers={**h, "Content-Type": "application/json"},
                      data="{}", timeout=60)
    r.raise_for_status()
    return r.json()


def src_download(path):
    key, h = _src_headers()
    r = requests.get(f"{_src_url()}/storage/v1/object/authenticated/{backup.BUCKET}/{path}", headers=h, timeout=120)
    r.raise_for_status()
    return r.content


def parse(data: bytes, default_table="articles"):
    for line in gzip.decompress(data).decode("utf-8").splitlines():
        if not line.strip():
            continue
        o = json.loads(line)
        if "t" in o and "r" in o:
            yield o["t"], o["r"]
        else:                       # 2026-10-25 이전 형식: 기사 행만
            yield default_table, o


def plan_storage():
    """최신 전체 사본(파일 목록, 기준일) + 그 날짜 이후 변경분 목록."""
    objs = src_objects()
    complete = backup.complete_fulls(objs)          # manifest 있는 완성 사본만
    fulls = {}
    for o in objs:
        kind, key = backup._snapshot_key(o["name"])
        if kind in ("weekly", "monthly") and (kind, key) in complete:
            fulls.setdefault((key if kind == "weekly" else key + "-01", kind, key), []).append(o["name"])
    if not fulls:
        raise SystemExit("보관함에 전체 사본이 없습니다.")
    (base_date, kind, key), names = max(fulls.items())
    dailies = sorted((backup._snapshot_key(o["name"])[1], o["name"]) for o in objs
                     if o["name"].startswith("daily/") and backup._snapshot_key(o["name"])[1] >= base_date)
    return f"{kind}/{key}", base_date, [n for n in names if not n.endswith("manifest.json")], [n for _, n in dailies]


def load_full(prefix, names):
    manifest = json.loads(src_download(f"{prefix}/manifest.json"))
    files = {f["file"]: f for t in manifest["tables"].values() for f in t}
    by_table = {t: [] for t in backup.TABLES}
    for n in names:
        data = src_download(n)
        meta = files.get(n.split("/")[-1])
        if meta and hashlib.sha256(data).hexdigest() != meta["sha256"]:
            raise SystemExit(f"{n}: 체크섬 불일치 (손상된 백업)")
        for t, r in parse(data):
            by_table[t].append(r)
    for t, rows in by_table.items():
        expect = sum(f["rows"] for f in manifest["tables"].get(t, []))
        if len(rows) != expect:
            raise SystemExit(f"{t}: 행 수 {len(rows)} ≠ 사본 기록 {expect}")
    return by_table, manifest


def merge(state: dict, records):
    for t, r in records:
        k = (r["date"], r.get("edition", "am")) if t == "briefings" else r["id"]
        state.setdefault(t, {})[k] = r


def write(state: dict):
    for t in backup.TABLES:   # 매체 → 사건 → 기사 → 브리핑 순서 (외래 키)
        rows = list(state.get(t, {}).values())
        groups = {}   # 열 구성이 같은 행끼리 보낸다 (옛 백업에 없던 열이 있어도 실패하지 않도록 — PostgREST는 묶음 안 열 구성이 같아야 함)
        for r in rows:
            groups.setdefault(tuple(sorted(r)), []).append(r)
        for grp in groups.values():
            for i in range(0, len(grp), 500):
                store.upsert(t, grp[i:i + 500], CONFLICT[t])
        print(f"  {t}: {len(rows)}행 복구")
    try:
        print("  일련번호:", store.rpc("reset_sequences"))
    except requests.RequestException as e:
        print(f"  일련번호 맞추기 실패(수동 확인 필요): {e}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="src", choices=["storage", "github"], default="storage")
    ap.add_argument("--dir", default=str(backup.GITHUB_DIR))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--summary", help="복구 결과 요약 JSON 저장 경로")
    a = ap.parse_args()

    state, info = {}, {"from": a.src}
    if a.src == "storage":
        prefix, base_date, names, dailies = plan_storage()
        full, manifest = load_full(prefix, names)
        for t, rows in full.items():
            merge(state, ((t, r) for r in rows))
        for n in dailies:
            merge(state, parse(src_download(n)))
        info.update(base=prefix, base_date=base_date, base_created_at=manifest["created_at"], dailies=len(dailies),
                    last_daily=backup._snapshot_key(dailies[-1])[1] if dailies else None)
        print(f"전체 사본 {prefix} + 변경분 {len(dailies)}개")
    else:
        files = sorted(Path(a.dir).rglob("*.jsonl.gz"))
        for f in files:
            merge(state, parse(f.read_bytes()))
        info.update(files=len(files))
        print(f"저장소 변경분 {len(files)}개")

    info["rows"] = {t: len(state.get(t, {})) for t in backup.TABLES}
    print("복구 대상 행 수:", info["rows"])
    if a.summary:
        Path(a.summary).write_text(json.dumps({**info, "ids": {t: sorted(map(str, state.get(t, {}))) for t in ("articles", "events")}},
                                              ensure_ascii=False), encoding="utf-8")
    if not a.dry_run:
        if not store.enabled():
            sys.exit("복구 대상 DB 환경변수(SUPABASE_URL, SUPABASE_SERVICE_KEY)가 없습니다.")
        write(state)


if __name__ == "__main__":
    main()
