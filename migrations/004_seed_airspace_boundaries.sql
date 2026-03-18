-- 004_seed_airspace_boundaries.sql
-- Seed Columbus-area airspace boundaries (5 total).
-- Circles generated with ST_Buffer over geography for geodetic accuracy.
--
-- Sources: FAA JO 7400.11 (KCMH Class C), FAA Chart Supplement Great Lakes.
--
-- Boundaries:
--   1. KCMH Class C surface (SFC-4000 ft MSL, ~5 NM radius)
--   2. KCMH Class C outer shelf (1200-4000 ft MSL, ~10 NM radius)
--   3. KLCK Class D (SFC-2900 ft MSL, ~4.4 NM radius)
--   4. KOSU Class D (SFC-3200 ft MSL, ~4.4 NM radius)
--   5. KTZR Class D (SFC-3200 ft MSL, ~4.4 NM radius)

truncate airspace_boundaries restart identity;

insert into airspace_boundaries (name, class, floor_ft, ceiling_ft, geom)
select
    name,
    class,
    floor_ft,
    ceiling_ft,
    -- Buffer the center point by radius_m meters over geography, then cast to geometry(polygon)
    st_setsrid(
        st_buffer(
            st_makepoint(center_lon, center_lat)::geography,
            radius_m
        )::geometry,
        4326
    ) as geom
from (values
    -- KCMH Class C surface area: 5 NM radius around KCMH
    ('KCMH Class C Surface',   'C', 0,    4000, 39.997972, -82.891889,  9260.0),
    -- KCMH Class C outer shelf: 10 NM radius, 1200 ft floor
    ('KCMH Class C Shelf',     'C', 1200, 4000, 39.997972, -82.891889, 18520.0),
    -- KLCK Class D: ~4.4 NM radius
    ('KLCK Class D',           'D', 0,    2900, 39.813778, -82.927778,  8149.0),
    -- KOSU Class D: ~4.4 NM radius
    ('KOSU Class D',           'D', 0,    3200, 40.079800, -83.072800,  8149.0),
    -- KTZR Class D: ~4.4 NM radius
    ('KTZR Class D',           'D', 0,    3200, 39.901300, -83.136900,  8149.0)
) as t(name, class, floor_ft, ceiling_ft, center_lat, center_lon, radius_m);
