-- 005_seed_points_of_interest.sql
-- Seed Columbus-area points of interest (16 total).
--
-- Categories:
--   approach_fix    — final approach fix / outer marker reference
--   navaid          — VOR, NDB, or GPS waypoint
--   overflight_zone — notable surface area to monitor for overflights
--   traffic_pattern — airport traffic pattern reference point

truncate points_of_interest restart identity;

insert into points_of_interest (name, type, lat, lon, radius_nm, geom)
select
    name, type, lat, lon, radius_nm,
    st_setsrid(st_makepoint(lon, lat), 4326)
from (values
    -- KCMH approach fixes (4)
    ('KCMH Final 28R',         'approach_fix',    40.0105,  -83.0335,  2.0),
    ('KCMH Final 28L',         'approach_fix',    40.0068,  -83.0280,  2.0),
    ('KCMH Final 10L',         'approach_fix',    39.9930,  -82.7453,  2.0),
    ('KCMH Final 10R',         'approach_fix',    39.9895,  -82.7534,  2.0),

    -- KLCK approach fixes (2)
    ('KLCK Final 23R',         'approach_fix',    39.8545,  -82.9533,  2.0),
    ('KLCK Final 05L',         'approach_fix',    39.7931,  -82.8793,  2.0),

    -- KOSU and KTZR approach fixes (2)
    ('KOSU Final 27R',         'approach_fix',    40.0797,  -83.1600,  1.5),
    ('KTZR Final 22',          'approach_fix',    39.9167,  -83.1217,  1.5),

    -- Navigation aids (4)
    ('CMH VORTAC',             'navaid',          39.9980,  -82.8919,  1.0),
    ('Appleton VOR (APE)',     'navaid',          40.2597,  -82.5839,  1.0),
    ('Zanesville VOR (ZZV)',   'navaid',          39.9556,  -81.8922,  1.0),
    ('Falmouth VOR (FFT)',     'navaid',          38.5208,  -84.5425,  1.0),

    -- Overflight monitoring zones (4)
    ('Downtown Columbus',      'overflight_zone', 39.9612,  -82.9988,  3.0),
    ('OSU Main Campus',        'overflight_zone', 40.0076,  -83.0305,  2.0),
    ('Rickenbacker Cargo Ramp','overflight_zone', 39.8255,  -82.9327,  1.5),
    ('Bolton Field Pattern',   'overflight_zone', 39.9013,  -83.1369,  2.5)
) as t(name, type, lat, lon, radius_nm);
