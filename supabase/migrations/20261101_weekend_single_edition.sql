-- 2026-11-01: 주말(토·일)은 06시판만 (사용자 결정·승인). 2026-11-07(토)부터.
-- 1) 12시판·18시판 브리핑 준비 신호를 평일(월~금)에만 — UTC 02:35·08:35는 KST와 같은 날이라 요일 그대로
-- 2) 주말에는 12시판·18시판 '누락' 경보(system_alerts)와 자동 재작성(auto_remediate)을 하지 않음
-- 함수는 운영 DB의 현재 정의에서 해당 부분만 바꿔 다시 만든다(바꿀 부분이 없으면 중단). 함수 권한은 그대로 유지됨.

select cron.schedule('prepare-noon', '35 2 * * 1-5', $c$select public.dispatch_github_workflow('daily.yml')$c$);
select cron.schedule('prepare-pm', '35 8 * * 1-5', $c$select public.dispatch_github_workflow('daily.yml')$c$);

do $$
declare
  d text;
  o text;
begin
  d := pg_get_functiondef('public.auto_remediate()'::regprocedure);
  o := $o$continue when e = 'noon' and today < date '2026-10-27';$o$;
  if (length(d) - length(replace(d, o, ''))) / length(o) <> 1 then raise exception 'auto_remediate: 바꿀 부분이 1곳이 아님'; end if;
  execute replace(d, o, o || $n$
    continue when e in ('noon', 'pm') and today >= date '2026-11-07' and extract(isodow from today) in (6, 7);   -- 주말은 06시판만$n$);

  d := pg_get_functiondef('public.system_alerts()'::regprocedure);
  o := $o$continue when e = 'noon' and d < date '2026-10-27';$o$;
  if (length(d) - length(replace(d, o, ''))) / length(o) <> 1 then raise exception 'system_alerts: 바꿀 부분이 1곳이 아님'; end if;
  execute replace(d, o, o || $n$
      continue when e in ('noon', 'pm') and d >= date '2026-11-07' and extract(isodow from d) in (6, 7);   -- 주말은 06시판만$n$);
end $$;
