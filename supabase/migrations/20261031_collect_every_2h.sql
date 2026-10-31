-- 2026-10-31: 수집 간격 1시간 → 2시간 (사용자 결정·승인). 브리핑 직전 수집(05:17·11:17·17:17 KST)은 그대로.
-- 1) 정시 수집·실패 매체 재수집: KST 홀수 시(01·03·…·23시) 17분·27분 = UTC 짝수 시. 11개 매체 모두 같은 일정
--    (2시간이면 놓치던 매체는 수집기에서 보강: 디지털데일리 4쪽, 디지털투데이 분야별 RSS, 지디넷 뉴스 사이트맵)
-- 2) 감시 기준을 2시간 간격에 맞춤: '수집 멈춤' 경보 2시간 15분 → 2시간 45분, 자동 재실행 90분 → 2시간 30분
-- 함수는 운영 DB의 현재 정의에서 해당 부분만 바꿔 다시 만든다(바꿀 부분이 없으면 중단). 함수 권한은 그대로 유지됨.

select cron.schedule('collect-hourly', '17 0-22/2 * * *', $c$select public.dispatch_github_workflow('collect.yml')$c$);
select cron.schedule('collect-retry', '27 0-22/2 * * *', $c$select public.retry_failed_sources()$c$);

do $$
declare
  d text;
  o text;
begin
  d := pg_get_functiondef('public.auto_remediate()'::regprocedure);
  o := $o$if last_collect < now() - interval '90 minutes'$o$;
  if (length(d) - length(replace(d, o, ''))) / length(o) <> 1 then raise exception 'auto_remediate: 바꿀 부분이 1곳이 아님'; end if;
  execute replace(d, o, $n$if last_collect < now() - interval '150 minutes'$n$);

  d := pg_get_functiondef('public.system_alerts()'::regprocedure);
  o := $o$last_any < now() - interval '2 hours 15 minutes'$o$;
  if (length(d) - length(replace(d, o, ''))) / length(o) <> 1 then raise exception 'system_alerts: 바꿀 부분이 1곳이 아님'; end if;
  d := replace(d, o, $n$last_any < now() - interval '2 hours 45 minutes'$n$);
  o := $o$(매시 17분 실행, 실패 매체는 27분 재수집)$o$;
  if (length(d) - length(replace(d, o, ''))) / length(o) <> 1 then raise exception 'system_alerts: 안내 문구가 1곳이 아님'; end if;
  execute replace(d, o, $n$(홀수 시 17분 실행, 실패 매체는 홀수 시 27분 재수집)$n$);
end $$;
