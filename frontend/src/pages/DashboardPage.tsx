import styles from "./PlaceholderPage.module.css";

export function DashboardPage() {
  return (
    <div className={styles.page} data-testid="dashboard-page">
      <h1>Dashboard</h1>
      <p>Statistics panels and system health — coming in WU-05.</p>
    </div>
  );
}
