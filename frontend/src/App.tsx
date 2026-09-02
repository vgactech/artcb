import { HashRouter, Navigate, Route, Routes } from "react-router-dom";
import { DashboardProvider } from "./context/DashboardContext";
import { DashboardLayout } from "./layout/DashboardLayout";
import { AgentMemory } from "./pages/AgentMemory";
import { ApiKeys } from "./pages/ApiKeys";
import { ChainPage } from "./pages/ChainPage";
import { Console } from "./pages/Console";
import { GraphPage } from "./pages/GraphPage";
import { Groups } from "./pages/Groups";
import { Integrations } from "./pages/Integrations";
import { JoinGroup } from "./pages/JoinGroup";
import { Home } from "./pages/Home";
import { Governance } from "./pages/Governance";
import { Network } from "./pages/Network";
import { Logs } from "./pages/Logs";
import { Memorize } from "./pages/Memorize";
import { Mining } from "./pages/Mining";
import { SystemPage } from "./pages/SystemPage";
import { Wallets } from "./pages/Wallets";
import { RegisterBiometric } from "./pages/RegisterBiometric";

export default function App() {
  return (
    <DashboardProvider>
      <HashRouter>
        <Routes>
          <Route element={<DashboardLayout />}>
            <Route index element={<Home />} />
            <Route path="memorize" element={<Memorize />} />
            <Route path="graph" element={<GraphPage />} />
            <Route path="chain" element={<ChainPage />} />
            <Route path="chain/block/:blockIndex" element={<ChainPage />} />
            <Route path="wallets" element={<Wallets />} />
            <Route path="register" element={<RegisterBiometric />} />
            <Route path="mining" element={<Mining />} />
            <Route path="system" element={<SystemPage />} />
            <Route path="logs" element={<Logs />} />
            <Route path="console" element={<Console />} />
            <Route path="groups/join" element={<JoinGroup />} />
            <Route path="groups" element={<Groups />} />
            <Route path="integrations" element={<Integrations />} />
            <Route path="governance" element={<Governance />} />
            <Route path="network" element={<Network />} />
            <Route path="api-keys" element={<ApiKeys />} />
            <Route path="agent-memory" element={<AgentMemory />} />
            <Route path="demo" element={<Navigate to="/memorize" replace />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </HashRouter>
    </DashboardProvider>
  );
}
