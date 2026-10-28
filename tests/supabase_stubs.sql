-- 시험 DB용: Supabase에만 있는 역할·스키마를 최소한으로 흉내 (재구축 정의를 그대로 적용해 보기 위함)
do $$ begin create role anon; exception when duplicate_object then null; end $$;
do $$ begin create role authenticated; exception when duplicate_object then null; end $$;
do $$ begin create role service_role; exception when duplicate_object then null; end $$;
create schema if not exists storage;
create table if not exists storage.buckets (id text primary key, name text, public boolean, file_size_limit bigint);
create table if not exists storage.objects (bucket_id text, name text, metadata jsonb, created_at timestamptz default now());
create schema if not exists cron;
create table if not exists cron.job (jobid bigserial primary key, jobname text, schedule text, command text);
create table if not exists cron.job_run_details (jobid bigint, status text, return_message text, start_time timestamptz, end_time timestamptz);
create schema if not exists net;
create table if not exists net._http_response (id bigserial, status_code int, content text, created timestamptz default now());
create or replace function net.http_post(url text, headers jsonb, body jsonb) returns bigint language sql as 'select 0::bigint';
create schema if not exists vault;
create table if not exists vault.decrypted_secrets (name text, decrypted_secret text);
