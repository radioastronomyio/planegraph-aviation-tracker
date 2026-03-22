import { BrowserRouter, Routes, Route } from "react-router-dom";
import { NavBar } from "./components/NavBar";
import { MapPage } from "./pages/MapPage";
import { DashboardPage } from "./pages/DashboardPage";
import { SettingsPage } from "./pages/SettingsPage";
import { FlightsPage } from "./pages/FlightsPage";
import { FlightDetailPage } from "./pages/FlightDetailPage";
import { ApproachPage } from "./pages/ApproachPage";
import { HeatmapPage } from "./pages/HeatmapPage";
import { AirportsPage } from "./pages/AirportsPage";
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
            <Route path="/flights" element={<FlightsPage />} />
            <Route path="/flights/:sessionId" element={<FlightDetailPage />} />
            <Route path="/flights/:sessionId/approach" element={<ApproachPage />} />
            <Route path="/analytics/heatmap" element={<HeatmapPage />} />
            <Route path="/analytics/airports" element={<AirportsPage />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}

export default App;
