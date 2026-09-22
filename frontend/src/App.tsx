// R359 — séparation surface publique / interne
// Supprimé du frontend public : /reflex, /memorize, /logs
// R379 — Supprimé du frontend : /agent-memory (P2P IA), /network (P2P pairs + pool ML-KEM)
// R420 — Supprimé du frontend : /identity-test (BiometricIdentityTest — debug backend-only)
// Backend AgentMemory, P2P, Network, ReflexStatus, Logs, BiometricIdentityTest : API/agents uniquement
import { HashRouter, Navigate, Route, Routes } from "react-router-dom";
import { DashboardProvider } from "./context/DashboardContext";
import { DashboardLayout } from "./layout/DashboardLayout";
import { ApiKeys } from "./pages/ApiKeys";
import { ChainPage } from "./pages/ChainPage";
import { Console } from "./pages/Console";
import { GraphPage } from "./pages/GraphPage";
import { Groups } from "./pages/Groups";
import { Integrations } from "./pages/Integrations";
import { JoinGroup } from "./pages/JoinGroup";
import { Home } from "./pages/Home";
import { Governance } from "./pages/Governance";
import { Mining } from "./pages/Mining";
import { SystemPage } from "./pages/SystemPage";
import { Wallets } from "./pages/Wallets";
import { RegisterBiometric } from "./pages/RegisterBiometric";
import { AddDevice } from "./pages/AddDevice";

export default function App() {
  return (
    <DashboardProvider>
      <HashRouter>
        <Routes>
          <Route element={<DashboardLayout />}>
            <Route index element={<Home />} />
            <Route path="graph" element={<GraphPage />} />
            <Route path="chain" element={<ChainPage />} />
            <Route path="chain/block/:blockIndex" element={<ChainPage />} />
            <Route path="wallets" element={<Wallets />} />
            <Route path="register" element={<RegisterBiometric />} />
            <Route path="add-device" element={<AddDevice />} />
            <Route path="mining" element={<Mining />} />
            <Route path="system" element={<SystemPage />} />
            <Route path="console" element={<Console />} />
            <Route path="groups/join" element={<JoinGroup />} />
            <Route path="groups" element={<Groups />} />
            <Route path="integrations" element={<Integrations />} />
            <Route path="governance" element={<Governance />} />
            <Route path="api-keys" element={<ApiKeys />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </HashRouter>
    </DashboardProvider>
  );
}
