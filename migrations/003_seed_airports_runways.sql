-- 003_seed_airports_runways.sql
-- Seed Columbus-area airports and runways.
-- Runway threshold coordinates derived from GDR-03 catalog.
-- Extended centerlines (15 NM = 27780 m) generated via ST_Project over geography.

-- ---------------------------------------------------------------------------
-- airports (4 total)
-- ---------------------------------------------------------------------------
insert into airports (icao, name, city, lat, lon, elevation_ft, geom) values
    ('KCMH', 'John Glenn Columbus International Airport', 'Columbus',  39.997972, -82.891889, 815,  st_setsrid(st_makepoint(-82.891889, 39.997972), 4326)),
    ('KLCK', 'Rickenbacker International Airport',       'Columbus',  39.813778, -82.927778, 744,  st_setsrid(st_makepoint(-82.927778, 39.813778), 4326)),
    ('KOSU', 'The Ohio State University Airport',        'Columbus',  40.079800, -83.072800, 905,  st_setsrid(st_makepoint(-83.072800, 40.079800), 4326)),
    ('KTZR', 'Bolton Field',                             'Columbus',  39.901300, -83.136900, 905,  st_setsrid(st_makepoint(-83.136900, 39.901300), 4326))
on conflict (icao) do nothing;

-- ---------------------------------------------------------------------------
-- runways (16 total — 4 per airport, each threshold is a separate row)
--
-- Approach heading = (heading_true + 180) % 360
-- Extended centerline: from threshold, projecting 27780 m in approach direction.
-- ---------------------------------------------------------------------------
insert into runways (
    airport_icao, designator, heading_true,
    threshold_lat, threshold_lon, threshold_elevation_ft,
    threshold_geom, extended_centerline_geom
)
select
    airport_icao,
    designator,
    heading_true,
    threshold_lat,
    threshold_lon,
    threshold_elevation_ft,
    st_setsrid(st_makepoint(threshold_lon, threshold_lat), 4326) as threshold_geom,
    st_makeline(
        st_setsrid(st_makepoint(threshold_lon, threshold_lat), 4326),
        st_setsrid(
            st_project(
                st_setsrid(st_makepoint(threshold_lon, threshold_lat), 4326)::geography,
                27780.0,
                radians(mod((heading_true + 180.0)::numeric, 360.0)::float)
            )::geometry,
            4326
        )
    ) as extended_centerline_geom
from (values
    -- KCMH (John Glenn Columbus International) — runways 10L/28R and 10R/28L
    ('KCMH', '10L',  104.0, 39.997778, -82.937400, 815),
    ('KCMH', '28R',  284.0, 40.002472, -82.861111, 810),
    ('KCMH', '10R',  104.0, 39.994583, -82.928056, 815),
    ('KCMH', '28L',  284.0, 39.998694, -82.867306, 810),

    -- KLCK (Rickenbacker International) — runways 05L/23R and 05R/23L
    ('KLCK', '05L',   53.0, 39.813806, -82.955889, 744),
    ('KLCK', '23R',  233.0, 39.835778, -82.911333, 744),
    ('KLCK', '05R',   53.0, 39.810806, -82.951806, 744),
    ('KLCK', '23L',  233.0, 39.833944, -82.910556, 744),

    -- KOSU (Ohio State University Airport) — runways 09L/27R and 09R/27L
    ('KOSU', '09L',   90.0, 40.080278, -83.103472, 905),
    ('KOSU', '27R',  270.0, 40.079583, -83.043194, 905),
    ('KOSU', '09R',   90.0, 40.078861, -83.100972, 905),
    ('KOSU', '27L',  270.0, 40.078306, -83.043861, 905),

    -- KTZR (Bolton Field) — runways 04/22 and 13/31
    ('KTZR', '04',    40.0, 39.898972, -83.137833, 905),
    ('KTZR', '22',   220.0, 39.907389, -83.129972, 905),
    ('KTZR', '13',   130.0, 39.910056, -83.141528, 905),
    ('KTZR', '31',   310.0, 39.895917, -83.124861, 905)
) as t(airport_icao, designator, heading_true, threshold_lat, threshold_lon, threshold_elevation_ft)
on conflict (airport_icao, designator) do nothing;
