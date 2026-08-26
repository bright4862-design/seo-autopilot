create table if not exists public.scanner_telemetry_v1 (
  scan_id text primary key check (char_length(scan_id) between 1 and 200),
  telemetry_version text not null,
  outcome text not null,
  scanner_version text not null default '',
  scanner_build_revision text not null default '',
  scan_mode text not null default 'unknown',
  scanner_elapsed_ms bigint not null default 0 check (scanner_elapsed_ms >= 0),
  scan_deadline_reached boolean not null default false,
  pages_crawled integer not null default 0 check (pages_crawled >= 0),
  pages_found integer not null default 0 check (pages_found >= 0),
  health_score integer check (health_score between 0 and 100),
  page_type_counts jsonb not null default '{}'::jsonb check (jsonb_typeof(page_type_counts) = 'object'),
  response_class_counts jsonb not null default '{}'::jsonb check (jsonb_typeof(response_class_counts) = 'object'),
  failure_reason_counts jsonb not null default '{}'::jsonb check (jsonb_typeof(failure_reason_counts) = 'object'),
  issue_counts jsonb not null default '{}'::jsonb check (jsonb_typeof(issue_counts) = 'object'),
  sampling_decisions jsonb not null default '{}'::jsonb check (jsonb_typeof(sampling_decisions) = 'object'),
  recorded_at timestamptz not null default now()
);

comment on table public.scanner_telemetry_v1 is
  'Server-written, aggregate-only FixList scanner telemetry. No URLs, HTML, customer identity, credentials, or authority evidence.';

alter table public.scanner_telemetry_v1 enable row level security;

revoke all on table public.scanner_telemetry_v1 from anon, authenticated;
grant insert, update on table public.scanner_telemetry_v1 to service_role;
