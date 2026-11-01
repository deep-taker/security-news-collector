-- 2026-11-02: '24시간 동안 새 기사 0건' 경보 기준을 매체별로 (사용자 결정).
-- 기사가 적은 매체(IT동아: 평일 하루 약 7건, 주말 거의 없음)는 주말마다 경보가 떠서 48시간으로 늘림.
-- 1) sources.no_new_alert_hours 추가 (기본 24, 기존 행은 24) → IT동아 48
-- 2) system_alerts: 매체별 시간으로 새 기사 수를 세고, 경보 제목에도 그 시간을 씀
-- 함수는 운영 DB의 현재 정의에서 해당 부분만 바꿔 다시 만든다(바꿀 부분이 없으면 중단). 함수 권한은 그대로 유지됨.

alter table public.sources add column if not exists no_new_alert_hours integer not null default 24;
update public.sources set no_new_alert_hours = 48 where id = 'itdonga';

do $$
declare
  d text;
  o text;
  hrs text := $h$(select s.no_new_alert_hours from public.sources s where s.id = r.id)$h$;
begin
  d := pg_get_functiondef('public.system_alerts()'::regprocedure);
  o := $o$if r.runs_24h >= 3 and r.new_24h = 0 then$o$;
  if (length(d) - length(replace(d, o, ''))) / length(o) <> 1 then raise exception 'system_alerts: 조건이 1곳이 아님'; end if;
  d := replace(d, o, 'if r.runs_24h >= 3 and (select coalesce(sum(c.new_count), 0) from public.collection_runs c where c.source_id = r.id and c.run_at > now() - make_interval(hours => '
                     || hrs || ')) = 0 then');
  o := $o$'title', r.name || ' 24시간 동안 새 기사 0건'$o$;
  if (length(d) - length(replace(d, o, ''))) / length(o) <> 1 then raise exception 'system_alerts: 제목이 1곳이 아님'; end if;
  execute replace(d, o, $n$'title', r.name || ' ' || $n$ || hrs || $n$ || '시간 동안 새 기사 0건'$n$);
end $$;
