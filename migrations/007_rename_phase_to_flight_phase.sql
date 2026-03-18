-- 007_rename_phase_to_flight_phase.sql
-- Rename position_reports.phase to flight_phase for consistency with
-- the API and acceptance criteria in WU-02.
-- Partitioned tables in PostgreSQL cascade column renames to all children.

alter table position_reports rename column phase to flight_phase;
