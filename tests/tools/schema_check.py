"""저장소 정의만으로 빈 DB를 만들 수 있는지, 표 열 구성이 운영 DB와 같은지 점검 (매일, schema-sync 워크플로).

  python tests/tools/schema_check.py <시험 DB 주소>
supabase/generated/columns.txt(방금 운영에서 내보낸 열 구성)와 비교. 결과는 backup_runs(schema_check)에 기록 →
실패하면 대시보드에 '재구축 정의 점검 실패' 오류로 표시된다.
"""
import json
import os
import re
import sys
from pathlib import Path

import requests

COLS = """select string_agg(format('%s.%s %s%s%s', table_name, column_name, data_type,
            case when is_nullable = 'NO' then ' not null' else '' end, coalesce(' default ' || column_default, '')),
            E'\\n' order by table_name, ordinal_position) from information_schema.columns where table_schema = 'public'"""


# 'to public' 권한(모든 역할 허용)은 이 프로젝트에서 쓰지 않는다. 운영 DB에 다시 생기면 export_definitions가
# 그대로 내보내므로(2026-10-27) 여기서 실패로 잡는다 → 대시보드 '재구축 정의 점검 실패'.
_PUBLIC_GRANT = re.compile(r"^grant [^;]* to (?:[^;]*,\s*)?public\s*(?:,[^;]*)?;", re.I | re.M)


def public_grants(sql: str) -> list:
    return [m.group(0)[:160] for m in _PUBLIC_GRANT.finditer(sql)]


def main(dsn):
    import psycopg   # 점검 실행 때만 필요 (public_grants 단위 시험은 psycopg 없이)
    problems = []
    pub = public_grants(Path("supabase/generated/definitions.sql").read_text())
    if pub:
        problems.append(f"PUBLIC(모든 역할) 권한 {len(pub)}건 — 운영 DB 권한 퇴행: {pub[:2]}")
    try:
        with psycopg.connect(dsn, autocommit=True) as c:
            for f in ("tests/supabase_stubs.sql", "supabase/schema.sql", "supabase/generated/definitions.sql"):
                try:
                    c.execute(Path(f).read_text())
                except psycopg.Error as e:
                    problems.append(f"{f} 적용 실패: {str(e).splitlines()[0][:200]}")
                    break
            mine = c.execute(COLS).fetchone()[0] or ""
    except psycopg.Error as e:
        problems.append(f"시험 DB 연결 실패: {e}")
        mine = ""
    theirs = Path("supabase/generated/columns.txt").read_text().strip()
    a = set(mine.replace("'public.", "'").splitlines())
    b = set(theirs.replace("'public.", "'").splitlines())
    if not problems and a != b:
        problems.append(f"schema.sql 열 구성이 운영과 다름 — 운영에만: {sorted(b - a)[:4]}, 저장소에만: {sorted(a - b)[:4]}")
    ok = not problems
    print("통과" if ok else "\n".join(problems))
    url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SERVICE_KEY")
    if url and key:
        requests.post(f"{url.rstrip('/')}/rest/v1/backup_runs", timeout=30,
                      headers={"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json", "Prefer": "return=minimal"},
                      json=[{"target": "schema_check", "kind": "schema_check", "ok": ok,
                             "detail": ("재구축 정의 점검 통과" if ok else "재구축 정의 점검: " + " / ".join(problems))[:500]}]).raise_for_status()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main(sys.argv[1])
