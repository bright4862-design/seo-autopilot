begin;

select plan(10);

select ok(
  not has_table_privilege('anon', 'public.scanner_telemetry_v1', 'select,insert,update,delete'),
  'anon has no scanner telemetry privileges'
);
select ok(
  not has_table_privilege('authenticated', 'public.scanner_telemetry_v1', 'select,insert,update,delete'),
  'authenticated has no scanner telemetry privileges'
);
select ok(
  has_table_privilege('service_role', 'public.scanner_telemetry_v1', 'insert'),
  'service_role can insert scanner telemetry'
);
select ok(
  has_table_privilege('service_role', 'public.scanner_telemetry_v1', 'update'),
  'service_role can update scanner telemetry idempotently'
);

set local role anon;
select throws_ok(
  $$select * from public.scanner_telemetry_v1$$,
  '42501', null, 'anon cannot read scanner telemetry'
);
select throws_ok(
  $$insert into public.scanner_telemetry_v1 (scan_id, telemetry_version, outcome) values ('anon', 'v1', 'complete')$$,
  '42501', null, 'anon cannot insert scanner telemetry'
);
select throws_ok(
  $$update public.scanner_telemetry_v1 set outcome = 'failed' where scan_id = 'anon'$$,
  '42501', null, 'anon cannot update scanner telemetry'
);

set local role authenticated;
select throws_ok(
  $$select * from public.scanner_telemetry_v1$$,
  '42501', null, 'authenticated cannot read scanner telemetry'
);
select throws_ok(
  $$insert into public.scanner_telemetry_v1 (scan_id, telemetry_version, outcome) values ('authenticated', 'v1', 'complete')$$,
  '42501', null, 'authenticated cannot insert scanner telemetry'
);
select throws_ok(
  $$delete from public.scanner_telemetry_v1 where scan_id = 'authenticated'$$,
  '42501', null, 'authenticated cannot delete scanner telemetry'
);

select * from finish();
rollback;
