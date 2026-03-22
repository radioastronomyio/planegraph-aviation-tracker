import { NavLink } from "react-router-dom";
import { useAircraftStore } from "../store/aircraftStore";
import styles from "./NavBar.module.css";

export function NavBar() {
  const connected = useAircraftStore((s) => s.connected);
  const count = useAircraftStore((s) => Object.keys(s.aircraft).length);

  return (
    <nav className={styles.nav} data-testid="navbar">
      <span className={styles.brand}>✈ Planegraph</span>
      <div className={styles.links}>
        <NavLink to="/" end className={({ isActive }) => isActive ? styles.active : ""}>
          Map
        </NavLink>
        <NavLink to="/dashboard" className={({ isActive }) => isActive ? styles.active : ""}>
          Dashboard
        </NavLink>
        <NavLink to="/settings" className={({ isActive }) => isActive ? styles.active : ""}>
          Settings
        </NavLink>
      </div>
      <div className={styles.status}>
        <span
          className={connected ? styles.dotConnected : styles.dotDisconnected}
          data-testid="ws-status"
          data-connected={connected}
        />
        <span data-testid="aircraft-count">{count} aircraft</span>
      </div>
    </nav>
  );
}
