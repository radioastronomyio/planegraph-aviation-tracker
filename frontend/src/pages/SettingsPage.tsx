import { useCallback, useEffect, useRef, useState } from "react";
import styles from "./SettingsPage.module.css";

interface ConfigEntry {
  key: string;
  value: unknown;
  updated_at: string;
}

type FieldState = "idle" | "saving" | "saved" | "error";
type ConfigMap = Record<string, unknown>;

interface PhaseClassification {
  ground_speed_max_kts: number;
  ground_alt_agl_max_ft: number;
  takeoff_vrate_min_fpm: number;
  climb_vrate_min_fpm: number;
  cruise_alt_min_ft: number;
  descent_vrate_max_fpm: number;
  approach_alt_max_ft: number;
  approach_speed_max_kts: number;
  landing_vrate_max_fpm: number;
  landing_alt_agl_max_ft: number;
}

const PHASE_FIELDS: [keyof PhaseClassification, string][] = [
  ["ground_speed_max_kts", "Ground speed max (kts)"],
  ["ground_alt_agl_max_ft", "Ground altitude AGL max (ft)"],
  ["takeoff_vrate_min_fpm", "Takeoff vertical rate min (fpm)"],
  ["climb_vrate_min_fpm", "Climb vertical rate min (fpm)"],
  ["cruise_alt_min_ft", "Cruise altitude min (ft)"],
  ["descent_vrate_max_fpm", "Descent vertical rate max (fpm)"],
  ["approach_alt_max_ft", "Approach altitude max (ft)"],
  ["approach_speed_max_kts", "Approach speed max (kts)"],
  ["landing_vrate_max_fpm", "Landing vertical rate max (fpm)"],
  ["landing_alt_agl_max_ft", "Landing altitude AGL max (ft)"],
];

function FieldStatus({ state }: { state: FieldState }) {
  if (state === "idle") return null;
  const cls =
    state === "saved"
      ? styles.statusSaved
      : state === "error"
        ? styles.statusError
        : styles.statusSaving;
  const text =
    state === "saved" ? "saved" : state === "error" ? "error" : "saving…";
  return <span className={cls}>{text}</span>;
}

function NumericField({
  label,
  value,
  state,
  onChange,
}: {
  label: string;
  value: number | undefined;
  state: FieldState;
  onChange: (v: number) => void;
}) {
  return (
    <div className={styles.field}>
      <label className={styles.label}>{label}</label>
      <input
        type="number"
        className={styles.input}
        value={value ?? ""}
        onChange={(e) => {
          const raw = e.target.value;
          if (raw === "") return;
          const n = Number(raw);
          if (!Number.isNaN(n)) onChange(n);
        }}
      />
      <FieldStatus state={state} />
    </div>
  );
}

function ToggleField({
  label,
  value,
  state,
  onChange,
}: {
  label: string;
  value: boolean;
  state: FieldState;
  onChange: (v: boolean) => void;
}) {
  return (
    <div className={styles.field}>
      <label className={styles.label}>{label}</label>
      <input
        type="checkbox"
        className={styles.checkbox}
        checked={value}
        onChange={(e) => onChange(e.target.checked)}
      />
      <FieldStatus state={state} />
    </div>
  );
}

export function SettingsPage() {
  const [config, setConfig] = useState<ConfigMap>({});
  const [fieldState, setFieldState] = useState<Record<string, FieldState>>({});
  const [loadError, setLoadError] = useState<string | null>(null);
  const timers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});

  useEffect(() => {
    fetch("/api/v1/config")
      .then((r) => r.json())
      .then((entries: ConfigEntry[]) => {
        const map: ConfigMap = {};
        for (const e of entries) map[e.key] = e.value;
        setConfig(map);
      })
      .catch((e: unknown) => setLoadError(String(e)));

    return () => {
      Object.values(timers.current).forEach(clearTimeout);
    };
  }, []);

  const patch = useCallback((key: string, value: unknown) => {
    setConfig((prev) => ({ ...prev, [key]: value }));
    if (timers.current[key]) clearTimeout(timers.current[key]);
    timers.current[key] = setTimeout(async () => {
      setFieldState((prev) => ({ ...prev, [key]: "saving" }));
      try {
        const res = await fetch(`/api/v1/config/${encodeURIComponent(key)}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ value }),
        });
        if (!res.ok) {
          const msg = await res.text();
          throw new Error(msg);
        }
        setFieldState((prev) => ({ ...prev, [key]: "saved" }));
        setTimeout(
          () => setFieldState((prev) => ({ ...prev, [key]: "idle" })),
          2000,
        );
      } catch {
        setFieldState((prev) => ({ ...prev, [key]: "error" }));
      }
    }, 500);
  }, []);

  const patchPhaseField = useCallback(
    (field: keyof PhaseClassification, value: number) => {
      setConfig((prev) => {
        const current =
          (prev.phase_classification as PhaseClassification) ?? {};
        const merged = { ...current, [field]: value };
        patch("phase_classification", merged);
        return { ...prev, phase_classification: merged };
      });
    },
    [patch],
  );

  if (loadError) {
    return (
      <div className={styles.page} data-testid="settings-page">
        <h1>Settings</h1>
        <p className={styles.errorMsg}>Failed to load settings: {loadError}</p>
      </div>
    );
  }

  const phase = (config.phase_classification as PhaseClassification) ?? {};

  return (
    <div className={styles.page} data-testid="settings-page">
      <h1>Settings</h1>

      <section className={styles.section}>
        <h2>Ingest</h2>
        <NumericField
          label="Session gap threshold (sec)"
          value={config.session_gap_threshold_sec as number}
          state={fieldState.session_gap_threshold_sec ?? "idle"}
          onChange={(v) => patch("session_gap_threshold_sec", v)}
        />
        <NumericField
          label="Ground turnaround threshold (sec)"
          value={config.ground_turnaround_threshold_sec as number}
          state={fieldState.ground_turnaround_threshold_sec ?? "idle"}
          onChange={(v) => patch("ground_turnaround_threshold_sec", v)}
        />
        <NumericField
          label="Batch interval (sec)"
          value={config.batch_interval_sec as number}
          state={fieldState.batch_interval_sec ?? "idle"}
          onChange={(v) => patch("batch_interval_sec", v)}
        />
      </section>

      <section className={styles.section}>
        <h2>Data Retention</h2>
        <NumericField
          label="Retention days"
          value={config.retention_days as number}
          state={fieldState.retention_days ?? "idle"}
          onChange={(v) => patch("retention_days", v)}
        />
      </section>

      <section className={styles.section}>
        <h2>Phase Classification</h2>
        {PHASE_FIELDS.map(([field, label]) => (
          <NumericField
            key={field}
            label={label}
            value={phase[field]}
            state={fieldState.phase_classification ?? "idle"}
            onChange={(v) => patchPhaseField(field, v)}
          />
        ))}
      </section>

      <section className={styles.section}>
        <h2>Visibility</h2>
        {"geofence_visible" in config && (
          <ToggleField
            label="Show geofence boundaries"
            value={config.geofence_visible as boolean}
            state={fieldState.geofence_visible ?? "idle"}
            onChange={(v) => patch("geofence_visible", v)}
          />
        )}
        {"poi_monitoring_enabled" in config && (
          <ToggleField
            label="Enable POI monitoring"
            value={config.poi_monitoring_enabled as boolean}
            state={fieldState.poi_monitoring_enabled ?? "idle"}
            onChange={(v) => patch("poi_monitoring_enabled", v)}
          />
        )}
      </section>
    </div>
  );
}
