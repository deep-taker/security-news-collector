-- 2026-11-22: AI 한 줄 요약·칼럼 필자 Gemini 전환 1단계 (사용자 승인 뒤 적용).
-- system_alerts() 안의 모델 이름, 유료 환산 기준 단가(Gemini 3.5 Flash-Lite: 입력 $0.30, 출력 $2.50 / 100만 토큰),
-- ai_summary_low 안내 문구(ANTHROPIC_API_KEY → GEMINI_API_KEY)를 갱신한다.
-- 함수 권한은 그대로 유지됨.

do $$
declare
  d text;
  o text;
begin
  d := pg_get_functiondef('public.system_alerts()'::regprocedure);

  o := $o$'GitHub Secrets의 ANTHROPIC_API_KEY 등록·만료, API 사용 한도·결제 상태 확인 (수집 작업 로그의 AI 요약 결과 참고)'$o$;
  if (length(d) - length(replace(d, o, ''))) / length(o) <> 1 then
    raise exception 'system_alerts: ai_summary_low 안내 문구가 1곳이 아님';
  end if;
  d := replace(d, o, $n$'GitHub Secrets의 GEMINI_API_KEY 등록·만료, 무료 등급 일일 호출 한도 확인 (수집 작업 로그의 AI 요약 결과 참고)'$n$);

  o := $o$'price_in_per_mtok', 0.10, 'price_out_per_mtok', 0.50, 'model', 'claude-haiku-5-5'$o$;
  if (length(d) - length(replace(d, o, ''))) / length(o) <> 1 then
    raise exception 'system_alerts: 단가·모델 정의가 1곳이 아님';
  end if;
  d := replace(d, o, $n$'price_in_per_mtok', 0.30, 'price_out_per_mtok', 2.50, 'model', 'gemini-3.5-flash-lite'$n$);

  o := $o$round(((ai->>'month_in_tok')::numeric * 0.10 + (ai->>'month_out_tok')::numeric * 0.50) / 1e6, 4)$o$;
  if (length(d) - length(replace(d, o, ''))) / length(o) <> 1 then
    raise exception 'system_alerts: 월 비용 계산식이 1곳이 아님';
  end if;
  d := replace(d, o, $n$round(((ai->>'month_in_tok')::numeric * 0.30 + (ai->>'month_out_tok')::numeric * 2.50) / 1e6, 4)$n$);

  o := $o$'평소 월 1달러 미만(Haiku 5.5) — 반복 실행·요약 대상 급증 여부 확인 (수집 작업 로그의 AI 요약 표)'$o$;
  if (length(d) - length(replace(d, o, ''))) / length(o) <> 1 then
    raise exception 'system_alerts: ai_cost_high 안내 문구가 1곳이 아님';
  end if;
  execute replace(d, o, $n$'무료 등급 사용 중(유료 환산 기준 Gemini 3.5 Flash-Lite: 입력 $0.30·출력 $2.50) — 반복 실행·요약 대상 급증 여부 확인 (수집 작업 로그의 AI 요약 표)'$n$);
end $$;
