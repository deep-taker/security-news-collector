"""브리핑 반영 검증 (sync_briefing 직후 실행).

1) 형식: 출력 JSON의 판·날짜, 라벨 값, 사건 slug 형식, 통계(stats) 일치
2) 누락: 입력 파일의 모든 후보 기사에 라벨이 붙었는지, 입력에 없는 기사 id가 섞이지 않았는지
3) 사건 연결: 라벨의 event_slug가 이번 판 사건 또는 최근 사건 목록에 있는지
4) 본문: 브리핑 마크다운이 있고 제목·판 표기·필수 절이 있는지
5) DB: briefings 행 존재·본문 일치, 라벨이 실제 기사에 반영됐는지, 사건이 저장됐는지
6) 대시보드: https://briefing-security.vercel.app/b/<날짜-판> 이 열리고 브리핑이 보이는지

결과는 briefing_checks 표에 남기고(대시보드 '수집 상태'에 실패 표시), 실패하면 종료 코드 1.
"""
import json
import os
import re
import sys
from pathlib import Path

import requests

from . import store

LABEL_NAME = {"am": "06시판", "noon": "12시판", "pm": "18시판", "week": "주간 요약"}
VALID = {"security", "trend", "pr", "column", "not_security"}
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
HANGUL = re.compile(r"[가-힣]")
DASHBOARD = os.environ.get("DASHBOARD_URL", "https://briefing-security.vercel.app").rstrip("/")


# 브리핑 본문 링크로 허용하는 도메인 (수집 매체 9곳의 기사 주소). 외부 기사 내용의 숨은 지시로
# 엉뚱한 주소가 공개 대시보드에 실리는 것을 막는다.
ARTICLE_DOMAINS = ("boannews.com", "dailysecu.com", "etnews.com", "dt.co.kr", "digitaltoday.co.kr",
                   "aitimes.com", "bloter.net", "zdnet.co.kr", "ddaily.co.kr", "it.chosun.com", "it.donga.com")
LINK = re.compile(r"\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)|<(https?://[^>\s]+)>|(?<![(<\w])(https?://[^\s)<>\]]+)")


def check_links(markdown: str, input_urls: set) -> list:
    """링크가 ① 이번 판 입력 기사 주소이거나 ② 수집 매체 도메인의 https/http 주소인지."""
    from urllib.parse import urlsplit
    problems = []
    for m in LINK.finditer(markdown):
        url = next(g for g in m.groups() if g)
        if url in input_urls:
            continue
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        ok_scheme = parts.scheme in ("http", "https")
        ok_host = any(host == d or host.endswith("." + d) for d in ARTICLE_DOMAINS)
        if not (ok_scheme and ok_host) or parts.username or parts.password or parts.port not in (None, 80, 443):
            problems.append(url[:120])
    return problems


SECTION_ORDER = ["주요 사건", "기타 사건", "AI 보안", "정책", "국방", "보안 동향", "업계 동향", "칼럼", "보안 행사"]   # 2026-10-31 보안 동향·칼럼 추가
SRC_LINK = re.compile(r'\[[^\]]+\]\(\s*<?[^)\s>]+>?\s+"보도:[^"]+"\s*\)')


def check_format(markdown: str, edition: str) -> list:
    """2026-10-27 개편 형식 점검(주의 수준): 절 순서, '수집 상태' 절 없음, 제목 링크의 보도 매체 문구, 항목별 2줄."""
    warns = []
    heads = [h.strip() for h in re.findall(r"^##\s+(.+)$", markdown, re.M)]
    if any("수집 상태" in h for h in heads):
        warns.append("'수집 상태' 절이 있음 (개편 형식에서는 쓰지 않음)")
    if edition == "week":
        return warns
    pos = [next((i for i, k in enumerate(SECTION_ORDER) if k in h), None) for h in heads]
    pos = [p for p in pos if p is not None]
    if pos != sorted(pos):
        warns.append("절 순서가 다름 (주요 사건·사고 → 기타 사건·사고 → AI 보안 → 정책·제도 → 국방·방산보안 → 보안 동향 → 업계 동향 → 칼럼·기고 → 보안 행사)")
    # 절별 항목 점검
    sections = re.split(r"^##\s+", markdown, flags=re.M)[1:]
    no_src, bad_lines = 0, 0
    for sec in sections:
        title, _, body = sec.partition("\n")
        if "업계 동향" in title:   # 배치 기준: 보도 매체 수가 많은 순 (INSTRUCTIONS.md, 10/29 점검에서 3개 판이 어긋남)
            counts = [len(m.split(",")) for m in re.findall(r'^- \*\*\[[^\]]+\]\([^)]*"보도:\s*([^"]+)"', body, re.M)]
            if counts != sorted(counts, reverse=True):
                warns.append("업계 동향 배치 순서가 다름 (보도 매체 수가 많은 순 → 최신순)")
        if "주요 사건" in title:
            for item in re.split(r"^###\s+", body, flags=re.M)[1:]:
                head, _, rest = item.partition("\n")
                if not SRC_LINK.search(head):
                    no_src += 1
                lines = [l for l in rest.strip().splitlines() if l.strip()]
                if not 1 <= len(lines) <= 3:
                    bad_lines += 1
        elif any(k in title for k in ("기타 사건", "AI 보안", "정책", "국방", "보안 동향", "업계 동향")):   # 업계 동향도 2줄 (2026-10-27)
            for item in re.split(r"^- ", body, flags=re.M)[1:]:
                head, _, rest = item.partition("\n")
                if head.startswith("외 ") or "기사 검색에서 보기" in head:
                    continue
                if not SRC_LINK.search(head):
                    no_src += 1
                lines = [l for l in rest.strip().splitlines() if l.strip()]
                if not 1 <= len(lines) <= 3:
                    bad_lines += 1
    if no_src:
        warns.append(f"제목 링크에 보도 매체 문구(\"보도: …\")가 없는 항목 {no_src}건")
    if bad_lines:
        warns.append(f"2줄 요약 형식이 아닌 항목 {bad_lines}건")
    return warns


def check_files(out: dict, inp: dict | None, markdown: str) -> tuple[list, list, dict]:
    """파일만으로 하는 검사. (오류, 경고, 요약) 반환 — DB 없이 시험 가능."""
    errors, warns = [], []
    edition, date = out.get("edition"), out.get("date")
    labels = out.get("labels", [])
    events = out.get("events", [])

    bad = [l for l in labels if l.get("label") not in VALID or not isinstance(l.get("id"), int)]
    if bad:
        errors.append(f"잘못된 라벨 {len(bad)}건")
    ids = [l["id"] for l in labels if isinstance(l.get("id"), int)]
    if len(ids) != len(set(ids)):
        warns.append(f"같은 기사에 라벨 중복 {len(ids) - len(set(ids))}건")
    bad_slug = [e.get("slug") for e in events if not SLUG.match(str(e.get("slug", "")))]
    if bad_slug:
        errors.append(f"사건 slug 형식 오류: {', '.join(map(str, bad_slug[:3]))}")
    # 사건 제목·요약은 대시보드에 그대로 보이므로 한글로 써야 한다 (slug를 그대로 넣은 판이 있었음, 2026-10-28)
    def _korean(text, slug):
        text = str(text or "").strip()
        return bool(HANGUL.search(text)) and text != slug
    bad_text = [e.get("slug") for e in events
                if not (_korean(e.get("title"), e.get("slug")) and _korean(e.get("summary"), e.get("slug")))]
    if bad_text:
        errors.append(f"사건 제목·요약이 한글이 아님(비었거나 slug 그대로) {len(bad_text)}건: {', '.join(map(str, bad_text[:5]))}")

    known = {e.get("slug") for e in events}
    if inp:
        if inp.get("edition", edition) != edition or inp.get("date") != date:  # 구버전 입력은 edition 없음
            errors.append(f"입력({inp.get('date')}-{inp.get('edition')})과 출력({date}-{edition}) 판 불일치")
        cand = {a["id"] for a in inp.get("articles", [])}
        missing = cand - set(ids)
        extra = set(ids) - cand
        if missing:
            errors.append(f"라벨 누락 {len(missing)}건 (후보 {len(cand)}건 중)")
        if extra:
            warns.append(f"입력에 없는 기사 id {len(extra)}건")
        known |= {e.get("slug") for e in inp.get("recent_events", [])}
        st = out.get("stats", {})
        if st.get("candidates") not in (None, len(cand)):
            warns.append(f"통계 후보 수 {st.get('candidates')} ≠ 실제 {len(cand)}")
    else:
        warns.append("입력 파일을 찾지 못해 누락 검사 생략")

    # 확정 한 줄 요약: 보안·업계 동향 기사마다 60자 내외, 일반 글자만 (링크·마크다운·줄바꿈·지시문 금지)
    from .parsers import scan_injection
    kept = [l for l in labels if l.get("label") in ("security", "trend", "pr", "column")]
    needs = {a.get("id") for a in (inp or {}).get("articles", []) if a.get("needs_line", True)}
    no_line = [l for l in kept if l.get("id") in needs and not str(l.get("line") or "").strip()]
    bad_line = [l.get("id") for l in kept if l.get("line") and (
        len(str(l["line"])) > 80 or "\n" in str(l["line"]) or re.search(r"https?://|\]\(|[<>`#*]", str(l["line"]))
        or scan_injection(str(l["line"])))]
    if bad_line:
        errors.append(f"한 줄 요약 형식 오류 {len(bad_line)}건 (80자 초과·링크·마크다운·줄바꿈·지시문): id {bad_line[:5]}")
    if kept and len(no_line) > max(2, len(kept) // 10):
        warns.append(f"AI 요약도 브리핑 요약도 없는 보안·업계 기사 {len(no_line)}/{len(kept)}건")

    orphan = {l.get("event_slug") for l in labels if l.get("event_slug")} - known
    if orphan:
        errors.append(f"없는 사건에 연결된 라벨: {', '.join(sorted(orphan)[:3])}")
    if any(l.get("label") == "not_security" and l.get("event_slug") for l in labels):
        warns.append("'무관' 기사가 사건에 연결됨")

    in_urls = {a.get("url") for a in (inp or {}).get("articles", [])}
    in_urls |= {a.get("url") for e in (inp or {}).get("events", []) if isinstance(e, dict) for a in e.get("articles", [])}
    bad_links = check_links(markdown, in_urls)
    if bad_links:
        errors.append(f"허용되지 않은 링크 {len(bad_links)}건 (수집 매체 기사 주소만 허용): {', '.join(bad_links[:3])}")

    if not markdown.strip():
        errors.append("브리핑 본문(md) 없음")
    else:
        if not markdown.lstrip().startswith("# 정보보안 브리핑"):
            errors.append("본문 제목 형식 오류")
        if LABEL_NAME.get(edition, "?") not in markdown.split("\n", 1)[0]:
            warns.append("본문 제목에 판 표기 없음")
        warns += check_format(markdown, edition)
        if edition != "week" and "## 🔴 주요 사건" not in markdown and "새 보안 기사가 없습니다" not in markdown:
            warns.append("'주요 사건' 절 없음")

    # 보안 행사 목록 형식
    sev = out.get("security_events") or []
    if not isinstance(sev, list):
        errors.append("security_events 형식 오류 (목록이어야 함)")
    else:
        from .sync_briefing import allowed_event_url, clean_security_events
        bad = len(sev) - len(clean_security_events(sev))
        if bad:
            warns.append(f"보안 행사 {bad}건 형식 오류로 제외 (이름·날짜 YYYY-MM-DD 필요)")
        nolink = sum(1 for x in sev if isinstance(x, dict) and x.get("url") and not allowed_event_url(x["url"]))
        if nolink:
            warns.append(f"보안 행사 {nolink}건 링크가 수집 매체 기사 주소가 아니라 링크 없이 저장")

    summary = {"labels": len(labels), "events": len(events),
               "candidates": len(inp.get("articles", [])) if inp else None}
    return errors, warns, summary


def check_db(out: dict, markdown: str) -> list:
    errors = []
    date, edition = out["date"], out["edition"]
    rows = store.select("briefings", {"select": "markdown", "date": f"eq.{date}", "edition": f"eq.{edition}"})
    if not rows:
        errors.append("DB에 브리핑 없음")
    elif rows[0]["markdown"].strip() != markdown.strip():
        errors.append("DB 브리핑 본문이 파일과 다름")

    labels = {l["id"]: l["label"] for l in out.get("labels", []) if isinstance(l.get("id"), int)}
    if labels:
        got = {}
        ids = list(labels)
        for i in range(0, len(ids), 150):
            for r in store.select("articles", {"select": "id,label", "id": f"in.({','.join(map(str, ids[i:i + 150]))})"}):
                got[r["id"]] = r["label"]
        gone = [i for i in ids if i not in got]
        wrong = [i for i in ids if i in got and got[i] != labels[i]]
        if gone:
            errors.append(f"DB에 없는 기사 {len(gone)}건")
        if wrong:
            errors.append(f"DB 라벨 미반영 {len(wrong)}건")

    slugs = [e["slug"] for e in out.get("events", []) if e.get("slug")]
    if slugs:
        found = {r["slug"] for r in store.select("events", {"select": "slug", "slug": f"in.({','.join(slugs)})"})}
        if set(slugs) - found:
            errors.append(f"DB에 저장되지 않은 사건 {len(set(slugs) - found)}건")
    return errors


def check_dashboard(out: dict) -> list:
    url = f"{DASHBOARD}/b/{out['date']}-{out['edition']}"
    try:
        r = requests.get(url, timeout=30)
    except requests.RequestException as e:
        return [f"대시보드 접속 실패: {type(e).__name__}"]
    if r.status_code != 200:
        return [f"대시보드 응답 {r.status_code}"]
    if "브리핑이 없습니다" in r.text or "정보보안 브리핑 " + out["date"] not in r.text:
        return ["대시보드에 이번 판 브리핑이 표시되지 않음"]
    return []


def verify(out_path: Path) -> bool:
    out = json.loads(out_path.read_text(encoding="utf-8"))
    edition = out.get("edition") or (re.search(r"-(am|noon|pm|week)\.json$", out_path.name) or [None, "am"])[1]
    out["edition"] = edition
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(out.get("date", ""))) or edition not in LABEL_NAME:
        raise ValueError(f"{out_path}: 날짜·판 형식 오류")
    eid = f"{out['date']}-{edition}"
    in_path = Path("data/briefing-input") / f"{eid}.json"
    inp = json.loads(in_path.read_text(encoding="utf-8")) if in_path.exists() else None
    md_path = Path(f"briefings/{eid}.md")   # briefing_path 무시 — sync_briefing과 같은 고정 경로
    markdown = md_path.read_text(encoding="utf-8") if md_path.exists() else ""

    errors, warns, summary = check_files(out, inp, markdown)
    if store.enabled():
        errors += check_db(out, markdown)
        errors += check_dashboard(out)
    ok = not errors
    print(f"[{eid}] {'통과' if ok else '실패'} — 오류 {len(errors)}건, 경고 {len(warns)}건, {summary}")
    for p in errors:
        print(f"  ⛔ {p}")
    for p in warns:
        print(f"  ⚠️ {p}")
    if store.enabled():
        store.insert("briefing_checks", [{"date": out["date"], "edition": edition, "ok": ok,
                                          "problems": errors + [f"(경고) {w}" for w in warns],
                                          "summary": summary}])
    return ok


if __name__ == "__main__":
    results = [verify(Path(p)) for p in sys.argv[1:] if p.endswith(".json") and Path(p).exists()]
    sys.exit(0 if all(results) else 1)
