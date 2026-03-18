-- 006_partition_management.sql
-- Partition management functions for position_reports.
-- Creates daily child partitions named position_reports_YYYYMMDD.
-- Bootstrap creates today + 3 future UTC days.
-- Ongoing scheduling is handled by the Python scheduler in WU-02.

-- ---------------------------------------------------------------------------
-- create_daily_partition(target_date)
-- Creates a single day partition for position_reports if it does not already exist.
-- ---------------------------------------------------------------------------
create or replace function create_daily_partition(target_date date)
returns void as $$
declare
    partition_name text;
    start_ts       timestamptz;
    end_ts         timestamptz;
begin
    partition_name := 'position_reports_' || to_char(target_date, 'YYYYMMDD');
    start_ts       := target_date::timestamptz at time zone 'UTC';
    end_ts         := (target_date + interval '1 day')::timestamptz at time zone 'UTC';

    if not exists (
        select 1
        from   pg_class c
        join   pg_namespace n on n.oid = c.relnamespace
        where  c.relname = partition_name
        and    n.nspname = 'public'
    ) then
        execute format(
            'create table %I partition of position_reports '
            'for values from (%L) to (%L)',
            partition_name,
            start_ts,
            end_ts
        );
        raise notice 'created partition: %', partition_name;
    else
        raise notice 'partition already exists: %', partition_name;
    end if;
end;
$$ language plpgsql;

-- ---------------------------------------------------------------------------
-- drop_expired_partitions()
-- Drops partitions whose data range falls entirely before
-- now() - retention_days (from pipeline_config).
-- ---------------------------------------------------------------------------
create or replace function drop_expired_partitions()
returns void as $$
declare
    retention      int;
    cutoff_date    date;
    rec            record;
    partition_date date;
begin
    select (value::text)::int
    into   retention
    from   pipeline_config
    where  key = 'retention_days';

    if retention is null then
        retention := 60;
    end if;

    cutoff_date := (current_date - retention)::date;

    for rec in
        select c.relname as partition_name
        from   pg_inherits i
        join   pg_class c on c.oid = i.inhrelid
        join   pg_class p on p.oid = i.inhparent
        where  p.relname = 'position_reports'
    loop
        -- partition name format: position_reports_YYYYMMDD
        begin
            partition_date := to_date(
                right(rec.partition_name, 8),
                'YYYYMMDD'
            );
        exception when others then
            continue;
        end;

        if partition_date < cutoff_date then
            execute format('drop table if exists %I', rec.partition_name);
            raise notice 'dropped expired partition: %', rec.partition_name;
        end if;
    end loop;
end;
$$ language plpgsql;

-- ---------------------------------------------------------------------------
-- Bootstrap: create partitions for today and the next 3 UTC days.
-- ---------------------------------------------------------------------------
select create_daily_partition(current_date);
select create_daily_partition(current_date + 1);
select create_daily_partition(current_date + 2);
select create_daily_partition(current_date + 3);
