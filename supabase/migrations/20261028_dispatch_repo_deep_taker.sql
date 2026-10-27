-- 2026-10-28: 저장소를 deep-taker/security-news-collector(새 공개 저장소)로 옮김 (사용자 결정).
-- GitHub 작업 실행 주소만 바꾼다. 적용 시점: 새 공개 저장소에 코드·Secrets를 올리고 Vault github_dispatch_token을
-- 새 저장소 권한 토큰으로 바꾼 직후 (그 전에 적용하면 옛 저장소 이름 변경 뒤 실행 신호가 어긋남).
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
