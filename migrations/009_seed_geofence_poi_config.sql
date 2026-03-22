-- 009_seed_geofence_poi_config.sql
-- Seed UI-level visibility toggles into pipeline_config so the
-- settings page can read and write them via PATCH /api/v1/config/{key}.

insert into pipeline_config (key, value) values
    ('geofence_visible',       'true'),
    ('poi_monitoring_enabled', 'true')
on conflict (key) do nothing;
