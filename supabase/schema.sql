-- 보안 기사 수집기 DB: 표 정의 (운영 DB와 같은 열 순서)
-- 재구축 순서: ① 이 파일 → ② supabase/generated/definitions.sql (함수·색인·권한·정책·예약·보관함, 운영 DB에서 자동 생성)
--              → ③ Vault 토큰 등록 → ④ 백업 복구.  자세한 절차는 README '재구축 절차'
-- 표를 바꿀 때는 이 파일도 함께 고칠 것 (월간 복구 시험이 운영 DB와 열 구성을 대조해 차이를 알림)

create schema if not exists extensions;
create extension if not exists pg_trgm with schema extensions;

-- 매체
create table if not exists sources (
  id text primary key,
  name text not null,
  grp text not null default 'domestic_press',
  kind text not null,
  url text not null,
  active boolean not null default true,
  fail_alert_after integer not null default 3      -- 연속 실패 몇 회부터 '오류' 알림인지
);

-- 사건 (중복 기사를 묶는 단위)
create table if not exists events (
  id bigserial primary key,
  slug text unique not null,
  title text not null,
  category text,
  summary text,
  cves text[] default '{}',
  first_seen date not null default current_date,
  last_seen date not null default current_date,
  created_at timestamptz not null default now()
);

-- 기사
create table if not exists articles (
  id bigserial primary key,
  url_hash text unique not null,
  url text not null,
  source_id text not null references sources(id),
  title text not null,
  summary text,
  published_at timestamptz,
  published_approx boolean not null default false,
  collected_at timestamptz not null default now(),
  categories text[] default '{}',
  keywords text[] default '{}',
  candidate boolean not null default false,   -- 1차 필터(키워드·보안 매체) 통과
  ai_related boolean not null default false,
  label text check (label in ('security', 'trend', 'pr', 'column', 'not_security')), -- Claude 최종 분류 (trend·column 2026-10-31)
  event_id bigint references events(id) on delete set null,
  labeled_at timestamptz,
  summary_line text,                          -- 한 줄 요약 (제목 아래 표시)
  summary_source text check (summary_source in ('rss', 'ai', 'claude', 'none'))  -- ai=매시간 AI 요약, claude=브리핑 보완, none=포기, rss=옛 발췌(미사용)
);

-- 브리핑 (판: am=06시판, noon=12시판, pm=18시판, week=주간 요약(월요일))
create table if not exists briefings (
  date date not null,
  markdown text not null,
  stats jsonb default '{}',
  created_at timestamptz not null default now(),
  edition text not null default 'am' check (edition in ('am', 'noon', 'pm', 'week')),
  primary key (date, edition)
);

-- 보안 행사 일정 (국내, 브리핑 작업이 기사에서 추출) — 대시보드 '행사 일정'·브리핑 행사 탭
create table if not exists security_events (
  id bigserial primary key,
  name text not null check (length(name) between 2 and 120),
  name_key text generated always as (lower(regexp_replace(name, '[\s·\-–—''"“”‘’]+', '', 'g'))) stored,
  start_date date not null,
  end_date date,
  place text check (length(place) <= 120),
  organizer text check (length(organizer) <= 120),
  url text,
  major boolean not null default false,
  note text check (length(note) <= 200),
  article_ids bigint[] not null default '{}',
  first_seen date not null default current_date,
  updated_at timestamptz not null default now(),
  unique (name_key, start_date)
);

-- 수집 실행 기록 (90일 보관)
create table if not exists collection_runs (
  id bigserial primary key,
  run_at timestamptz not null default now(),
  source_id text references sources(id),
  ok boolean not null,
  fetched integer not null default 0,
  new_count integer,
  error text,
  flags text[] default '{}'          -- gap:누락 가능 구간, inject:지시문 의심, pageN_failed
);

-- 브리핑 반영 검증 결과 (30일 보관)
create table if not exists briefing_checks (
  id bigserial primary key,
  checked_at timestamptz not null default now(),
  date date not null,
  edition text not null check (edition in ('am', 'noon', 'pm', 'week')),
  ok boolean not null,
  problems jsonb not null default '[]',
  summary jsonb not null default '{}'
);

-- 백업·복구 시험 기록 (90일 보관)
create table if not exists backup_runs (
  id bigserial primary key,
  run_at timestamptz not null default now(),
  target text not null check (target in ('storage', 'github', 'restore_test', 'schema_check')),
  kind text not null,              -- daily / weekly / monthly / restore_test
  ok boolean not null,
  files integer not null default 0,
  bytes bigint not null default 0,
  rows_count integer not null default 0,
  used_bytes bigint,               -- 실행 후 전체 사용량
  limit_bytes bigint,              -- 90% 상한
  detail text
);

-- 자동 조치 기록 (90일 보관) — auto_remediate()
create table if not exists remediation_runs (
  id bigserial primary key,
  run_at timestamptz not null default now(),
  kind text not null,         -- collect_restart / briefing_refire / sync_retry / briefing_fix / backup_retry / notify / repair_request
  target text not null default '',
  ok boolean not null,
  request_id bigint,          -- pg_net 요청 번호
  detail text
);

-- 지속 중인 오류 (알림 중복 방지)
create table if not exists alert_state (
  key text primary key,
  first_seen timestamptz not null default now(),
  last_seen timestamptz not null default now(),
  last_notified timestamptz,
  title text
);

-- main 코드 자동 시험(CI) 결과 — 실패하면 대시보드 오류
create table if not exists ci_runs (
  id bigserial primary key,
  run_at timestamptz not null default now(),
  sha text not null,
  ok boolean not null,
  detail text,
  url text
);

-- 정기 작업 기한 (비밀값 교체 등): 14일 전 주의, 지나면 오류. 교체 후 due를 1년 뒤로 갱신
create table if not exists ops_reminders (
  key text primary key,
  title text not null,
  due date not null,
  note text
);
insert into ops_reminders (key, title, due, note) values
  ('github_dispatch_token', 'GitHub 실행 신호 토큰(Vault) 교체', date '2027-10-26', 'README 비밀값 교체 절차'),
  ('supabase_service_key', 'Supabase 비밀 키(GitHub Secrets) 교체', date '2027-10-26', 'README 비밀값 교체 절차')
on conflict (key) do nothing;

-- 매체 초기 데이터 (1단계: 국내 언론사)
insert into sources (id, name, grp, kind, url, fail_alert_after) values
  ('boannews', '보안뉴스', 'domestic_press', 'rss', 'https://www.boannews.com/rss/allArticle.xml', 3),
  ('dailysecu', '데일리시큐', 'domestic_press', 'rss', 'https://www.dailysecu.com/rss/allArticle.xml', 3),
  ('etnews_sec', '전자신문', 'domestic_press', 'html_etnews', 'https://www.etnews.com/news/section.html?id1=04&id2=045', 3),
  ('dt_ict', '디지털타임스', 'domestic_press', 'rss', 'https://www.dt.co.kr/rss/google/ict', 3),
  ('digitaltoday', '디지털투데이', 'domestic_press', 'rss', 'https://www.digitaltoday.co.kr/rss/allArticle.xml', 2),
  ('aitimes', 'AI타임스', 'domestic_press', 'rss', 'https://www.aitimes.com/rss/allArticle.xml', 3),
  ('bloter', '블로터', 'domestic_press', 'rss', 'https://www.bloter.net/rss/allArticle.xml', 3),
  ('zdnet', '지디넷코리아', 'domestic_press', 'rss', 'https://feeds.feedburner.com/zdkorea', 3),
  ('ddaily', '디지털데일리', 'domestic_press', 'html_ddaily', 'https://www.ddaily.co.kr/news', 2)
on conflict (id) do nothing;
