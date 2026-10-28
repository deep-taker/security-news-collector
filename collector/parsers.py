"""피드·목록 페이지 파서와 공통 정규화 함수."""
import html
import re
import hashlib
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlsplit, urlunsplit, parse_qsl, urlencode

from bs4 import BeautifulSoup

KST = timezone(timedelta(hours=9))
SUMMARY_LIMIT = 300  # 저장 요약 최대 글자 수 (용량 분석 기준)

# 추적용 파라미터만 지우고 나머지(기사 번호 등)는 모두 유지한다
_DROP_PARAMS = {"fbclid", "gclid", "ref", "rss", "from", "fr", "share", "sns", "feed"}


def canonical_url(url: str) -> str:
    url = url.strip()
    p = urlsplit(url)
    netloc = p.netloc.lower()
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
         if not k.lower().startswith("utm_") and k.lower() not in _DROP_PARAMS]
    return urlunsplit(("https", netloc, p.path or "/", urlencode(q), ""))


def url_hash(url: str) -> str:
    return hashlib.sha1(canonical_url(url).encode("utf-8")).hexdigest()


_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def clean_text(s: str | None, limit: int | None = None) -> str:
    if not s:
        return ""
    s = html.unescape(html.unescape(s))  # 이중 이스케이프 대응 (&amp;#39; 등)
    s = _TAG.sub(" ", s)
    s = _WS.sub(" ", s).strip()
    if limit and len(s) > limit:
        s = s[:limit].rstrip() + "…"
    return s


def parse_date(value: str | None):
    """여러 날짜 형식을 KST 기준 aware datetime으로 바꾼다.

    시간대 표시가 없는 값("2026-10-24 10:29:10", "2026-10-24")은 국내 매체 관행상 KST로 본다.
    """
    if not value:
        return None
    v = value.strip()
    try:
        d = parsedate_to_datetime(v)  # RFC 822
        if d is not None:
            return (d if d.tzinfo else d.replace(tzinfo=KST)).astimezone(KST)
    except (TypeError, ValueError, IndexError):
        pass
    v2 = v.replace("T", " ").replace("Z", "+00:00")
    for fmt in ("%Y-%m-%d %H:%M:%S%z", "%Y-%m-%d %H:%M%z", "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M", "%Y.%m.%d %H:%M:%S", "%Y.%m.%d %H:%M", "%Y-%m-%d", "%Y.%m.%d"):
        try:
            d = datetime.strptime(v2, fmt)
            return (d if d.tzinfo else d.replace(tzinfo=KST)).astimezone(KST)
        except ValueError:
            continue
    try:
        d = datetime.fromisoformat(v2)
        return (d if d.tzinfo else d.replace(tzinfo=KST)).astimezone(KST)
    except ValueError:
        return None


def _local(tag) -> str:
    if not isinstance(tag, str):      # lxml 주석·처리 명령 노드
        return ""
    return tag.rsplit("}", 1)[-1].lower()


def _child_text(el, *names):
    for c in el:
        if _local(c.tag) in names:
            if _local(c.tag) == "link" and c.get("href"):
                return c.get("href")
            if c.text and c.text.strip():
                return c.text
    return None


_XML_BAD_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]")


class FeedItems(list):
    """parse_feed 결과. recovered=True면 형식 오류가 있어 복구 모드로 읽은 것 (일부 기사가 빠졌을 수 있음)."""
    recovered = False


def parse_feed(raw: bytes):
    """RSS 2.0 / Atom 공통 파서. 형식이 표준과 조금 달라도 읽도록 관대하게 처리."""
    text = raw.decode("utf-8", errors="replace").lstrip("\ufeff").lstrip()
    text = _XML_BAD_CHARS.sub("", text)          # XML에서 허용되지 않는 제어 문자 제거
    recovered = False
    try:
        root = ET.fromstring(text.encode("utf-8"))
    except ET.ParseError:
        # 매체 RSS에 이스케이프 안 된 & 같은 오류가 한 군데만 있어도 전체가 실패하므로, 복구 모드로 다시 읽는다
        from lxml import etree as LET
        root = LET.fromstring(text.encode("utf-8"), LET.XMLParser(recover=True, resolve_entities=False, no_network=True))
        if root is None:
            raise
        recovered = True
    items = [e for e in root.iter() if _local(e.tag) in ("item", "entry")]
    out = FeedItems()
    out.recovered = recovered
    for it in items:
        link = _child_text(it, "link") or _child_text(it, "guid", "id")
        title = clean_text(_child_text(it, "title"))
        if not link or not title:
            continue
        cats = [clean_text(c.text) for c in it if _local(c.tag) == "category" and c.text]
        out.append({
            "url": link.strip(),
            "title": title,
            "summary_raw": _child_text(it, "description", "summary", "content", "encoded") or "",
            "published_at": parse_date(_child_text(it, "pubdate", "published", "updated", "date")),
            "published_approx": False,
            "categories": [c for c in cats if c],
        })
    return out


_ETNEWS_ID = re.compile(r"(?:etnews\.com)?/(\d{14})(?:[/?#]|$)")
_DATE_IN_TEXT = re.compile(r"(\d{4})[-.](\d{2})[-.](\d{2})\.?\s+(\d{2}):(\d{2})")


def _list_summary(a, classes=("body", "summary", "lead", "desc")) -> str:
    """목록 페이지에서 제목 링크 가까이(같은 기사 항목 안)의 요약 문단을 찾는다. 없으면 ""."""
    node = a
    for _ in range(4):
        node = node.parent
        if node is None:
            return ""
        el = node.find(class_=lambda c: c and any(k in (c if isinstance(c, list) else c.split()) for k in classes))
        if el is not None and el is not a and a not in el.parents:
            t = clean_text(el.get_text(" "))
            if len(t) >= 20:
                return t
        if node.name == "li":       # 기사 항목 경계를 넘지 않음
            return ""
    return ""


def parse_etnews(raw: bytes, base_url: str):
    soup = BeautifulSoup(raw, "lxml")
    seen, out = set(), []
    for a in soup.find_all("a", href=True):
        m = _ETNEWS_ID.search(a["href"])
        if not m:
            continue
        title = clean_text(a.get_text(" "))
        if len(title) < 8:  # 이미지·숫자 링크 제외
            continue
        aid = m.group(1)
        if aid in seen:
            continue
        seen.add(aid)
        pub, approx = None, False
        node = a
        for _ in range(4):  # 가까운 상위 요소에서 표시 시각 찾기
            node = node.parent
            if node is None:
                break
            dm = _DATE_IN_TEXT.search(node.get_text(" "))
            if dm:
                y, mo, d, h, mi = map(int, dm.groups())
                pub = datetime(y, mo, d, h, mi, tzinfo=KST)
                break
        if pub is None:  # 기사 번호 앞 8자리(날짜)로 대체
            pub = datetime.strptime(aid[:8], "%Y%m%d").replace(tzinfo=KST)
            approx = True
        out.append({
            "url": urljoin(base_url, f"/{aid}"),
            "title": title,
            "summary_raw": _list_summary(a),
            "published_at": pub,
            "published_approx": approx,
            "categories": ["보안"],
        })
    return out


_DDAILY_ID = re.compile(r"/page/view/(\d{19})")


def parse_ddaily(raw: bytes, base_url: str):
    soup = BeautifulSoup(raw, "lxml")
    seen, out = set(), []
    for a in soup.find_all("a", href=True):
        m = _DDAILY_ID.search(a["href"])
        if not m:
            continue
        title = clean_text(a.get_text(" "))
        if len(title) < 8:
            continue
        aid = m.group(1)
        if aid in seen:
            continue
        seen.add(aid)
        try:  # 기사 번호 앞 14자리 = 게시 시각(YYYYMMDDHHMMSS)
            pub = datetime.strptime(aid[:14], "%Y%m%d%H%M%S").replace(tzinfo=KST)
            approx = False
        except ValueError:
            pub, approx = None, True
        out.append({
            "url": urljoin(base_url, f"/page/view/{aid}"),
            "title": title,
            "summary_raw": _list_summary(a),
            "published_at": pub,
            "published_approx": approx,
            "categories": [],
        })
    return out


PARSERS = {
    "rss": lambda raw, url: parse_feed(raw),
    "html_etnews": parse_etnews,
    "html_ddaily": parse_ddaily,
}

# 수집 텍스트에 AI를 겨냥한 지시문이 숨어 있는지 점검 (탐지 시 원문 영구 보관)
_INJECTION = [re.compile(p, re.IGNORECASE) for p in [
    r"ignore (all |any )?(previous|prior|above) (instructions|prompts)",
    r"disregard (the |all )?(previous|prior|above)",
    r"(system|developer) prompt",
    r"you are (now )?(an? )?(ai|assistant|language model|chatgpt|claude)",
    r"as an ai (model|assistant)",
    r"(do not|don't) (tell|inform) the user",
    r"(AI|인공지능|챗봇|어시스턴트)(에게|는|은)\s*(다음|아래|이)\s*(지시|명령|규칙)",
    r"(이전|앞의|위의)\s*(지시|명령)(을|를)?\s*(무시|따르지)",
    r"요약(할 때|시)\s*(반드시|다음)",
    r"<\s*/?\s*(system|instructions?|prompt)\s*>",
]]


def scan_injection(text: str):
    return [p.pattern for p in _INJECTION if p.search(text)]
