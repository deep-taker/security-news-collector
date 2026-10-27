-- 2026-10-28: 새 공개 저장소 전환 때 DB 기록을 모두 지운 뒤 정리 (사용자 승인)
-- 1) 브리핑 누락 경보는 2026-10-28 판부터 검사 (지운 10/27 판이 '누락'으로 36시간 남지 않게)
-- 2) source_summary_low 안내 문구: 보관 저장소의 원문 표본 저장 작업 폐기에 맞춤 (ops/RUNBOOK.md)
-- 함수 본문은 supabase/generated/definitions.sql(2026-10-28 05:00 생성)에서 위 두 곳만 바꿈. 권한은 그대로 유지됨.

CREATE OR REPLACE FUNCTION public.system_alerts()
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
  kst timestamp := now() at time zone 'Asia/Seoul';
  alerts jsonb := '[]'::jsonb;
  srcs jsonb;
  bk jsonb;
  last_any timestamptz;
  r record;
  d date;
  e text;
  due timestamp;
  cov record;
  cov_all_ok boolean := true;
  ai jsonb;
  dbsize bigint := pg_database_size(current_database());
begin
  select coalesce(jsonb_agg(x order by x->>'name'), '[]'::jsonb) into srcs from (
    select jsonb_build_object(
      'id', s.id, 'name', s.name, 'fail_alert_after', s.fail_alert_after,
      'last_run_at', (select max(run_at) from public.collection_runs c where c.source_id = s.id),
      'last_ok_at', (select max(run_at) from public.collection_runs c where c.source_id = s.id and c.ok),
      'consecutive_fails', (select count(*) from public.collection_runs c where c.source_id = s.id and not c.ok
                              and not (coalesce(c.flags, '{}') && array['retry:403', 'retry:conn'])   -- 첫 시도 403·접속 실패는 새 서버 재시도 결과로 판단
                              and c.run_at > coalesce((select max(run_at) from public.collection_runs c2 where c2.source_id = s.id and c2.ok), '-infinity')),
      'runs_24h', (select count(*) from public.collection_runs c where c.source_id = s.id and c.run_at > now() - interval '24 hours'),
      'new_24h', (select coalesce(sum(new_count), 0) from public.collection_runs c where c.source_id = s.id and c.run_at > now() - interval '24 hours'),
      'last_error', (select left(error, 200) from public.collection_runs c where c.source_id = s.id and not c.ok order by run_at desc limit 1),
      'gap', (select f from public.collection_runs c, unnest(c.flags) f where c.source_id = s.id and f like 'gap:%'
                and c.run_at > now() - interval '24 hours' order by c.run_at desc limit 1)
    ) x
    from public.sources s where s.active
  ) t;

  select max(run_at) into last_any from public.collection_runs;
  if last_any is null or last_any < now() - interval '2 hours 15 minutes' then
    alerts := alerts || jsonb_build_object('level','error','code','collect_stalled', 'title','수집이 멈췄습니다',
      'detail', '마지막 수집: ' || coalesce(to_char(last_any at time zone 'Asia/Seoul','MM-DD HH24:MI'),'없음') || ' (매시 17분 실행, 실패 매체는 27분 재수집)');
  end if;

  select count(*) n, count(a.summary_line) filled into cov from public.articles a
   where (a.candidate or a.label in ('security', 'pr')) and coalesce(a.label, '') <> 'not_security'
     and a.collected_at between now() - interval '27 hours' and now() - interval '3 hours';
  cov_all_ok := not (cov.n >= 10 and cov.filled < cov.n * 0.5);
  if not cov_all_ok then
    alerts := alerts || jsonb_build_object('level','warn','code','ai_summary_low',
      'title', 'AI 한 줄 요약 채움률 ' || round(100.0 * cov.filled / cov.n) || '% (24시간 ' || cov.n || '건)',
      'detail', 'GitHub Secrets의 ANTHROPIC_API_KEY 등록·만료, API 사용 한도·결제 상태 확인 (수집 작업 로그의 AI 요약 결과 참고)');
  end if;

  for r in select * from jsonb_to_recordset(srcs) as x(id text, name text, fail_alert_after int, consecutive_fails int,
                                                        runs_24h int, new_24h int, last_error text, gap text) loop
    if r.consecutive_fails >= r.fail_alert_after then
      alerts := alerts || jsonb_build_object('level','error','code','source_failing','source_id',r.id,
        'title', r.name || ' 수집 ' || r.consecutive_fails || '회 연속 실패', 'detail', coalesce(r.last_error,''));
    elsif r.consecutive_fails >= 1 then
      alerts := alerts || jsonb_build_object('level','warn','code','source_failed','source_id',r.id,
        'title', r.name || ' 최근 수집 실패 (' || r.consecutive_fails || '회)', 'detail', coalesce(r.last_error,''));
    end if;
    if r.runs_24h >= 3 and r.new_24h = 0 then
      alerts := alerts || jsonb_build_object('level','warn','code','source_no_new','source_id',r.id,
        'title', r.name || ' 24시간 동안 새 기사 0건', 'detail', '사이트 구조 변경이나 RSS 중단 가능성');
    end if;
    -- 한 줄 요약 채움률 (매체별): 전체가 정상인데 특정 매체만 낮으면 그 매체 설명(재료) 수집 문제
    select count(*) n, count(a.summary_line) filled into cov from public.articles a
     where a.source_id = r.id and (a.candidate or a.label in ('security', 'pr')) and coalesce(a.label, '') <> 'not_security'
       and a.collected_at between now() - interval '27 hours' and now() - interval '3 hours';
    if cov_all_ok and cov.n >= 5 and cov.filled < cov.n * 0.5 then
      alerts := alerts || jsonb_build_object('level','warn','code','source_summary_low','source_id',r.id,
        'title', r.name || ' 한 줄 요약 채움률 ' || round(100.0 * cov.filled / cov.n) || '% (24시간 ' || cov.n || '건)',
        'detail', '기사 설명(요약 재료)을 못 읽고 있을 가능성 — Claude 세션에서 매체 목록 페이지를 열어 구조 확인');
    end if;
    if r.gap is not null then
      alerts := alerts || jsonb_build_object('level','warn','code','source_gap','source_id',r.id,
        'title', r.name || ' 놓친 기사가 있을 수 있음',
        'detail', '수집이 끊긴 사이 목록에서 밀려난 기사 가능 구간: ' || substr(r.gap, 5) || ' (매체 사이트에서 직접 확인)');
    end if;
  end loop;

  for d in select generate_series(kst::date - 1, kst::date, interval '1 day')::date loop
    foreach e in array array['am','noon','pm'] loop
      continue when e = 'noon' and d < date '2026-10-27';
      continue when d < date '2026-10-28';   -- 2026-10-28 DB 기록을 지우고 새로 시작 (그 전 판은 없음)
      due := d + case e when 'am' then time '07:00' when 'noon' then time '13:00' else time '19:00' end;
      if due <= kst and due > kst - interval '36 hours'
         and not exists (select 1 from public.briefings b where b.date = d and b.edition = e) then
        alerts := alerts || jsonb_build_object('level','error','code','briefing_missing',
          'title', to_char(d,'MM-DD') || ' ' || case e when 'am' then '06시판' when 'noon' then '12시판' else '18시판' end || ' 브리핑 누락',
          'detail', 'Claude 예약 작업 실행 기록과 GitHub Actions(브리핑 준비·반영)를 확인하세요');
      end if;
    end loop;
  end loop;

  if extract(isodow from kst) = 1 and kst::time >= time '08:00' and kst::date >= date '2026-11-02'
     and not exists (select 1 from public.briefings b where b.date = kst::date and b.edition = 'week') then
    alerts := alerts || jsonb_build_object('level','warn','code','weekly_missing',
      'title', to_char(kst::date,'MM-DD') || ' 주간 요약 누락',
      'detail', '월요일 06시판 브리핑 작업이 주간 요약도 작성함 — 브리핑 작업 실행 기록과 data/briefing-input/<날짜>-week.json 확인');
  end if;

  -- 수집 원문의 숨은 지시문 의심 (브리핑 본문 '수집 상태' 절을 없애며 대시보드로 이전, 2026-10-27)
  select count(*) n, string_agg(distinct s.name, ', ') names into r
    from public.collection_runs c join public.sources s on s.id = c.source_id
   where c.run_at > now() - interval '24 hours' and exists (select 1 from unnest(c.flags) f where f like 'inject:%');
  if r.n > 0 then
    alerts := alerts || jsonb_build_object('level','warn','code','inject_suspected',
      'title', '수집 원문에서 지시문 의심 문장 (24시간 ' || r.n || '회 · ' || r.names || ')',
      'detail', '원문은 저장소 data/suspicious/에 보관 — 브리핑은 그 지시를 따르지 않음. 오탐이면 무시, 반복되면 원문 확인');
  end if;

  for r in select j.jobname, count(*) n, max(left(d2.return_message,150)) msg
           from cron.job_run_details d2 join cron.job j using (jobid)
           where d2.start_time > now() - interval '24 hours' and d2.status = 'failed' group by 1 loop
    alerts := alerts || jsonb_build_object('level','warn','code','cron_failed',
      'title', '예약 신호 실패: ' || r.jobname || ' ' || r.n || '회', 'detail', coalesce(r.msg,''));
  end loop;
  select count(*) as n, max(status_code) as sc into r from net._http_response
   where created > now() - interval '24 hours' and (status_code is null or status_code >= 300);
  if r.n > 0 then
    alerts := alerts || jsonb_build_object('level','warn','code','dispatch_failed',
      'title', 'GitHub 실행 신호 응답 오류 ' || r.n || '건',
      'detail', '응답 코드 ' || coalesce(r.sc::text,'없음') || ' — 토큰 권한·만료 확인 필요');
  end if;

  for r in select distinct on (c.date, c.edition) c.date, c.edition, c.ok, c.problems
           from public.briefing_checks c where c.date >= kst::date - 2
           order by c.date, c.edition, c.checked_at desc loop
    if not r.ok then
      alerts := alerts || jsonb_build_object('level','error','code','briefing_check_failed',
        'title', to_char(r.date,'MM-DD') || ' ' || case r.edition when 'am' then '06시판' when 'noon' then '12시판' else '18시판' end || ' 브리핑 반영 검증 실패',
        'detail', (select string_agg(p, ' · ') from (select jsonb_array_elements_text(r.problems) p limit 3) z));
    end if;
  end loop;

  select jsonb_object_agg(k, v) into bk from (
    select b.target || '_' || case when b.target = 'storage' and b.kind in ('weekly','monthly') then 'full' else 'last' end as k,
           jsonb_build_object('run_at', b.run_at, 'kind', b.kind, 'ok', b.ok, 'bytes', b.bytes, 'used_bytes', b.used_bytes,
                              'limit_bytes', b.limit_bytes, 'detail', b.detail) as v
      from (select distinct on (target, (target = 'storage' and kind in ('weekly','monthly'))) * from public.backup_runs
             order by target, (target = 'storage' and kind in ('weekly','monthly')), run_at desc) b
  ) z;
  bk := coalesce(bk, '{}'::jsonb) || jsonb_build_object(
    'storage_ok_at', (select max(run_at) from public.backup_runs where target = 'storage' and kind = 'daily' and ok),
    'storage_used', (select coalesce(sum((o.metadata->>'size')::bigint), 0) from storage.objects o where o.bucket_id = 'backups'),
    'storage_limit', 900000000,
    'restore_ok_at', (select max(run_at) from public.backup_runs where target = 'restore_test' and ok));
  if exists (select 1 from public.backup_runs where target = 'storage')
     and coalesce((bk->>'storage_ok_at')::timestamptz, '-infinity') < now() - interval '26 hours' then
    alerts := alerts || jsonb_build_object('level','error','code','backup_storage_missing', 'title','주 백업(Supabase Storage) 26시간 이상 없음',
      'detail', coalesce(bk->'storage_last'->>'detail', '06시판 준비 작업(GitHub Actions) 로그 확인'));
  end if;
  if (bk->'github_last'->>'ok')::boolean is false and (bk->'github_last'->>'run_at')::timestamptz > now() - interval '26 hours' then
    alerts := alerts || jsonb_build_object('level','warn','code','backup_github_failed', 'title','보조 백업(GitHub) 실패',
      'detail', coalesce(bk->'github_last'->>'detail',''));
  end if;
  if (bk->'storage_full'->>'ok')::boolean is false then
    alerts := alerts || jsonb_build_object('level','warn','code','backup_full_failed', 'title','주 백업 전체 사본 실패',
      'detail', coalesce(bk->'storage_full'->>'detail',''));
  end if;
  if (bk->>'storage_used')::bigint > 0.9 * 900000000 then
    alerts := alerts || jsonb_build_object('level','warn','code','backup_storage_size',
      'title', '주 백업 용량 ' || round((bk->>'storage_used')::bigint / 1e6) || 'MB / 상한 900MB', 'detail','오래된 사본 자동 정리 중 — 보관 개수 조정 검토');
  end if;
  if (bk->'github_last'->>'used_bytes')::bigint > 0.9 * 900000000 then
    alerts := alerts || jsonb_build_object('level','warn','code','backup_github_size',
      'title', 'GitHub 저장소 ' || round((bk->'github_last'->>'used_bytes')::bigint / 1e6) || 'MB / 상한 900MB', 'detail','보조 백업 중단 임박');
  end if;
  if (bk->'restore_test_last'->>'ok')::boolean is false then
    alerts := alerts || jsonb_build_object('level','error','code','restore_test_failed', 'title','백업 복구 시험 실패',
      'detail', coalesce(left(bk->'restore_test_last'->>'detail', 200),''));
  elsif exists (select 1 from public.backup_runs where target = 'storage' and run_at < now() - interval '40 days')
        and coalesce((bk->>'restore_ok_at')::timestamptz, '-infinity') < now() - interval '40 days' then
    alerts := alerts || jsonb_build_object('level','warn','code','restore_test_old', 'title','복구 시험 40일 이상 미실행', 'detail','');
  end if;

  -- 매일 재구축 정의 점검 실패
  if (bk->'schema_check_last'->>'ok')::boolean is false then
    alerts := alerts || jsonb_build_object('level','error','code','schema_check_failed',
      'title','재구축 정의 점검 실패 (저장소 정의와 운영 DB 불일치)', 'detail', coalesce(left(bk->'schema_check_last'->>'detail', 200), ''));
  end if;
  -- main CI 실패 (마지막 결과 기준)
  select * into r from public.ci_runs order by run_at desc limit 1;
  if found and not r.ok then
    alerts := alerts || jsonb_build_object('level','error','code','ci_failed',
      'title', 'main 코드 자동 시험(CI) 실패 (' || left(r.sha, 7) || ')', 'detail', coalesce(r.detail, ''));
  end if;
  -- 정기 작업 (비밀값 교체 등): 14일 전 주의, 지나면 오류
  for r in select o.* from public.ops_reminders o where o.due <= kst::date + 14 order by o.due loop
    alerts := alerts || jsonb_build_object('level', case when r.due < kst::date then 'error' else 'warn' end,
      'code', 'reminder', 'source_id', r.key,
      'title', r.title || ' ' || case when r.due < kst::date then '기한 지남' else 'D-' || (r.due - kst::date) end || ' (' || r.due || ')',
      'detail', coalesce(r.note, ''));
  end loop;

  -- AI 한 줄 요약 현황 (요약 단계 실행 기록: source_id 없음, flags에 ai_summary)
  with runs as (
    select c.run_at, c.ok, c.fetched, c.new_count, c.error, c.flags,
           coalesce((select substr(f, 8)::bigint from unnest(c.flags) f where f like 'in_tok:%' limit 1), 0) tin,
           coalesce((select substr(f, 9)::bigint from unnest(c.flags) f where f like 'out_tok:%' limit 1), 0) tout,
           coalesce((select substr(f, 10)::int from unnest(c.flags) f where f like 'rejected:%' limit 1), 0) rej
      from public.collection_runs c
     where c.source_id is null and 'ai_summary' = any(c.flags) and c.run_at > now() - interval '40 days')
  select jsonb_build_object(
    'last', (select jsonb_build_object('run_at', run_at, 'ok', ok, 'target', fetched, 'done', new_count, 'rejected', rej, 'error', error,
                                       'why', (select jsonb_agg(substr(f, 5)) from unnest(flags) f where f like 'why:%'))
               from runs order by run_at desc limit 1),
    'runs_24h', (select count(*) from runs where run_at > now() - interval '24 hours'),
    'done_24h', (select coalesce(sum(new_count), 0) from runs where run_at > now() - interval '24 hours'),
    'rejected_24h', (select coalesce(sum(rej), 0) from runs where run_at > now() - interval '24 hours'),
    'failed_runs_24h', (select count(*) from runs where run_at > now() - interval '24 hours' and not ok),
    'coverage_n', cov_total.n, 'coverage_filled', cov_total.filled,
    'month_in_tok', (select coalesce(sum(tin), 0) from runs where run_at >= date_trunc('month', kst)::timestamp at time zone 'Asia/Seoul'),
    'month_out_tok', (select coalesce(sum(tout), 0) from runs where run_at >= date_trunc('month', kst)::timestamp at time zone 'Asia/Seoul'),
    'price_in_per_mtok', 0.10, 'price_out_per_mtok', 0.50, 'model', 'claude-haiku-5-5'
  ) into ai
  from (select count(*) n, count(a.summary_line) filled from public.articles a
         where (a.candidate or a.label in ('security', 'pr')) and coalesce(a.label, '') <> 'not_security'
           and a.collected_at between now() - interval '27 hours' and now() - interval '3 hours') cov_total;
  ai := ai || jsonb_build_object('month_cost_usd',
          round(((ai->>'month_in_tok')::numeric * 0.10 + (ai->>'month_out_tok')::numeric * 0.50) / 1e6, 4));
  if (ai->>'month_cost_usd')::numeric > 20 then
    alerts := alerts || jsonb_build_object('level','warn','code','ai_cost_high',
      'title', '이번 달 AI 요약 예상 비용 $' || (ai->>'month_cost_usd') || ' (기준 $20)',
      'detail', '평소 월 1달러 미만(Haiku 5.5) — 반복 실행·요약 대상 급증 여부 확인 (수집 상태의 AI 요약 표)');
  end if;

  if dbsize > 400 * 1024 * 1024 then
    alerts := alerts || jsonb_build_object('level','warn','code','db_size',
      'title','DB 용량 ' || (dbsize / 1024 / 1024) || 'MB / 500MB', 'detail','보관 정책 점검 필요');
  end if;

  return jsonb_build_object('checked_at', now(), 'db_size_mb', round(dbsize / 1024.0 / 1024.0, 1),
    'last_collect_at', last_any, 'alerts', alerts, 'ai', ai, 'sources', srcs, 'backup', bk,
    'remediations', coalesce((select jsonb_agg(jsonb_build_object('run_at', m.run_at, 'kind', m.kind, 'target', m.target, 'ok', m.ok) order by m.run_at desc)
                                 from (select * from public.remediation_runs where run_at > now() - interval '48 hours' order by run_at desc limit 15) m), '[]'::jsonb));
end $function$
;
