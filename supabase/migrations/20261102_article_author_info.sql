-- 칼럼·기고 필자 정보 (사용자 결정·승인 2026-11-02, ①안: 수집 시 기사 페이지의 필자 줄 → AI가 소속·직책·성명으로 정리)
-- {"org": 소속, "position": 직책, "name": 성명} / {} = 찾았으나 알 수 없음 / null = 아직 찾지 않음
alter table public.articles add column if not exists author_info jsonb;
comment on column public.articles.author_info is '칼럼·기고 필자 {org, position, name} — collector/authors.py, {}=알 수 없음, null=미확인';
-- 대시보드(읽기 전용 공개 키)는 열 단위로만 읽는다 → 이 열 읽기 허용
grant select (author_info) on public.articles to anon;
