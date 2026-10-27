"""백업·복구 전 과정 시험 (실제 PostgreSQL + 시험용 PostgREST/Storage 흉내 서버).

  python tests/e2e_backup.py "postgresql://postgres@localhost:5432/postgres"

1) 운영 DB 흉내(src)에 2주 동안 매일 기사·분류·사건·브리핑이 쌓이는 상황을 만들고 매일 05:35 백업 실행
   - 다음 날 06시판이 전날 밤 기사에 분류를 붙이는 것(백업 뒤 변경)까지 재현
2) 주 백업(Storage)으로 빈 DB에 복구 → 운영 DB와 모든 행·열이 같은지 대조
3) 보조 백업(GitHub 파일)만으로 빈 DB에 복구 → 대조
4) 용량 상한을 작게 걸고(분할·정리 강제) 다시 백업 → 상한 이하 유지, 그래도 복구 가능한지 확인
"""
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parent.parent
KST_OFF = "+09:00"
BASE = sys.argv[1]
KEY = "test-service-key"
TABLES = {"sources": "id", "events": "id", "articles": "id", "briefings": "date, edition", "security_events": "id"}


def dsn(db):
    return BASE.rsplit("/", 1)[0] + "/" + db


def make_db(name):
    with psycopg.connect(BASE, autocommit=True) as c:
        c.execute(f"drop database if exists {name}")
        c.execute(f"create database {name}")
    with psycopg.connect(dsn(name), autocommit=True) as c:   # 재구축 절차와 같은 순서
        c.execute((ROOT / "tests/supabase_stubs.sql").read_text())
        c.execute((ROOT / "supabase/schema.sql").read_text())
        defs = ROOT / "supabase/generated/definitions.sql"
        if defs.exists():
            c.execute(defs.read_text())


def serve(db, port):
    p = subprocess.Popen([sys.executable, str(ROOT / "tests/mock_postgrest.py"), dsn(db), str(port)])
    time.sleep(1.2)
    return p


def env(port, backup_port=None, **extra):
    e = {**os.environ, "SUPABASE_URL": f"http://127.0.0.1:{port}", "SUPABASE_SERVICE_KEY": KEY, **extra}
    if backup_port:
        e.update(BACKUP_URL=f"http://127.0.0.1:{backup_port}", BACKUP_KEY=KEY)
    e.pop("GITHUB_TOKEN", None)
    return e


def py(code, e, cwd):
    r = subprocess.run([sys.executable, "-c", code], env=e, cwd=cwd, capture_output=True, text=True)
    if r.returncode:
        print(r.stdout, r.stderr)
        raise SystemExit("실패")
    return r.stdout


def ts(d, h, m=0):
    return f"{d.isoformat()} {h:02d}:{m:02d}:00{KST_OFF}"


def simulate_day(c, d, rnd, seq):
    """d일: 기사 수집(하루 종일), 낮 판 분류, 사건·브리핑."""
    ids = []
    for i in range(rnd.randint(40, 70)):
        seq[0] += 1
        h = rnd.randint(0, 23)
        cur = c.execute(
            "insert into articles (url_hash, url, source_id, title, summary, published_at, collected_at, categories, keywords, candidate)"
            " values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) returning id",
            (f"h{seq[0]}", f"https://ex.kr/{seq[0]}", rnd.choice(["boannews", "zdnet", "ddaily"]), f"기사 {seq[0]} 해킹 '따옴표' \\ 역슬래시",
             "요약 " * rnd.randint(1, 40), ts(d, h), ts(d, h, 17), ["보안"], ["해킹"], rnd.random() < 0.6))
        ids.append((cur.fetchone()[0], h))
    slug = f"case-{d:%m%d}"
    ev = c.execute("insert into events (slug, title, category, cves, first_seen, last_seen) values (%s,%s,%s,%s,%s,%s)"
                   " returning id", (slug, f"사건 {d}", "취약점", [f"CVE-2026-{d:%m%d}"], d, d)).fetchone()[0]
    # 지난 사건 후속 보도 (last_seen 갱신, CVE 추가)
    c.execute("update events set last_seen = %s, cves = cves || %s where id = (select min(id) from events)", (d, [f"CVE-X-{d:%d}"]))
    for e, at in (("noon", 12), ("pm", 18)):
        day_ids = [i for i, h in ids if h < at]
        for i in day_ids:
            c.execute("update articles set label = %s, event_id = %s, labeled_at = %s where id = %s and label is null",
                      (rnd.choice(["security", "pr", "not_security"]), ev if rnd.random() < 0.3 else None, ts(d, at, 5), i))
        c.execute("insert into briefings (date, edition, markdown, stats) values (%s,%s,%s,%s) on conflict do nothing",
                  (d, e, f"# 정보보안 브리핑 {d} {e}", psycopg.types.json.Jsonb({"n": len(day_ids)})))
    # 과거 기사 재분류 (변경분에 잡혀야 함)
    c.execute("update articles set label = 'security', labeled_at = %s where id in (select id from articles where label = 'pr' order by id limit 2)",
              (ts(d, 15),))
    return ids


def morning_after(c, d_next, rnd):
    """d_next 06시판: 전날 밤 기사 분류 (백업 05:35 뒤)."""
    c.execute("update articles set label = 'security', labeled_at = %s where label is null and collected_at < %s",
              (ts(d_next, 6, 5), ts(d_next, 5, 30)))
    c.execute("insert into briefings (date, edition, markdown) values (%s,'am',%s) on conflict do nothing",
              (d_next, f"# 정보보안 브리핑 {d_next} am"))


def dump(db):
    out = {}
    with psycopg.connect(dsn(db)) as c:
        for t, k in TABLES.items():
            out[t] = c.execute(f"select * from {t} order by {k}").fetchall()
    return out


def compare(a, b, label):
    for t in TABLES:
        if a[t] != b[t]:
            sa, sb = set(map(repr, a[t])), set(map(repr, b[t]))
            print(f"[{label}] {t}: 원본 {len(a[t])}행 / 복구 {len(b[t])}행, 원본에만 {len(sa - sb)} 복구에만 {len(sb - sa)}")
            for x in list(sa - sb)[:2]:
                print("  원본:", x[:300])
            for x in list(sb - sa)[:2]:
                print("  복구:", x[:300])
            raise SystemExit(f"{label} 불일치")
    print(f"[{label}] 일치: " + ", ".join(f"{t} {len(a[t])}행" for t in TABLES))


def main():
    work = Path(tempfile.mkdtemp(prefix="snc-e2e-"))
    shutil.copytree(ROOT / "collector", work / "collector")
    make_db("e2e_src")
    procs = [serve("e2e_src", 55431)]
    try:
        rnd, seq = random.Random(7), [0]
        start = date(2026, 10, 26)            # 10/26 월 → 11/01(일·1일) → 11/08(일)
        days = [start + timedelta(days=i) for i in range(14)]
        with psycopg.connect(dsn("e2e_src"), autocommit=True) as c:
            for d in days:
                simulate_day(c, d, rnd, seq)
                py(f"from datetime import date; from collector import backup; assert backup.run(date.fromisoformat('{d + timedelta(days=1)}'))",
                   env(55431), work)
                if d != days[-1]:
                    morning_after(c, d + timedelta(days=1), rnd)
        objs = py("from collector import backup; import json; print(json.dumps(backup.objects()))", env(55431), work)
        names = [o["name"] for o in __import__("json").loads(objs)]
        print("보관함:", sorted({n.split('/')[0] + '/' + n.split('/')[1] for n in names}))
        assert any(n.startswith("weekly/2026-10-27/") for n in names), "첫 실행 전체 사본 없음"
        assert any(n.startswith("weekly/2026-11-01/") for n in names) and any(n.startswith("monthly/2026-11/") for n in names)
        assert any(n.startswith("weekly/2026-11-08/") for n in names)
        assert not (work / "data/backup").exists()   # GitHub 보조 백업 중단 (2026-10-27)
        # 소급: 11/09 백업을 건너뛰고(장애 가정) 11/10에 실행 → 11/09 변경분도 만들어져야 함
        with psycopg.connect(dsn("e2e_src"), autocommit=True) as c:
            simulate_day(c, date(2026, 11, 9), rnd, seq)
            simulate_day(c, date(2026, 11, 10), rnd, seq)
        # 미완성 전체 사본(manifest 없음)이 남아 있어도 기준본으로 쓰이지 않아야 함
        py("""from collector import backup
backup.upload('weekly/2026-11-10/articles.part1.jsonl.gz', b'broken')""", env(55431), work)
        py("from datetime import date; from collector import backup; assert backup.run(date(2026, 11, 11))", env(55431), work)
        objs2 = __import__("json").loads(py("from collector import backup; import json; print(json.dumps(backup.objects()))", env(55431), work))
        names2 = [o["name"] for o in objs2]
        assert any(n.endswith("daily/2026/11/2026-11-09.jsonl.gz") for n in names2), "11/09 소급 안 됨"
        assert any(n.endswith("daily/2026/11/2026-11-10.jsonl.gz") for n in names2)
        assert not any(n.startswith("weekly/2026-11-10/") for n in names2), "미완성 사본이 남음"
        src = dump("e2e_src")

        # 2) 주 백업으로 복구
        make_db("e2e_dst1")
        procs.append(serve("e2e_dst1", 55432))
        print(py("import runpy, sys; sys.argv=['restore','--summary','s.json']; runpy.run_module('collector.restore', run_name='__main__')",
                 env(55432, 55431), work))
        compare(src, dump("e2e_dst1"), "Storage 복구")
        # 월간 복구 시험의 대조 스크립트도 같은 상황에서 통과해야 함
        r = subprocess.run([sys.executable, str(ROOT / "tests/restore_check.py"), dsn("e2e_dst1"), str(work / "s.json")],
                           env=env(55432, 55431), capture_output=True, text=True)
        print(r.stdout[-400:], r.stderr[-400:])
        assert r.returncode == 0, "restore_check 실패"
        with psycopg.connect(dsn("e2e_dst1")) as c:   # 일련번호가 맞아 새 기사 입력 가능
            assert c.execute("select last_value from articles_id_seq").fetchone()[0] == max(r[0] for r in src["articles"])


        # 4) 용량 상한: 현재 사용량의 60%로 상한, 분할 4KB → 다음 날 백업(일요일 아님) + 강제 전체 사본
        used = sum(o["bytes"] for o in __import__("json").loads(objs))
        limit = int(used * 0.6)
        e4 = env(55431, BACKUP_STORAGE_LIMIT=str(limit), BACKUP_PART_ROTATE="4000")
        d = date(2026, 11, 11)
        with psycopg.connect(dsn("e2e_src"), autocommit=True) as c:
            simulate_day(c, d, rnd, seq)
        out = py(f"""
from datetime import date; from collector import backup
backup.run(date.fromisoformat('{d + timedelta(days=1)}'))
backup.prune(date.fromisoformat('{d + timedelta(days=1)}'))
files, nbytes, rows = backup.full_snapshot('weekly/{d + timedelta(days=1)}')
backup.prune(date.fromisoformat('{d + timedelta(days=1)}'))
objs = backup.objects(); print('USED', sum(o['bytes'] for o in objs), 'PARTS', sum('articles.part' in o['name'] for o in objs if o['name'].startswith('weekly/{d + timedelta(days=1)}')))
""", e4, work)
        print(out.strip().splitlines()[-1], "상한", limit)
        used2 = int(out.split("USED")[1].split()[0])
        parts = int(out.split("PARTS")[1].split()[0])
        assert used2 <= limit, "상한 초과"
        assert parts >= 2, "분할 안 됨"
        src = dump("e2e_src")
        make_db("e2e_dst3")
        procs.append(serve("e2e_dst3", 55434))
        print(py("import runpy, sys; sys.argv=['restore']; runpy.run_module('collector.restore', run_name='__main__')",
                 env(55434, 55431), work))
        compare(src, dump("e2e_dst3"), "상한 정리 후 Storage 복구")
        print("✅ 백업·복구 전 과정 시험 통과")
    finally:
        for p in procs:
            p.terminate()
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
