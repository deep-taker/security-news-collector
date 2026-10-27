"""공개 저장소 개인정보·계정 식별자 검사 (2026-10-28 사용자 결정, CLAUDE.md 원칙 8).

저장소에 올라간 파일(git ls-files)에 개인 이메일·Claude 세션 ID·예약 작업 ID·세션 링크가 없어야 한다.
수집 자료(data/)·브리핑(briefings/)은 외부 기사라 검사하지 않고, DB에서 자동 생성되는 정의 파일도 제외한다.
"""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP = ("data/", "briefings/", "supabase/generated/", "dashboard/package-lock.json")
PATTERNS = {
    "개인 메일 주소": re.compile(r"[A-Za-z0-9._%+-]+@(?:gmail|naver|daum|hanmail|kakao|nate|outlook|hotmail|icloud)\.[a-z.]+", re.I),
    "Claude 세션 ID": re.compile(r"\b(?:session|cse)_01[A-Za-z0-9]{16,}"),
    "예약 작업 ID": re.compile(r"\btrig_01[A-Za-z0-9]{16,}"),
    "Claude 세션 링크": re.compile(r"claude\.ai/code/session_"),
}


def test_no_personal_info_in_tracked_files():
    files = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout.decode().split("\0")
    found = []
    for f in files:
        if not f or f.startswith(SKIP) or f == "tests/test_public_repo.py":
            continue
        try:
            text = (ROOT / f).read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        for name, pat in PATTERNS.items():
            for m in pat.finditer(text):
                found.append(f"{f}: {name}")
    assert not found, "공개 저장소에 개인정보·식별자: " + ", ".join(sorted(set(found)))


def test_no_private_words():
    """사용자가 GitHub Secrets PRIVATE_WORDS(쉼표 구분)에 넣은 개인 단어(옛 계정 이름·개인 도메인·기기 이름 등)가
    저장소 파일에 없어야 한다. 단어 목록 자체를 공개하지 않으려고 Secrets로만 받는다 — 없으면(로컬·외부 PR) 건너뜀.
    자동 생성 정의 파일(supabase/generated/)도 검사한다."""
    import os
    import pytest
    words = [w.strip() for w in os.environ.get("PRIVATE_WORDS", "").split(",") if len(w.strip()) >= 3]
    if not words:
        pytest.skip("PRIVATE_WORDS 없음")
    pats = [re.compile(r"(?<![0-9A-Za-z])" + re.escape(w) + r"(?![0-9A-Za-z])", re.I) for w in words]
    files = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout.decode().split("\0")
    found = set()
    for f in files:
        if not f or f.startswith(("data/", "briefings/", "dashboard/package-lock.json")):
            continue
        try:
            text = (ROOT / f).read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        for i, p in enumerate(pats):
            if p.search(text):
                found.add(f"{f}: 개인 단어 {i + 1}번")      # 단어 자체는 출력하지 않음 (작업 기록 공개)
    assert not found, "공개 저장소에 개인 단어: " + ", ".join(sorted(found))


def test_patterns_catch_examples():
    assert PATTERNS["개인 메일 주소"].search("연락처 someone@gmail.com")
    assert not PATTERNS["개인 메일 주소"].search("collector-bot@users.noreply.github.com")
    assert PATTERNS["예약 작업 ID"].search("trig_01" + "A" * 20)
    assert PATTERNS["Claude 세션 링크"].search("https://claude.ai/code/session_x")
