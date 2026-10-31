-- 2026-10-31: 새 분류 '보안 동향'(trend)·'칼럼·기고'(column) 추가 (사용자 결정·승인)
-- 1) articles.label 허용값에 trend·column 추가 (기존 행은 바뀌지 않음)
-- 2) 공개 읽기 정책: trend·column 기사도 대시보드(읽기 전용 공개 키)에서 보이게
-- 3) apply_briefing: trend·column 기사도 브리핑의 한 줄 요약(line)을 저장
-- 4) system_alerts: 한 줄 요약 채움률 계산에 trend·column 포함
-- 3·4는 운영 DB의 현재 함수 정의에서 해당 부분만 바꿔 다시 만든다(바꿀 부분이 없으면 중단). 함수 권한은 그대로 유지됨.

alter table public.articles drop constraint articles_label_check;
alter table public.articles add constraint articles_label_check
  check (label in ('security', 'trend', 'pr', 'column', 'not_security'));

drop policy if exists public_read on public.articles;
create policy public_read on public.articles as PERMISSIVE for SELECT to anon
  using (((label = ANY (ARRAY['security'::text, 'trend'::text, 'pr'::text, 'column'::text])) OR ((label IS NULL) AND candidate)));

do $$
declare
  d text;
  n int;
begin
  d := pg_get_functiondef('public.apply_briefing(date, text, jsonb, jsonb, jsonb, text)'::regprocedure);
  n := (length(d) - length(replace(d, $o$l->>'label' in ('security', 'pr')$o$, ''))) / length($o$l->>'label' in ('security', 'pr')$o$);
  if n <> 1 then raise exception 'apply_briefing: 바꿀 부분 % 곳 (1곳이어야 함)', n; end if;
  execute replace(d, $o$l->>'label' in ('security', 'pr')$o$, $n$l->>'label' in ('security', 'trend', 'pr', 'column')$n$);

  d := pg_get_functiondef('public.system_alerts()'::regprocedure);
  n := (length(d) - length(replace(d, $o$a.label in ('security', 'pr')$o$, ''))) / length($o$a.label in ('security', 'pr')$o$);
  if n <> 3 then raise exception 'system_alerts: 바꿀 부분 % 곳 (3곳이어야 함)', n; end if;
  execute replace(d, $o$a.label in ('security', 'pr')$o$, $n$a.label in ('security', 'trend', 'pr', 'column')$n$);
end $$;
