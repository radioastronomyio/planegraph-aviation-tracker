import { BrowserRouter, Routes, Route } from "react-router-dom";
import { NavBar } from "./components/NavBar";
import { MapPage } from "./pages/MapPage";
import { DashboardPage } from "./pages/DashboardPage";
import { SettingsPage } from "./pages/SettingsPage";
import styles from "./App.module.css";

function App() {
  return (
    <BrowserRouter>
      <div className={styles.layout}>
        <NavBar />
        <main className={styles.main}>
          <Routes>
            <Route path="/" element={<MapPage />} />
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}

export default App;
