-- 2026-10-31: 수집 간격 1시간 → 2시간 (사용자 결정·승인). 브리핑 직전 수집(05:17·11:17·17:17 KST)은 그대로.
-- 1) 정시 수집·실패 매체 재수집: KST 홀수 시(01·03·…·23시) 17분·27분 = UTC 짝수 시
-- 2) 지디넷코리아만 매시간: RSS가 최근 30건뿐이라 2시간이면 기사를 놓침 → KST 짝수 시 17분에 지디넷만 추가 수집
-- 3) 감시 기준: 지디넷이 매시간 돌아 '가장 최근 수집 시각'만으로는 멈춤을 알 수 없으므로,
--    활성 매체의 절반 이상이 최근(경보 2시간 45분·자동 재실행 2시간 30분) 안에 수집되지 않았으면 이상으로 본다
-- 함수는 운영 DB의 현재 정의에서 해당 부분만 바꿔 다시 만든다(바꿀 부분이 없으면 중단). 함수 권한은 그대로 유지됨.

select cron.schedule('collect-hourly', '17 0-22/2 * * *', $c$select public.dispatch_github_workflow('collect.yml')$c$);
select cron.schedule('collect-retry', '27 0-22/2 * * *', $c$select public.retry_failed_sources()$c$);
select cron.schedule('collect-zdnet', '17 1-23/2 * * *', $c$select public.dispatch_github_workflow('collect.yml', '{"only": "zdnet"}'::jsonb)$c$);

do $$
declare
  d text;
  o text;
  r text;
  recent text := $q$(select count(distinct c.source_id) from public.collection_runs c join public.sources s on s.id = c.source_id and s.active where c.run_at > now() - interval '%s') * 2 < (select count(*) from public.sources s where s.active)$q$;
begin
  d := pg_get_functiondef('public.auto_remediate()'::regprocedure);
  o := $o$if last_collect < now() - interval '90 minutes'$o$;
  if (length(d) - length(replace(d, o, ''))) / length(o) <> 1 then raise exception 'auto_remediate: 바꿀 부분이 1곳이 아님'; end if;
  execute replace(d, o, 'if ' || format(recent, '150 minutes'));

  d := pg_get_functiondef('public.system_alerts()'::regprocedure);
  o := $o$if last_any is null or last_any < now() - interval '2 hours 15 minutes' then$o$;
  if (length(d) - length(replace(d, o, ''))) / length(o) <> 1 then raise exception 'system_alerts: 바꿀 부분이 1곳이 아님'; end if;
  r := 'if last_any is null or ' || format(recent, '2 hours 45 minutes') || ' then';
  d := replace(d, o, r);
  o := $o$(매시 17분 실행, 실패 매체는 27분 재수집)$o$;
  if (length(d) - length(replace(d, o, ''))) / length(o) <> 1 then raise exception 'system_alerts: 안내 문구가 1곳이 아님'; end if;
  execute replace(d, o, $n$(홀수 시 17분 실행·지디넷은 매시, 실패 매체는 홀수 시 27분 재수집)$n$);
end $$;
