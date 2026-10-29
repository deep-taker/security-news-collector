"""1차 필터용 키워드.

넓게 잡아 누락을 줄이고, 최종 판단은 매일 아침 Claude가 한다.
"""
import re

# 일반 정보보안
SECURITY_KO = [
    "보안", "해킹", "해커", "유출", "침해", "취약점", "랜섬웨어", "악성코드", "멀웨어",
    "피싱", "스미싱", "보이스피싱", "디도스", "DDoS", "개인정보", "정보보호", "사이버",
    "백도어", "제로데이", "보안 패치", "긴급 패치", "보안 업데이트", "인증 우회", "다중인증",
    "암호화", "스파이웨어",
    "봇넷", "공급망 공격", "크리덴셜", "계정 탈취", "도용", "위변조", "포렌식",
    "망분리", "제로트러스트", "ISMS", "CISO", "KISA", "인터넷진흥원",   # CPO 제외: 대부분 '최고제품책임자' (10/29 점검 3/3 오탐)
    "국정원", "국가정보원", "방첩", "국가사이버안보센터", "개인정보보호위원회", "개인정보위",
    "북한 해킹", "라자루스", "김수키", "APT", "침입", "무단 접근", "비인가 접근",
    "방산보안", "방위산업", "방사청", "방위사업청", "방산업체", "군사기밀", "국방보안",   # '방산' 단독 제외: 실적·수출 기사와 '지방산' (10/29 점검 16건 중 15건 오탐)
    "기술유출", "산업기밀", "산업보안", "기밀 유출",
    "경보", "보안관제", "모의해킹", "버그바운티", "CVE",
    # 10/29 점검의 놓친 기사 표본 근거 (인증 방식 전환·양자 보안)
    "패스키", "양자암호", "양자내성", "PQC",
    # 국방·군사보안 (2026-10-27 사용자 결정) — '해킹·유출·보안' 같은 일반 단어 없이 쓰이는 군사보안 고유 용어
    "군사보안", "군 보안", "군보안", "방첩사", "국군방첩사령부", "안보지원사", "기무사", "사이버작전사령부", "사이버사령부",
    "사이버작전", "사이버전", "전자전", "GPS 교란", "GPS교란", "전파 교란", "전파교란", "재밍", "정찰총국", "간첩",
    "비밀취급", "비밀 취급", "보안측정", "국방망", "국방정보본부", "군사정보", "기밀 누설", "군 기밀",
]
# AI 보안 (최근 이슈로 함께 수집 — 사용자 결정 2026-10-26)
AI_SECURITY_KO = [
    "AI 보안", "AI보안", "프롬프트 인젝션", "탈옥", "딥페이크", "AI 안전", "AI안전",
    "정렬 실패", "모델 탈취", "AI 해킹", "AI 에이전트 보안", "레드팀", "샌드박스 탈출",
    "데이터 오염", "적대적 공격", "AI 악용",
]
SECURITY_EN = [
    "security", "hack", "breach", "vulnerability", "exploit", "ransomware", "malware",
    "phishing", "backdoor", "zero-day", "botnet", "leak", "jailbreak",
    "prompt injection", "deepfake", "red team",
]

# 짧아서 오탐이 잦은 영어 약어는 단어 경계로만 매칭
_WORD_BOUNDARY = {"APT", "CVE", "CISO", "ISMS", "KISA", "DDoS", "PQC"}


def _compile(words):
    pats = []
    for w in words:
        esc = re.escape(w)
        if w in _WORD_BOUNDARY:
            pats.append((w, re.compile(rf"(?<![A-Za-z]){esc}(?![A-Za-z])")))
        else:
            pats.append((w, re.compile(esc, re.IGNORECASE)))
    return pats


_SEC = _compile(SECURITY_KO + SECURITY_EN)
_AI = _compile(AI_SECURITY_KO)

# 보안 키워드처럼 보이지만 보안과 무관한 표현 (오탐 제거)
_FALSE_POSITIVE = [
    re.compile(p) for p in [
        r"인증샷", r"인증서 수여", r"품질 ?인증", r"KC ?인증", r"할랄 ?인증",
        r"유출 ?우려 없", r"패치워크", r"사이버 ?대학", r"사이버트럭",
        r"안보(?!센터)", r"경보음", r"폭염 ?경보", r"한파 ?경보", r"호우 ?경보",
    ]
]


# 보안 키워드 판정에서만 지우는 표현 (행사 판정에는 그대로 둔다 — 예: 해커톤은 행사 단어)
# 10/29 점검: '암호화' 22건 중 16건이 암호화폐 기사, '해커'가 해커톤에, '사이버'가 테슬라 사이버캡에 걸림
_SEC_FALSE_POSITIVE = [re.compile(p) for p in [r"암호 ?화폐", r"암호화 ?자산", r"해커톤", r"사이버캡"]]


def match(text: str):
    """(보안 키워드 목록, AI 보안 키워드 목록)을 돌려준다."""
    cleaned = text
    for fp in _FALSE_POSITIVE + _SEC_FALSE_POSITIVE:
        cleaned = fp.sub(" ", cleaned)
    sec = sorted({w for w, p in _SEC if p.search(cleaned)})
    ai = sorted({w for w, p in _AI if p.search(cleaned)})
    return sec, ai


# 보안 행사 (2026-10-27 사용자 결정): '행사 단어' + '보안 관련 단어'가 함께 나오면 후보.
# 보안 키워드(보안·해킹 등)가 이미 있으면 그것으로 후보가 되므로, 여기서는 보안 키워드에 없는 관련 단어(국방·군 등)를 보완한다.
EVENT_WORDS = ["컨퍼런스", "콘퍼런스", "세미나", "포럼", "워크숍", "워크샵", "서밋", "심포지엄", "학술대회", "전시회", "박람회",
               "엑스포", "해커톤", "CTF", "경진대회", "설명회", "웨비나", "행사", "개최", "개막"]
EVENT_CONTEXT = ["국방", "국군", "합참", "합동참모", "육군", "해군", "공군", "해병대", "사이버작전", "군 ", "AI 안전", "AI안전",
                 "프라이버시", "데이터 보호", "디지털 포렌식", "보안", "정보보호", "사이버", "해킹", "개인정보", "방산", "방위"]
_EV = _compile(EVENT_WORDS)
_EV_CTX = _compile(EVENT_CONTEXT)


def event_match(text: str):
    """보안 관련 행사 기사면 걸린 행사 단어 목록, 아니면 []."""
    cleaned = text
    for fp in _FALSE_POSITIVE:
        cleaned = fp.sub(" ", cleaned)
    ev = sorted({w for w, p in _EV if p.search(cleaned)})
    if not ev or not any(p.search(cleaned) for _, p in _EV_CTX):
        return []
    return ev
