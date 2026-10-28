"""두 파싱 결과(JSON) 비교. 하나라도 다르면 종료 코드 1.  python tests/tools/replay_compare.py <이전.json> <새.json>"""
import json
import sys

a, b = (json.load(open(p, encoding="utf-8")) for p in sys.argv[1:3])
diffs = 0
for name in sorted(set(a) | set(b)):
    x, y = a.get(name), b.get(name)
    if x == y:
        continue
    diffs += 1
    if diffs <= 15:
        if isinstance(x, list) and isinstance(y, list):
            ka = {i["url"]: i for i in x}; kb = {i["url"]: i for i in y}
            only_a, only_b = set(ka) - set(kb), set(kb) - set(ka)
            changed = [u for u in set(ka) & set(kb) if ka[u] != kb[u]]
            print(f"- {name}: 이전 {len(x)}건 / 새 {len(y)}건, 이전에만 {len(only_a)}, 새에만 {len(only_b)}, 내용 다름 {len(changed)}")
            for u in changed[:2]:
                for k in ka[u]:
                    if ka[u][k] != kb[u].get(k):
                        print(f"    {k}: {str(ka[u][k])[:80]!r} → {str(kb[u].get(k))[:80]!r}")
        else:
            print(f"- {name}: {str(x)[:120]} → {str(y)[:120]}")
total = len(set(a) | set(b))
items = sum(len(v) for v in a.values() if isinstance(v, list))
print(f"원문 {total}개(기사 {items}건) 중 결과가 다른 원문 {diffs}개")
sys.exit(1 if diffs else 0)
