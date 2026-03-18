-- 002_reference_geometry_schema.sql
-- Reference geometry tables: airports, runways, airspace_boundaries, points_of_interest.

-- ---------------------------------------------------------------------------
-- airports
-- ---------------------------------------------------------------------------
create table if not exists airports (
    icao                char(4) primary key,
    name                varchar(100) not null,
    city                varchar(60),
    lat                 numeric(10,6) not null,
    lon                 numeric(10,6) not null,
    elevation_ft        integer not null,
    geom                geometry(point, 4326)
);

create index if not exists idx_airports_geom on airports using gist (geom);

-- ---------------------------------------------------------------------------
-- runways
-- ---------------------------------------------------------------------------
create table if not exists runways (
    runway_id               serial primary key,
    airport_icao            char(4) not null references airports (icao),
    designator              varchar(5) not null,
    heading_true            numeric(5,1) not null,
    threshold_lat           numeric(10,6) not null,
    threshold_lon           numeric(10,6) not null,
    threshold_elevation_ft  integer not null,
    threshold_geom          geometry(point, 4326),
    extended_centerline_geom geometry(linestring, 4326),
    unique (airport_icao, designator)
);

create index if not exists idx_runways_airport_icao on runways (airport_icao);
create index if not exists idx_runways_geom          on runways using gist (threshold_geom);
create index if not exists idx_runways_centerline    on runways using gist (extended_centerline_geom);

-- ---------------------------------------------------------------------------
-- airspace_boundaries
-- ---------------------------------------------------------------------------
create table if not exists airspace_boundaries (
    boundary_id serial primary key,
    name        varchar(100) not null,
    class       varchar(10) not null,
    floor_ft    integer not null,
    ceiling_ft  integer not null,
    geom        geometry(polygon, 4326)
);

create index if not exists idx_airspace_boundaries_geom on airspace_boundaries using gist (geom);

-- ---------------------------------------------------------------------------
-- points_of_interest
-- ---------------------------------------------------------------------------
create table if not exists points_of_interest (
    poi_id      serial primary key,
    name        varchar(100) not null,
    type        varchar(50) not null,
    lat         numeric(10,6) not null,
    lon         numeric(10,6) not null,
    radius_nm   numeric(4,1) not null default 1.0,
    geom        geometry(point, 4326)
);

create index if not exists idx_poi_geom on points_of_interest using gist (geom);
