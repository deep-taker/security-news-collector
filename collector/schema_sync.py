"""운영 DB 정의를 저장소에 맞춘다 (매일 05:00 KST, schema-sync 워크플로).

DB 함수 export_definitions()가 내보낸 함수·색인·권한·정책·예약·보관함 정의를
supabase/generated/definitions.sql, 표 열 구성을 supabase/generated/columns.txt 로 저장한다.
바뀐 것이 있으면 워크플로가 커밋 → 저장소만으로 재구축 가능한 상태를 유지.
"""
from pathlib import Path

from . import store

OUT = Path("supabase/generated")


def main():
    d = store.rpc("export_definitions")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "definitions.sql").write_text(d["sql"], encoding="utf-8")
    (OUT / "columns.txt").write_text(d["columns"] + "\n", encoding="utf-8")
    print(f"정의 {len(d['sql']):,}자, 열 {d['columns'].count(chr(10)) + 1}개 저장 ({d['exported_at']})")


if __name__ == "__main__":
    main()
