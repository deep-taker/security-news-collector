"""운영 백업 복구 시험의 대조 단계 (월 1회, restore-test 워크플로).

복구된 시험 DB(직접 연결)와 운영 DB(REST, 읽기만)를 비교한다. 운영 DB는 백업 뒤에도 계속 바뀌므로
'백업 기준 시각(cutoff)' 이전에 생겨 그 뒤로 바뀌지 않은 행만 대조한다.
  python tests/restore_check.py <시험 DB DSN> <restore 요약 JSON>
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import psycopg
import requests

KST = timezone(timedelta(hours=9))
URL = os.environ["BACKUP_URL"].rstrip("/")
H = {"apikey": os.environ["BACKUP_KEY"], "Authorization": f"Bearer {os.environ['BACKUP_KEY']}"}


def prod(table, select, extra=None):
    rows, start = [], 0
    while True:
        r = requests.get(f"{URL}/rest/v1/{table}", params={"select": select, **(extra or {})}, timeout=60,
                         headers={**H, "Range-Unit": "items", "Range": f"{start}-{start + 999}"})
        r.raise_for_status()
        rows += r.json()
        if len(r.json()) < 1000:
            return rows
        start += 1000


def main():
    dsn, summary = sys.argv[1], json.load(open(sys.argv[2], encoding="utf-8"))
    base = datetime.fromisoformat(summary["base_created_at"])
    last_daily = summary.get("last_daily")
    cutoff = max(base, datetime.fromisoformat(last_daily).replace(tzinfo=KST) + timedelta(days=1)) if last_daily else base
    cut = cutoff.isoformat()
    problems = []
    with psycopg.connect(dsn) as c:
        got = {r[0]: r[1:] for r in c.execute("select id, url_hash, label, event_id from articles")}
        p = prod("articles", "id,url_hash,label,event_id,labeled_at", {"collected_at": f"lt.{cut}"})
        stable = [r for r in p if not r["labeled_at"] or datetime.fromisoformat(r["labeled_at"]) < cutoff]
        missing = [r["id"] for r in p if r["id"] not in got]
        diff = [r["id"] for r in stable if r["id"] in got and got[r["id"]] != (r["url_hash"], r["label"], r["event_id"])]
        if missing:
            problems.append(f"기사 누락 {len(missing)}건 (예: {missing[:5]})")
        if diff:
            problems.append(f"기사 내용 불일치 {len(diff)}건 (예: {diff[:5]})")
        ev = {r[0] for r in c.execute("select slug from events")}
        pe = [r["slug"] for r in prod("events", "slug", {"created_at": f"lt.{cut}"}) if r["slug"] not in ev]
        if pe:
            problems.append(f"사건 누락 {len(pe)}건")
        br = {(str(r[0]), r[1]) for r in c.execute("select date, edition from briefings")}
        pb = [(r["date"], r["edition"]) for r in prod("briefings", "date,edition", {"created_at": f"lt.{cut}"})
              if (r["date"], r["edition"]) not in br]
        if pb:
            problems.append(f"브리핑 누락 {len(pb)}건 {pb[:3]}")
        # 재구축 정의 점검: 저장소 schema.sql로 만든 시험 DB의 열 구성이 운영 DB와 같은지
        mine = c.execute("""select string_agg(format('%s.%s %s%s%s', table_name, column_name, data_type,
                                   case when is_nullable = 'NO' then ' not null' else '' end,
                                   coalesce(' default ' || column_default, '')), E'\\n' order by table_name, ordinal_position)
                            from information_schema.columns where table_schema = 'public'""").fetchone()[0]
        r = requests.post(f"{URL}/rest/v1/rpc/export_definitions", headers={**H, "Content-Type": "application/json"}, data="{}", timeout=60)
        r.raise_for_status()
        theirs = r.json()["columns"]
        mine, theirs = (x.replace("'public.", "'") for x in (mine, theirs))   # 검색 경로에 따른 스키마 표기 차이 무시
        if mine != theirs:
            a, b = set(mine.splitlines()), set(theirs.splitlines())
            problems.append(f"schema.sql 열 구성이 운영 DB와 다름: 운영에만 {sorted(b - a)[:3]}, 저장소에만 {sorted(a - b)[:3]}")
        fns = {r[0] for r in c.execute("select proname from pg_proc p join pg_namespace n on n.oid = p.pronamespace where n.nspname = 'public'")}
        need = {"apply_briefing", "apply_retention", "system_alerts", "system_alerts_public", "dispatch_github_workflow", "reset_sequences"}
        if need - fns:
            problems.append(f"재구축 정의에 없는 함수: {sorted(need - fns)}")
        counts = {t: c.execute(f"select count(*) from {t}").fetchone()[0] for t in ("sources", "events", "articles", "briefings")}
    result = {"ok": not problems, "cutoff": cut, "base": summary["base"], "dailies": summary["dailies"],
              "restored": counts, "checked_articles": len(p), "problems": problems}
    print(json.dumps(result, ensure_ascii=False, indent=1))
    requests.post(f"{URL}/rest/v1/backup_runs", headers={**H, "Content-Type": "application/json", "Prefer": "return=minimal"},
                  json=[{"target": "restore_test", "kind": "restore_test", "ok": not problems,
                         "rows_count": counts["articles"], "detail": json.dumps(result, ensure_ascii=False)[:500]}],
                  timeout=30).raise_for_status()
    sys.exit(0 if not problems else 1)


if __name__ == "__main__":
    main()
