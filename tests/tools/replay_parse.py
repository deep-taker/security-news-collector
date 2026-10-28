"""실제 수집 원문을 파서로 다시 읽어 결과를 JSON으로 저장 (라이브러리·파서 변경 전후 비교용).

  python tests/tools/replay_parse.py <원문 폴더> <결과.json>
원문 파일 이름: <매체ID>-<YYYYMMDD-HHMM>[-pN].<xml|html>  (collect.py가 output/raw/에 남기는 형식)
"""
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.getcwd())   # 현재 폴더의 collector(이전 또는 변경본)를 쓴다

from collector.parsers import PARSERS
from collector.sources import SOURCE_BY_ID

NAME = re.compile(r"^(?P<src>[a-z_]+)-\d{8}-\d{4}(?:-p\d+)?\.(?:xml|html)$")


def main(raw_dir, out):
    result = {}
    for f in sorted(Path(raw_dir).rglob("*")):
        m = NAME.match(f.name)
        if not m or m["src"] not in SOURCE_BY_ID:
            continue
        src = SOURCE_BY_ID[m["src"]]
        try:
            items = PARSERS[src["kind"]](f.read_bytes(), src["url"])
            result[f.name] = [{k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in it.items()} for it in items]
        except Exception as e:
            result[f.name] = f"오류: {type(e).__name__}: {e}"
    Path(out).write_text(json.dumps(result, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")
    print(f"{len(result)}개 원문, 기사 {sum(len(v) for v in result.values() if isinstance(v, list))}건")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
