-- 자동 생성 파일: 운영 DB에서 내보낸 함수·색인·권한·정책·예약·보관함 정의. 직접 고치지 말 것.
-- 적용 순서: supabase/schema.sql(표) → 이 파일 → Vault 토큰 등록(README 재구축 절차)

-- ===== 색인 =====
CREATE INDEX IF NOT EXISTS articles_candidate_idx ON public.articles USING btree (published_at) WHERE candidate;
CREATE INDEX IF NOT EXISTS articles_collected_idx ON public.articles USING btree (collected_at DESC);
CREATE INDEX IF NOT EXISTS articles_event_collected_idx ON public.articles USING btree (event_id, collected_at DESC) WHERE (event_id IS NOT NULL);
CREATE INDEX IF NOT EXISTS articles_event_idx ON public.articles USING btree (event_id) WHERE (event_id IS NOT NULL);
CREATE INDEX IF NOT EXISTS articles_published_idx ON public.articles USING btree (published_at DESC);
CREATE INDEX IF NOT EXISTS articles_source_pub_idx ON public.articles USING btree (source_id, published_at DESC);
CREATE INDEX IF NOT EXISTS articles_summary_line_trgm ON public.articles USING gin (summary_line extensions.gin_trgm_ops) WHERE (summary_line IS NOT NULL);
CREATE INDEX IF NOT EXISTS articles_title_trgm ON public.articles USING gin (title extensions.gin_trgm_ops);
CREATE INDEX IF NOT EXISTS backup_runs_idx ON public.backup_runs USING btree (target, run_at DESC);
CREATE INDEX IF NOT EXISTS briefing_checks_idx ON public.briefing_checks USING btree (date, edition, checked_at DESC);
CREATE INDEX IF NOT EXISTS ci_runs_at_idx ON public.ci_runs USING btree (run_at DESC);
CREATE INDEX IF NOT EXISTS collection_runs_at_idx ON public.collection_runs USING btree (run_at DESC);
CREATE INDEX IF NOT EXISTS collection_runs_source_at_idx ON public.collection_runs USING btree (source_id, run_at DESC);
CREATE INDEX IF NOT EXISTS remediation_runs_idx ON public.remediation_runs USING btree (kind, target, run_at DESC);
CREATE INDEX IF NOT EXISTS security_events_date_idx ON public.security_events USING btree (start_date);

-- ===== 함수 =====
CREATE OR REPLACE FUNCTION public.apply_briefing(p_date date, p_markdown text, p_events jsonb, p_labels jsonb, p_stats jsonb DEFAULT '{}'::jsonb, p_edition text DEFAULT 'am'::text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public', 'pg_temp'
AS $function$
declare
  e jsonb;
  l jsonb;
  ln text;
  n_events int := 0;
  n_labels int := 0;
  n_lines int := 0;
begin
  if p_edition not in ('am', 'noon', 'pm', 'week') then
    raise exception 'edition must be am, noon, pm or week';
  end if;
  for e in select * from jsonb_array_elements(coalesce(p_events, '[]'::jsonb)) loop
    insert into events (slug, title, category, summary, cves, first_seen, last_seen)
    values (e->>'slug', coalesce(e->>'title', e->>'slug'), e->>'category', e->>'summary',
            coalesce(array(select jsonb_array_elements_text(e->'cves')), '{}'),
            p_date, p_date)
    on conflict (slug) do update
      set title = excluded.title,
          category = coalesce(excluded.category, events.category),
          summary = coalesce(excluded.summary, events.summary),
          cves = (select array(select distinct unnest(events.cves || excluded.cves))),
          last_seen = greatest(events.last_seen, p_date);
    n_events := n_events + 1;
  end loop;

  for l in select * from jsonb_array_elements(coalesce(p_labels, '[]'::jsonb)) loop
    ln := case when l->>'label' in ('security', 'pr')
               then nullif(btrim(left(regexp_replace(coalesce(l->>'line', ''), '\s+', ' ', 'g'), 80)), '') end;
    update articles
       set label = l->>'label',
           labeled_at = now(),
           event_id = (select id from events where slug = l->>'event_slug'),
           summary_line = case when summary_line is null and ln is not null then ln else summary_line end,
           summary_source = case when summary_line is null and ln is not null then 'claude' else summary_source end
     where id = (l->>'id')::bigint;
    n_labels := n_labels + 1;
    if ln is not null and found then n_lines := n_lines + 1; end if;
  end loop;

  if p_markdown is not null and length(p_markdown) > 0 then
    insert into briefings (date, edition, markdown, stats)
    values (p_date, p_edition, p_markdown, coalesce(p_stats, '{}'))
    on conflict (date, edition) do update set markdown = excluded.markdown, stats = excluded.stats, created_at = now();
  end if;

  return jsonb_build_object('events', n_events, 'labels', n_labels, 'lines', n_lines, 'edition', p_edition);
end $function$
;
revoke all on function public.apply_briefing(p_date date, p_markdown text, p_events jsonb, p_labels jsonb, p_stats jsonb, p_edition text) from public, anon, authenticated;
grant execute on function public.apply_briefing(p_date date, p_markdown text, p_events jsonb, p_labels jsonb, p_stats jsonb, p_edition text) to service_role;

CREATE OR REPLACE FUNCTION public.apply_retention()
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public', 'pg_temp'
AS $function$
declare
  n_articles int;
  n_runs int;
begin
  delete from articles
   where coalesce(published_at, collected_at) < now() - interval '90 days'
     and (label = 'not_security' or label is null);
  get diagnostics n_articles = row_count;
  delete from collection_runs where run_at < now() - interval '90 days';
  get diagnostics n_runs = row_count;
  return jsonb_build_object('deleted_articles', n_articles, 'deleted_runs', n_runs,
    'db_size_bytes', pg_database_size(current_database()), 'articles_total', (select count(*) from articles));
end $function$
;
revoke all on function public.apply_retention() from public, anon, authenticated;
grant execute on function public.apply_retention() to service_role;

CREATE OR REPLACE FUNCTION public.apply_security_events(p_events jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public', 'pg_temp'
AS $function$
declare e jsonb; n int := 0; skipped int := 0; sd date; ed date;
begin
  for e in select * from jsonb_array_elements(coalesce(p_events, '[]'::jsonb)) loop
    begin
      sd := (e->>'start_date')::date;
      ed := nullif(e->>'end_date', '')::date;
      if sd is null or coalesce(length(e->>'name'), 0) < 2 or (ed is not null and ed < sd)
         or (e->>'url' is not null and e->>'url' !~ '^https?://') then
        skipped := skipped + 1; continue;
      end if;
      insert into security_events (name, start_date, end_date, place, organizer, url, major, note, article_ids)
      values (left(e->>'name', 120), sd, ed, left(e->>'place', 120), left(e->>'organizer', 120), e->>'url',
              coalesce((e->>'major')::boolean, false), left(e->>'note', 200),
              coalesce(array(select jsonb_array_elements_text(e->'article_ids')::bigint), '{}'))
      on conflict (name_key, start_date) do update set
        end_date = coalesce(excluded.end_date, security_events.end_date),
        place = coalesce(excluded.place, security_events.place),
        organizer = coalesce(excluded.organizer, security_events.organizer),
        url = coalesce(security_events.url, excluded.url),
        major = security_events.major or excluded.major,
        note = coalesce(excluded.note, security_events.note),
        article_ids = (select array(select distinct unnest(security_events.article_ids || excluded.article_ids))),
        updated_at = now();
      n := n + 1;
    exception when others then
      skipped := skipped + 1;
    end;
  end loop;
  return jsonb_build_object('events', n, 'skipped', skipped);
end $function$
;
revoke all on function public.apply_security_events(p_events jsonb) from public, anon, authenticated;
grant execute on function public.apply_security_events(p_events jsonb) to service_role;

CREATE OR REPLACE FUNCTION public.auto_remediate()
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
  kst timestamp := now() at time zone 'Asia/Seoul';
  today date := (now() at time zone 'Asia/Seoul')::date;
  done jsonb := '[]'::jsonb;
  last_collect timestamptz;
  e text; due timestamp; tgt text; rid bigint;
  r record;
  alerts jsonb := '[]'::jsonb;
  pending text := '';
  n_pending int := 0;
begin
  begin
    select max(run_at) into last_collect from public.collection_runs;
    if last_collect < now() - interval '90 minutes'
       and public.remediation_count('collect_restart', '', interval '60 minutes') = 0
       and public.remediation_count('collect_restart', '', interval '6 hours') < 2 then
      rid := public.dispatch_github_workflow('collect.yml');
      perform public.log_remediation('collect_restart', '', true, rid, '마지막 수집 ' || to_char(last_collect at time zone 'Asia/Seoul', 'MM-DD HH24:MI'));
      done := done || jsonb_build_array('collect_restart');
    end if;
  exception when others then
    perform public.log_remediation('collect_restart', 'error', false, null, sqlerrm);
  end;

  foreach e in array array['am', 'noon', 'pm'] loop
    continue when e = 'noon' and today < date '2026-10-27';
    due := today + case e when 'am' then time '06:40' when 'noon' then time '12:40' else time '18:40' end;
    tgt := today || '-' || e;
    begin
      if kst >= due and kst < due + interval '2 hours'
         and not exists (select 1 from public.briefings b where b.date = today and b.edition = e)
         and public.remediation_count('briefing_refire', tgt, interval '1 day') = 0 then
        rid := public.fire_routine('briefing', '자동 조치: ' || tgt || ' 브리핑이 예정 시각에 생성되지 않아 다시 실행합니다. 평소 절차대로 이 판을 작성하세요.');
        perform public.log_remediation('briefing_refire', tgt, rid is not null, rid, case when rid is null then 'API 실행 주소 미설정' else '브리핑 작업 재실행' end);
        done := done || jsonb_build_array('briefing_refire:' || tgt);
      end if;
    exception when others then
      perform public.log_remediation('briefing_refire', tgt, false, null, sqlerrm);
    end;
  end loop;

  for r in select distinct on (c.date, c.edition) c.date, c.edition, c.ok, c.problems, c.checked_at
             from public.briefing_checks c where c.checked_at > now() - interval '3 hours'
            order by c.date, c.edition, c.checked_at desc loop
    continue when r.ok;
    tgt := r.date || '-' || r.edition;
    begin
      if r.problems::text ~ '(DB|대시보드)' and public.remediation_count('sync_retry', tgt, interval '1 day') = 0 then
        rid := public.dispatch_github_workflow('sync-briefing.yml');
        perform public.log_remediation('sync_retry', tgt, true, rid, left(r.problems::text, 300));
        done := done || jsonb_build_array('sync_retry:' || tgt);
      end if;
    exception when others then
      perform public.log_remediation('sync_retry', tgt, false, null, sqlerrm);
    end;
    begin
      if r.problems::text ~ '(라벨|사건|본문|slug|링크)' and public.remediation_count('briefing_fix', tgt, interval '1 day') = 0 then
        rid := public.fire_routine('briefing', '보완 요청: ' || tgt || ' 브리핑 출력 검증 실패 — ' || left(r.problems::text, 1500));
        perform public.log_remediation('briefing_fix', tgt, rid is not null, rid, case when rid is null then 'API 실행 주소 미설정' else left(r.problems::text, 300) end);
        done := done || jsonb_build_array('briefing_fix:' || tgt);
      end if;
    exception when others then
      perform public.log_remediation('briefing_fix', tgt, false, null, sqlerrm);
    end;
  end loop;

  begin
    if kst::time >= time '06:00'
       and not exists (select 1 from public.backup_runs where target = 'storage' and kind = 'daily' and ok
                        and run_at >= (today + time '05:00') at time zone 'Asia/Seoul')
       and public.remediation_count('backup_retry', today::text, interval '50 minutes') = 0
       and public.remediation_count('backup_retry', today::text, interval '1 day') < 2 then
      rid := public.dispatch_github_workflow('backup.yml');
      perform public.log_remediation('backup_retry', today::text, true, rid, '오늘 주 백업 성공 기록 없음');
      done := done || jsonb_build_array('backup_retry');
    end if;
  exception when others then
    perform public.log_remediation('backup_retry', today::text, false, null, sqlerrm);
  end;

  begin
    alerts := coalesce(public.system_alerts()->'alerts', '[]'::jsonb);
  exception when others then
    alerts := jsonb_build_array(jsonb_build_object('level', 'error', 'code', 'system_alerts_failed',
                'title', '이상 점검 함수 오류: ' || left(sqlerrm, 120)));
  end;
  if exists (select 1 from public.remediation_runs where run_at > now() - interval '1 hour' and not ok
              and request_id is null and coalesce(detail, '') not like 'API 실행 주소 미설정%') then
    alerts := alerts || jsonb_build_array(jsonb_build_object('level', 'error', 'code', 'remediation_failed',
                'title', '자동 조치 실행 오류 (실행 신호·토큰 확인 필요)'));
  end if;
  begin
    insert into public.alert_state (key, title)
    select (a->>'code') || ':' || coalesce(a->>'source_id', a->>'title'), a->>'title'
      from jsonb_array_elements(alerts) a where a->>'level' = 'error'
    on conflict (key) do update set last_seen = now(), title = excluded.title;
    delete from public.alert_state where last_seen < now() - interval '1 minute';

    for r in select * from public.alert_state
              where first_seen <= now() - interval '20 minutes' and (last_notified is null or last_notified < now() - interval '6 hours') loop
      pending := pending || '- ' || r.title || ' (' || to_char(r.first_seen at time zone 'Asia/Seoul', 'MM-DD HH24:MI') || '부터)' || E'\n';
      n_pending := n_pending + 1;
    end loop;
    if n_pending > 0 then
      rid := public.fire_routine('alert', '알림: 확인 필요 — 해결되지 않은 오류 ' || n_pending || '건 (사용자 조치 필요할 수 있음)' || E'\n' || pending
                                          || '최근 자동 조치: ' || coalesce((select string_agg(kind || '(' || target || ')', ', ')
                                               from (select kind, target from public.remediation_runs where run_at > now() - interval '6 hours'
                                                     order by run_at desc limit 8) z), '없음'));
      perform public.log_remediation('notify', '', rid is not null, rid, case when rid is null then 'API 실행 주소 미설정: ' else '' end || left(pending, 300));
      update public.alert_state set last_notified = now()
       where first_seen <= now() - interval '20 minutes' and (last_notified is null or last_notified < now() - interval '6 hours');
      done := done || jsonb_build_array('notify');
    end if;
  exception when others then
    perform public.log_remediation('notify', 'error', false, null, sqlerrm);
  end;

  begin
    for r in select a->>'source_id' sid, a->>'title' title, s.first_seen
               from jsonb_array_elements(alerts) a
               join public.alert_state s on s.key = (a->>'code') || ':' || coalesce(a->>'source_id', a->>'title')
              where a->>'code' = 'source_failing' and a->>'detail' like '수집 0건%' and s.first_seen <= now() - interval '3 hours' loop
      if public.remediation_count('repair_request', r.sid, interval '1 day') = 0 then
        rid := public.fire_routine('alert', '수리 요청: ' || r.sid || ' — ' || r.title || ' (수집 0건, 사이트 구조 변경 추정)');
        perform public.log_remediation('repair_request', r.sid, rid is not null, rid, case when rid is null then 'API 실행 주소 미설정' else r.title end);
        done := done || jsonb_build_array('repair_request:' || r.sid);
      end if;
    end loop;
  exception when others then
    perform public.log_remediation('repair_request', 'error', false, null, sqlerrm);
  end;

  return jsonb_build_object('at', now(), 'actions', done);
end $function$
;
revoke all on function public.auto_remediate() from public, anon, authenticated;
grant execute on function public.auto_remediate() to service_role;

CREATE OR REPLACE FUNCTION public.backup_objects()
 RETURNS TABLE(name text, bytes bigint, created_at timestamp with time zone)
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
  select o.name, coalesce((o.metadata->>'size')::bigint, 0), o.created_at
    from storage.objects o where o.bucket_id = 'backups' order by o.name
$function$
;
revoke all on function public.backup_objects() from public, anon, authenticated;
grant execute on function public.backup_objects() to service_role;

CREATE OR REPLACE FUNCTION public.dispatch_github_workflow(p_workflow text, p_inputs jsonb DEFAULT '{}'::jsonb)
 RETURNS bigint
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public', 'pg_temp'
AS $function$
declare
  tok text;
  rid bigint;
begin
  if p_workflow not in ('collect.yml', 'daily.yml', 'restore-test.yml', 'schema-sync.yml', 'backup.yml', 'sync-briefing.yml') then
    raise exception 'unsupported workflow %', p_workflow;
  end if;
  select decrypted_secret into tok from vault.decrypted_secrets where name = 'github_dispatch_token' limit 1;
  if tok is null then
    raise exception 'vault secret github_dispatch_token not found';
  end if;
  select net.http_post(
    url := 'https://api.github.com/repos/deep-taker/security-news-collector/actions/workflows/' || p_workflow || '/dispatches',
    headers := jsonb_build_object(
      'Authorization', 'Bearer ' || tok,
      'Accept', 'application/vnd.github+json',
      'X-GitHub-Api-Version', '2022-11-28',
      'User-Agent', 'security-news-collector-cron',
      'Content-Type', 'application/json'),
    body := jsonb_build_object('ref', 'main', 'inputs', coalesce(p_inputs, '{}'::jsonb))
  ) into rid;
  return rid;
end $function$
;
revoke all on function public.dispatch_github_workflow(p_workflow text, p_inputs jsonb) from public, anon, authenticated;
grant execute on function public.dispatch_github_workflow(p_workflow text, p_inputs jsonb) to service_role;

CREATE OR REPLACE FUNCTION public.error_class(p text)
 RETURNS text
 LANGUAGE sql
 IMMUTABLE
 SET search_path TO ''
AS $function$
  select case
    when p is null or p = '' then null
    when p ilike '%timeout%' or p ilike '%timed out%' then '접속 시간 초과'
    when p ~ '\m403\M' then '접근 거부(403)'
    when p ~ '\m404\M' then '주소 없음(404)'
    when p ~ '\m429\M' then '요청 제한(429)'
    when p ~ '\m5\d\d\M' then '사이트 서버 오류(5xx)'
    when p ilike '%ConnectionError%' or p ilike '%Max retries%' then '접속 실패'
    when p like '수집 0건%' then '수집 0건 (사이트 구조 변경 가능성)'
    when p ilike '%상한%' then '용량 상한'
    else '처리 오류'
  end
$function$
;
revoke all on function public.error_class(p text) from public, anon, authenticated;
grant execute on function public.error_class(p text) to service_role;

CREATE OR REPLACE FUNCTION public.export_definitions()
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
  out text := '';
  r record;
  cols text;
begin
  out := out || E'-- 자동 생성 파일: 운영 DB에서 내보낸 함수·색인·권한·정책·예약·보관함 정의. 직접 고치지 말 것.\n'
             || E'-- 적용 순서: supabase/schema.sql(표) → 이 파일 → Vault 토큰 등록(README 재구축 절차)\n\n';

  out := out || E'-- ===== 색인 =====\n';
  for r in select indexdef from pg_indexes where schemaname = 'public' and indexname not like '%_pkey' and indexdef not like 'CREATE UNIQUE%'
           order by tablename, indexname loop
    out := out || regexp_replace(r.indexdef, '^CREATE INDEX ', 'CREATE INDEX IF NOT EXISTS ') || E';\n';
  end loop;

  out := out || E'\n-- ===== 함수 =====\n';
  for r in select p.oid, p.proname, pg_get_function_identity_arguments(p.oid) args, coalesce(p.proacl, acldefault('f', p.proowner)) proacl
             from pg_proc p join pg_namespace n on n.oid = p.pronamespace
            where n.nspname = 'public' and p.prokind = 'f' order by p.proname loop
    out := out || pg_get_functiondef(r.oid) || E';\n';
    out := out || format(E'revoke all on function public.%I(%s) from public, anon, authenticated;\n', r.proname, r.args);
    -- PUBLIC(모든 역할) 실행 권한도 그대로 적는다 → 권한 퇴행이 파일에 드러나고 재구축 점검이 잡는다 (2026-10-27)
    out := out || coalesce((select string_agg(format('grant execute on function public.%I(%s) to %s;', r.proname, r.args,
                                                     case when g = '-' then 'public' else quote_ident(g) end), E'\n' order by g)
                              from (select distinct (aclexplode(r.proacl)).grantee::regrole::text g) x
                             where g in ('-', 'anon', 'authenticated', 'service_role')) || E'\n', '') || E'\n';
  end loop;

  out := out || E'-- ===== 표 권한·행 단위 보안 =====\n';
  for r in select c.relname, c.relrowsecurity from pg_class c join pg_namespace n on n.oid = c.relnamespace
            where n.nspname = 'public' and c.relkind = 'r' order by c.relname loop
    out := out || format(E'alter table public.%I %s row level security;\n', r.relname, case when r.relrowsecurity then 'enable' else 'disable' end);
    out := out || format(E'revoke all on public.%I from public, anon, authenticated;\n', r.relname);
    out := out || coalesce((select string_agg(format('grant %s on public.%I to %s;', string_agg_priv, r.relname,
                                                     case when grantee = 'PUBLIC' then 'public' else quote_ident(grantee) end), E'\n')
      from (select grantee, string_agg(privilege_type, ', ' order by privilege_type) string_agg_priv
              from information_schema.role_table_grants
             where table_schema = 'public' and table_name = r.relname and grantee in ('PUBLIC', 'anon', 'authenticated', 'service_role')
             group by grantee) g) || E'\n', '');
    out := out || coalesce((select string_agg(format('grant %s (%s) on public.%I to %s;', cp.ptype, cp.colnames, r.relname,
                                                     case when cp.grantee = 'PUBLIC' then 'public' else quote_ident(cp.grantee) end), E'\n')
      from (select c.grantee, c.privilege_type ptype, string_agg(quote_ident(c.column_name), ', ' order by c.column_name) colnames
              from information_schema.column_privileges c
             where c.table_schema = 'public' and c.table_name = r.relname and c.grantee in ('PUBLIC', 'anon', 'authenticated')
               and not exists (select 1 from information_schema.role_table_grants t
                                where t.table_schema = 'public' and t.table_name = r.relname
                                  and t.grantee = c.grantee and t.privilege_type = c.privilege_type)
             group by c.grantee, c.privilege_type) cp) || E'\n', '');
  end loop;
  for r in select sequence_name from information_schema.sequences where sequence_schema = 'public' order by 1 loop
    out := out || format(E'grant usage, select on sequence public.%I to service_role;\n', r.sequence_name);
  end loop;
  for r in select * from pg_policies where schemaname = 'public' order by tablename, policyname loop
    out := out || format(E'drop policy if exists %I on public.%I;\ncreate policy %I on public.%I as %s for %s to %s%s%s;\n',
      r.policyname, r.tablename, r.policyname, r.tablename, r.permissive, r.cmd, array_to_string(r.roles, ', '),
      coalesce(' using (' || r.qual || ')', ''), coalesce(' with check (' || r.with_check || ')', ''));
  end loop;

  out := out || E'\n-- ===== Storage 보관함 (Supabase에서만) =====\n';
  for r in select id, public, file_size_limit from storage.buckets order by id loop
    out := out || format(E'do $b$ begin if exists (select 1 from pg_namespace where nspname = ''storage'') then\n'
      || E'  insert into storage.buckets (id, name, public, file_size_limit) values (%L, %L, %s, %s)\n'
      || E'  on conflict (id) do update set public = excluded.public, file_size_limit = excluded.file_size_limit;\nend if; end $b$;\n',
      r.id, r.id, case when r.public then 'true' else 'false' end, coalesce(r.file_size_limit::text, 'null'));
  end loop;

  out := out || E'\n-- ===== 예약 (pg_cron, Supabase에서만) =====\n';
  for r in select jobname, schedule, command from cron.job order by jobname loop
    out := out || format(E'do $c$ begin if exists (select 1 from pg_extension where extname = ''pg_cron'') then\n'
      || E'  perform cron.schedule(%L, %L, %L);\nend if; end $c$;\n', r.jobname, r.schedule, r.command);
  end loop;

  select string_agg(format('%s.%s %s%s%s', table_name, column_name, data_type,
                           case when is_nullable = 'NO' then ' not null' else '' end,
                           coalesce(' default ' || column_default, '')), E'\n' order by table_name, ordinal_position)
    into cols from information_schema.columns where table_schema = 'public';

  return jsonb_build_object('sql', out, 'columns', cols, 'exported_at', now());
end $function$
;
revoke all on function public.export_definitions() from public, anon, authenticated;
grant execute on function public.export_definitions() to service_role;

CREATE OR REPLACE FUNCTION public.fire_routine(p_which text, p_text text)
 RETURNS bigint
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
  u text; tok text; rid bigint;
begin
  if p_which not in ('briefing', 'alert') then raise exception 'unsupported routine %', p_which; end if;
  select decrypted_secret into u from vault.decrypted_secrets where name = p_which || '_fire_url' limit 1;
  select decrypted_secret into tok from vault.decrypted_secrets where name = p_which || '_fire_token' limit 1;
  if u is null or tok is null then return null; end if;
  if u !~ '^https://api\.anthropic\.com/v1/claude_code/routines/trig_[A-Za-z0-9]+/fire$' then
    raise exception 'fire url 형식 오류';
  end if;
  select net.http_post(
    url := u,
    headers := jsonb_build_object('Authorization', 'Bearer ' || tok, 'anthropic-beta', 'experimental-cc-routine-2026-04-01',
                                  'anthropic-version', '2023-06-01', 'Content-Type', 'application/json'),
    body := jsonb_build_object('text', left(p_text, 4000))
  ) into rid;
  return rid;
end $function$
;
revoke all on function public.fire_routine(p_which text, p_text text) from public, anon, authenticated;
grant execute on function public.fire_routine(p_which text, p_text text) to service_role;

CREATE OR REPLACE FUNCTION public.log_remediation(p_kind text, p_target text, p_ok boolean, p_rid bigint, p_detail text)
 RETURNS void
 LANGUAGE sql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
  insert into public.remediation_runs (kind, target, ok, request_id, detail) values (p_kind, coalesce(p_target, ''), p_ok, p_rid, left(p_detail, 500));
$function$
;
revoke all on function public.log_remediation(p_kind text, p_target text, p_ok boolean, p_rid bigint, p_detail text) from public, anon, authenticated;
grant execute on function public.log_remediation(p_kind text, p_target text, p_ok boolean, p_rid bigint, p_detail text) to service_role;

CREATE OR REPLACE FUNCTION public.remediation_count(p_kind text, p_target text, p_since interval)
 RETURNS integer
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
  select count(*)::int from public.remediation_runs where kind = p_kind and target = coalesce(p_target, '') and run_at > now() - p_since;
$function$
;
revoke all on function public.remediation_count(p_kind text, p_target text, p_since interval) from public, anon, authenticated;
grant execute on function public.remediation_count(p_kind text, p_target text, p_since interval) to service_role;

CREATE OR REPLACE FUNCTION public.reset_sequences()
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
begin
  perform setval('public.articles_id_seq', greatest(coalesce((select max(id) from public.articles), 1), 1));
  perform setval('public.events_id_seq', greatest(coalesce((select max(id) from public.events), 1), 1));
  perform setval('public.security_events_id_seq', greatest(coalesce((select max(id) from public.security_events), 1), 1));
  return jsonb_build_object('articles', (select max(id) from public.articles), 'events', (select max(id) from public.events),
                            'security_events', (select max(id) from public.security_events));
end $function$
;
revoke all on function public.reset_sequences() from public, anon, authenticated;
grant execute on function public.reset_sequences() to service_role;

CREATE OR REPLACE FUNCTION public.retry_failed_sources()
 RETURNS text
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
  failed text;
begin
  select string_agg(source_id, ',' order by source_id) into failed from (
    select distinct on (c.source_id) c.source_id, c.ok
      from public.collection_runs c
     where c.run_at > now() - interval '15 minutes'
     order by c.source_id, c.run_at desc
  ) t where not ok;
  if failed is null then
    return null;
  end if;
  perform public.dispatch_github_workflow('collect.yml', jsonb_build_object('only', failed));
  return failed;
end $function$
;
revoke all on function public.retry_failed_sources() from public, anon, authenticated;
grant execute on function public.retry_failed_sources() to service_role;

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
revoke all on function public.system_alerts() from public, anon, authenticated;
grant execute on function public.system_alerts() to service_role;

CREATE OR REPLACE FUNCTION public.system_alerts_public()
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
  a jsonb := public.system_alerts();
begin
  return jsonb_build_object(
    'checked_at', a->'checked_at', 'db_size_mb', a->'db_size_mb', 'last_collect_at', a->'last_collect_at', 'remediations', a->'remediations',
    'ai', case when a->'ai' is null then null else (a->'ai') || jsonb_build_object('last', (a->'ai'->'last') - 'error'
            || jsonb_build_object('error', public.error_class(a->'ai'->'last'->>'error'))) end,
    'alerts', coalesce((select jsonb_agg(x - 'detail' || jsonb_build_object('detail',
        case when x->>'code' in ('source_failing','source_failed','backup_storage_missing','backup_github_failed','backup_full_failed')
             then public.error_class(x->>'detail')
             when x->>'code' in ('restore_test_failed','cron_failed','dispatch_failed','briefing_check_failed','schema_check_failed') then '상세 내용은 운영 기록에서 확인'
             else x->>'detail' end))
      from jsonb_array_elements(a->'alerts') x), '[]'::jsonb),
    'sources', coalesce((select jsonb_agg(s - 'last_error' || jsonb_build_object('last_error', public.error_class(s->>'last_error')))
      from jsonb_array_elements(a->'sources') s), '[]'::jsonb),
    'backup', (select coalesce(jsonb_object_agg(k, case when jsonb_typeof(v) = 'object'
                                                      then v - 'detail' || jsonb_build_object('detail', public.error_class(v->>'detail'))
                                                      else v end), '{}'::jsonb)
                 from jsonb_each(coalesce(a->'backup', '{}'::jsonb)) e(k, v))
  );
end $function$
;
revoke all on function public.system_alerts_public() from public, anon, authenticated;
grant execute on function public.system_alerts_public() to anon;
grant execute on function public.system_alerts_public() to authenticated;
grant execute on function public.system_alerts_public() to service_role;

-- ===== 표 권한·행 단위 보안 =====
alter table public.alert_state enable row level security;
revoke all on public.alert_state from public, anon, authenticated;
grant DELETE, INSERT, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE on public.alert_state to service_role;
alter table public.articles enable row level security;
revoke all on public.articles from public, anon, authenticated;
grant DELETE, INSERT, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE on public.articles to service_role;
grant SELECT (ai_related, candidate, collected_at, event_id, id, keywords, label, published_at, source_id, summary_line, summary_source, title, url) on public.articles to anon;
alter table public.backup_runs enable row level security;
revoke all on public.backup_runs from public, anon, authenticated;
grant DELETE, INSERT, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE on public.backup_runs to service_role;
alter table public.briefing_checks enable row level security;
revoke all on public.briefing_checks from public, anon, authenticated;
grant DELETE, INSERT, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE on public.briefing_checks to service_role;
alter table public.briefings enable row level security;
revoke all on public.briefings from public, anon, authenticated;
grant SELECT on public.briefings to anon;
grant DELETE, INSERT, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE on public.briefings to service_role;
alter table public.ci_runs enable row level security;
revoke all on public.ci_runs from public, anon, authenticated;
grant DELETE, INSERT, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE on public.ci_runs to service_role;
alter table public.collection_runs enable row level security;
revoke all on public.collection_runs from public, anon, authenticated;
grant DELETE, INSERT, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE on public.collection_runs to service_role;
alter table public.events enable row level security;
revoke all on public.events from public, anon, authenticated;
grant SELECT on public.events to anon;
grant DELETE, INSERT, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE on public.events to service_role;
alter table public.ops_reminders enable row level security;
revoke all on public.ops_reminders from public, anon, authenticated;
grant DELETE, INSERT, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE on public.ops_reminders to service_role;
alter table public.remediation_runs enable row level security;
revoke all on public.remediation_runs from public, anon, authenticated;
grant DELETE, INSERT, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE on public.remediation_runs to service_role;
alter table public.security_events enable row level security;
revoke all on public.security_events from public, anon, authenticated;
grant SELECT on public.security_events to anon;
grant DELETE, INSERT, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE on public.security_events to service_role;
alter table public.sources enable row level security;
revoke all on public.sources from public, anon, authenticated;
grant SELECT on public.sources to anon;
grant DELETE, INSERT, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE on public.sources to service_role;
grant usage, select on sequence public.articles_id_seq to service_role;
grant usage, select on sequence public.backup_runs_id_seq to service_role;
grant usage, select on sequence public.briefing_checks_id_seq to service_role;
grant usage, select on sequence public.ci_runs_id_seq to service_role;
grant usage, select on sequence public.collection_runs_id_seq to service_role;
grant usage, select on sequence public.events_id_seq to service_role;
grant usage, select on sequence public.remediation_runs_id_seq to service_role;
grant usage, select on sequence public.security_events_id_seq to service_role;
drop policy if exists public_read on public.articles;
create policy public_read on public.articles as PERMISSIVE for SELECT to anon using (((label = ANY (ARRAY['security'::text, 'pr'::text])) OR ((label IS NULL) AND candidate)));
drop policy if exists public_read on public.briefings;
create policy public_read on public.briefings as PERMISSIVE for SELECT to anon using (true);
drop policy if exists public_read on public.events;
create policy public_read on public.events as PERMISSIVE for SELECT to anon using (true);
drop policy if exists public_read on public.security_events;
create policy public_read on public.security_events as PERMISSIVE for SELECT to anon using (true);
drop policy if exists public_read on public.sources;
create policy public_read on public.sources as PERMISSIVE for SELECT to anon using (true);

-- ===== Storage 보관함 (Supabase에서만) =====
do $b$ begin if exists (select 1 from pg_namespace where nspname = 'storage') then
  insert into storage.buckets (id, name, public, file_size_limit) values ('backups', 'backups', false, 45000000)
  on conflict (id) do update set public = excluded.public, file_size_limit = excluded.file_size_limit;
end if; end $b$;

-- ===== 예약 (pg_cron, Supabase에서만) =====
do $c$ begin if exists (select 1 from pg_extension where extname = 'pg_cron') then
  perform cron.schedule('auto-remediate', '3,13,23,33,43,53 * * * *', 'select public.auto_remediate()');
end if; end $c$;
do $c$ begin if exists (select 1 from pg_extension where extname = 'pg_cron') then
  perform cron.schedule('backup-daily', '45 20 * * *', 'select public.dispatch_github_workflow(''backup.yml'')');
end if; end $c$;
do $c$ begin if exists (select 1 from pg_extension where extname = 'pg_cron') then
  perform cron.schedule('cleanup-logs', '10 19 * * *', 'delete from cron.job_run_details where end_time < now() - interval ''30 days''; delete from public.briefing_checks where checked_at < now() - interval ''30 days''; delete from public.backup_runs where run_at < now() - interval ''90 days''; delete from public.remediation_runs where run_at < now() - interval ''90 days''');
end if; end $c$;
do $c$ begin if exists (select 1 from pg_extension where extname = 'pg_cron') then
  perform cron.schedule('collect-hourly', '17 * * * *', 'select public.dispatch_github_workflow(''collect.yml'')');
end if; end $c$;
do $c$ begin if exists (select 1 from pg_extension where extname = 'pg_cron') then
  perform cron.schedule('collect-retry', '27 * * * *', 'select public.retry_failed_sources()');
end if; end $c$;
do $c$ begin if exists (select 1 from pg_extension where extname = 'pg_cron') then
  perform cron.schedule('prepare-am', '35 20 * * *', 'select public.dispatch_github_workflow(''daily.yml'')');
end if; end $c$;
do $c$ begin if exists (select 1 from pg_extension where extname = 'pg_cron') then
  perform cron.schedule('prepare-noon', '35 2 * * *', 'select public.dispatch_github_workflow(''daily.yml'')');
end if; end $c$;
do $c$ begin if exists (select 1 from pg_extension where extname = 'pg_cron') then
  perform cron.schedule('prepare-pm', '35 8 * * *', 'select public.dispatch_github_workflow(''daily.yml'')');
end if; end $c$;
do $c$ begin if exists (select 1 from pg_extension where extname = 'pg_cron') then
  perform cron.schedule('restore-test', '10 22 1 * *', 'select public.dispatch_github_workflow(''restore-test.yml'')');
end if; end $c$;
do $c$ begin if exists (select 1 from pg_extension where extname = 'pg_cron') then
  perform cron.schedule('schema-sync', '0 20 * * *', 'select public.dispatch_github_workflow(''schema-sync.yml'')');
end if; end $c$;
