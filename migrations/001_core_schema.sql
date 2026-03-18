-- 001_core_schema.sql
-- Core tables: flight_sessions, position_reports (partitioned), pipeline_config,
-- materialization_log, and the config notification trigger.

-- ---------------------------------------------------------------------------
-- flight_sessions
-- ---------------------------------------------------------------------------
create table if not exists flight_sessions (
    session_id              uuid primary key default gen_random_uuid(),
    hex                     char(6) not null,
    callsign                varchar(10),
    started_at              timestamptz not null,
    ended_at                timestamptz,
    on_ground               boolean not null default false,
    departure_airport_icao  char(4),
    arrival_airport_icao    char(4),
    total_distance_nm       numeric(10,2),
    trajectory_geom         geometry(linestringz, 4326),
    created_at              timestamptz not null default now(),
    updated_at              timestamptz not null default now()
);

create index if not exists idx_flight_sessions_hex        on flight_sessions (hex);
create index if not exists idx_flight_sessions_started_at on flight_sessions (started_at desc);
create index if not exists idx_flight_sessions_ended_at   on flight_sessions (ended_at)
    where ended_at is not null;
create index if not exists idx_flight_sessions_callsign   on flight_sessions (callsign)
    where callsign is not null;

-- ---------------------------------------------------------------------------
-- position_reports  (range-partitioned by report_time)
-- ---------------------------------------------------------------------------
create table if not exists position_reports (
    report_id       bigserial,
    session_id      uuid not null,
    hex             char(6) not null,
    report_time     timestamptz not null,
    lat             numeric(10,6) not null,
    lon             numeric(10,6) not null,
    alt_ft          integer,
    track           numeric(5,1),
    speed_kts       integer,
    vrate_fpm       integer,
    phase           varchar(10),
    squawk          varchar(4),
    on_ground       boolean not null default false,
    category        varchar(4),
    geom            geometry(pointz, 4326)
) partition by range (report_time);

create index if not exists idx_position_reports_session_id  on position_reports (session_id);
create index if not exists idx_position_reports_hex         on position_reports (hex);
create index if not exists idx_position_reports_report_time on position_reports (report_time desc);

-- ---------------------------------------------------------------------------
-- pipeline_config
-- ---------------------------------------------------------------------------
create table if not exists pipeline_config (
    key         varchar(64) primary key,
    value       jsonb not null,
    updated_at  timestamptz not null default now()
);

-- Seed default configuration values
insert into pipeline_config (key, value) values
    ('session_gap_threshold_sec', '300'),
    ('batch_interval_sec',        '2'),
    ('phase_classification',      '{
        "ground_speed_max_kts":  50,
        "ground_alt_agl_max_ft": 200,
        "takeoff_vrate_min_fpm": 200,
        "climb_vrate_min_fpm":   200,
        "cruise_alt_min_ft":     18000,
        "descent_vrate_max_fpm": -200,
        "approach_alt_max_ft":   5000,
        "approach_speed_max_kts": 200,
        "landing_vrate_max_fpm": -100,
        "landing_alt_agl_max_ft": 100
    }'),
    ('retention_days', '60')
on conflict (key) do nothing;

-- ---------------------------------------------------------------------------
-- materialization_log
-- ---------------------------------------------------------------------------
create table if not exists materialization_log (
    session_id      uuid not null references flight_sessions (session_id),
    materialized_at timestamptz not null default now(),
    distance_nm     numeric(10,2),
    phase_summary   jsonb,
    primary key (session_id, materialized_at)
);

create index if not exists idx_materialization_log_session_id on materialization_log (session_id);

-- ---------------------------------------------------------------------------
-- config notification trigger
-- ---------------------------------------------------------------------------
create or replace function notify_config_changed()
returns trigger as $$
begin
    new.updated_at := now();
    perform pg_notify(
        'config_changed',
        json_build_object(
            'key',        new.key,
            'value',      new.value,
            'updated_at', new.updated_at
        )::text
    );
    return new;
end;
$$ language plpgsql;

drop trigger if exists trg_pipeline_config_changed on pipeline_config;
create trigger trg_pipeline_config_changed
before update on pipeline_config
for each row
execute function notify_config_changed();

-- also fire on insert so new keys added via API propagate immediately
drop trigger if exists trg_pipeline_config_inserted on pipeline_config;
create trigger trg_pipeline_config_inserted
before insert on pipeline_config
for each row
execute function notify_config_changed();
