"""Claude가 저장소에 올린 브리핑 결과를 Supabase에 반영.

python -m collector.sync_briefing data/briefing-output/2026-10-27-am.json [...]

파일 형식은 briefing/OUTPUT_FORMAT.md 참고 (date, edition, briefing_path, events, labels, stats).
"""
import json
import re
import sys
from pathlib import Path

from . import store

VALID = {"security", "trend", "pr", "column", "not_security"}


def sync(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    edition = data.get("edition")
    if edition not in ("am", "noon", "pm", "week"):  # 파일 이름에서 판별 (구버전 파일은 오전판으로 간주)
        m = re.search(r"-(am|noon|pm|week)\.json$", path.name)
        edition = m.group(1) if m else "am"
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(data.get("date", ""))):
        raise ValueError(f"{path}: 날짜 형식 오류")
    eid = f'{data["date"]}-{edition}'
    md_path = Path(f"briefings/{eid}.md")   # 출력 JSON의 briefing_path는 무시 (임의 파일을 읽어 공개 브리핑에 싣는 것 방지)
    markdown = md_path.read_text(encoding="utf-8") if md_path.exists() else ""
    if markdown and not markdown.lstrip().startswith("# 정보보안 브리핑"):
        raise ValueError(f"{md_path}: 브리핑 제목 형식이 아니라 반영하지 않음")
    labels = [l for l in data.get("labels", []) if l.get("label") in VALID and isinstance(l.get("id"), int)]
    res = store.rpc("apply_briefing", {
        "p_date": data["date"],
        "p_edition": edition,
        "p_markdown": markdown,
        "p_events": data.get("events", []),
        "p_labels": labels,
        "p_stats": data.get("stats", {}),
    })
    print(f"{path}: {res}")
    evs = clean_security_events(data.get("security_events"))
    if evs:
        print(f"{path}: 보안 행사 {store.rpc('apply_security_events', {'p_events': evs})}")


def allowed_event_url(url) -> bool:
    """행사 링크는 수집 매체 기사 주소만 (외부 누리집 링크는 저장하지 않음)."""
    from .verify_briefing import ARTICLE_DOMAINS
    from urllib.parse import urlsplit
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        return False
    host = (urlsplit(url).hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in ARTICLE_DOMAINS)


def clean_security_events(items) -> list:
    """브리핑 출력의 보안 행사 목록 정리: 형식이 맞고 링크가 수집 매체 기사 주소인 것만 (나머지는 버림)."""
    out = []
    for e in items or []:
        if not isinstance(e, dict) or not isinstance(e.get("name"), str):
            continue
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(e.get("start_date", ""))):
            continue
        if e.get("end_date") and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(e["end_date"])):
            continue
        url = e.get("url") if allowed_event_url(e.get("url")) else None
        out.append({"name": e["name"].strip()[:120], "start_date": e["start_date"], "end_date": e.get("end_date") or None,
                    "place": (e.get("place") or None) and str(e["place"])[:120],
                    "organizer": (e.get("organizer") or None) and str(e["organizer"])[:120],
                    "url": url, "major": bool(e.get("major")), "note": (e.get("note") or None) and str(e["note"])[:200],
                    "article_ids": [i for i in e.get("article_ids", []) if isinstance(i, int)]})
    return out


def sync_all(paths) -> int:
    """파일마다 따로 반영 — 한 파일이 실패해도 나머지는 반영하고, 실패한 파일 수를 돌려준다."""
    failed = 0
    for p in paths:
        if not (p.endswith(".json") and Path(p).exists()):
            continue
        try:
            sync(Path(p))
        except Exception as e:  # noqa: BLE001 — 다음 파일 계속, 마지막에 실패로 종료
            failed += 1
            print(f"::error::{p}: 반영 실패 — {type(e).__name__}: {str(e)[:300]}")
    return failed


if __name__ == "__main__":
    if not store.enabled():
        print("Supabase 환경변수가 없어 건너뜁니다.")
        sys.exit(0)
    sys.exit(1 if sync_all(sys.argv[1:]) else 0)
