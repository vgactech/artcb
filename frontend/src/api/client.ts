import axios from "axios";
import type { IRGraph, PolMetrics, ChainBlock } from "../types";

const api = axios.create({ baseURL: "/api/v1" });

/** R345 — stable browser device id (not HumanIdentity; not server host FP). */
const DEVICE_ID_KEY = "artcb_device_id";

function ensureClientDeviceId(): string {
  try {
    let id = localStorage.getItem(DEVICE_ID_KEY);
    if (!id || id.length < 8) {
      id =
        typeof crypto !== "undefined" && "randomUUID" in crypto
          ? crypto.randomUUID()
          : `dev_${Math.random().toString(36).slice(2)}${Date.now().toString(36)}`;
      localStorage.setItem(DEVICE_ID_KEY, id);
    }
    return id;
  } catch {
    return "anonymous";
  }
}

api.interceptors.request.use((config) => {
  config.headers = config.headers ?? {};
  config.headers["X-ARTCB-Device-Id"] = ensureClientDeviceId();
  return config;
});

export async function fetchWaillyExcerpt(maxPages = 3): Promise<string> {
  const { data } = await api.get<{ text: string }>("/demo/wailly-excerpt", {
    params: { max_pages: maxPages },
  });
  return data.text;
}

export async function runAgents(
  text: string,
  sessionId: string,
  useLlm = false,
  llmProvider?: string,
) {
  const { data } = await api.post("/agents/run", {
    text,
    session_id: sessionId,
    use_llm: useLlm,
    llm_provider: llmProvider,
  });
  return data as {
    graph_id: string;
    pol: PolMetrics;
    node_count: number;
  };
}

export async function fetchGraph(graphId: string): Promise<IRGraph> {
  const { data } = await api.get(`/graph/${graphId}`);
  return {
    graph_id: data.graph_id,
    source_text: data.source_text,
    nodes: data.nodes,
    edges: data.edges.map((e: { fr?: string; from?: string; to: string; rel: string }) => ({
      from: e.fr ?? e.from,
      to: e.to,
      rel: e.rel,
    })),
  };
}

export async function searchNodes(query: string, graphId: string) {
  const { data } = await api.post("/search", { query, graph_id: graphId, top_k: 3 });
  return data.results as Array<{ node_id: string; score: number; text: string }>;
}

export async function decodeGraph(graphId: string) {
  const { data } = await api.post("/decode", { graph_id: graphId });
  return data as { original_text: string; similarity: number; reversible: boolean };
}

export async function storeGraph(
  graphId: string,
  sessionId: string,
  visibility: "private" | "group" | "public" = "private",
  groupId?: string | null,
  actorAddress?: string | null,
) {
  const { data } = await api.post("/store", {
    graph_id: graphId,
    session_id: sessionId,
    visibility,
    group_id: groupId ?? undefined,
    actor_address: actorAddress ?? undefined,
  });
  return data as {
    block_index: number;
    hash: string;
    signature: string;
    pol_score: number;
    block_reward?: number;
  };
}

export async function fetchWallets() {
  const { data } = await api.get("/wallet/list", { headers: sessionHeaders() });
  return data.wallets as Array<{ address: string; name: string }>;
}

export async function fetchWalletBalance(address: string) {
  const { data } = await api.get(`/wallet/balance/${address}`, { headers: sessionHeaders() });
  return data as { balance_satoshi: number; balance_artcb: number };
}

export interface GroupData {
  group_id: string;
  name: string;
  founder_address: string;
  created_at: string;
  join_code?: string;
  dissolved: boolean;
  members: Array<{ address: string; role: string; joined_at: string }>;
}

function sessionHeaders(): Record<string, string> {
  // R318: session lives in sessionStorage (Wallets/WebAuthn). Prefer it.
  // ~~localStorage-only~~ caused ghost "logged in" after tab restore mismatches.
  let token: string | null = null;
  if (typeof sessionStorage !== "undefined") {
    token = sessionStorage.getItem("artcb_session_token");
  }
  if (!token && typeof localStorage !== "undefined") {
    token = localStorage.getItem("artcb_session_token");
    // Migrate legacy localStorage → sessionStorage once, then clear local.
    if (token && typeof sessionStorage !== "undefined") {
      sessionStorage.setItem("artcb_session_token", token);
      try {
        localStorage.removeItem("artcb_session_token");
      } catch {
        /* ignore */
      }
    }
  }
  if (!token) return {};
  return { Authorization: `Bearer ${token}` };
}

export async function authMe() {
  const { data } = await api.get("/auth/me", { headers: sessionHeaders() });
  return data as {
    authenticated: boolean;
    kind: string;
    address: string | null;
    wallet_name?: string | null;
    is_user?: boolean;
    is_operator?: boolean;
  };
}

export async function createGroup(name: string, founderAddress: string) {
  const { data } = await api.post(
    "/groups",
    { name, founder_address: founderAddress },
    { headers: sessionHeaders() },
  );
  return data as GroupData;
}

export type DomainManifestView = {
  domain_id: string;
  domain_type: string;
  subject_id: string;
  founder_address: string;
  genesis_hash: string;
  hosting_node_id: string;
  authorized_nodes: string[];
  storage_mode: string;
  recovery_enabled: boolean;
  min_replicas: number;
  node_owns_domain: boolean;
  body_replicated: boolean;
  commitment_anchored_on_chain: boolean;
  projection: string;
};

export type OrgCreated = {
  organization_id: string;
  name: string;
  founder_address: string;
  content_hash: string;
  domain: DomainManifestView;
  authority?: {
    controller_address: string;
    legal_owner: string;
    founder_address: string;
    unique_human_proven: boolean;
  };
  ownership: {
    founder_address: string;
    controller_address?: string;
    legal_owner?: string;
    hosting_node_id: string;
    node_owns_domain: boolean;
    cest_a_dire: string;
  };
};

export async function createOrganization(
  name: string,
  storageMode = "artcb_managed",
  authorizedNodes: string[] = [],
) {
  const { data } = await api.post(
    "/authz/orgs",
    { name, storage_mode: storageMode, authorized_nodes: authorizedNodes },
    { headers: sessionHeaders() },
  );
  return data as OrgCreated;
}

export async function fetchDomains() {
  const { data } = await api.get("/authz/domains");
  return data as { domains: DomainManifestView[]; count: number; node_owns_domain: boolean };
}

export async function locateDomain(domainId: string) {
  const { data } = await api.get(`/authz/domains/${domainId}/locate`);
  return data as DomainManifestView & { hosted_here: boolean; this_node: string; route: string };
}

export async function exportDomain(domainId: string) {
  const { data } = await api.post(`/authz/domains/${domainId}/export`, {}, { headers: sessionHeaders() });
  return data as Record<string, unknown>;
}

export async function proposeOrgTransfer(
  organizationId: string,
  newController: string,
  reason = "DIRECTOR_CHANGE",
) {
  const { data } = await api.post(
    `/authz/orgs/${organizationId}/transfer`,
    { new_controller: newController, reason },
    { headers: sessionHeaders() },
  );
  return data as { tx_id: string; status: string; org_id_unchanged: boolean };
}

export async function acceptTransfer(txId: string) {
  const { data } = await api.post(
    "/authz/transfers/accept",
    { tx_id: txId },
    { headers: sessionHeaders() },
  );
  return data as { status: string; authority: Record<string, unknown> };
}

export async function fetchOrgAuthority(organizationId: string) {
  const { data } = await api.get(`/authz/orgs/${organizationId}/authority`);
  return data as {
    controller_address: string;
    legal_owner: string;
    founder_address: string;
    unique_human_proven: boolean;
  };
}

export async function proposeGroupTransfer(
  groupId: string,
  newController: string,
  reason = "DIRECTOR_CHANGE",
) {
  const { data } = await api.post(
    `/authz/groups/${groupId}/transfer`,
    { new_controller: newController, reason },
    { headers: sessionHeaders() },
  );
  return data as { tx_id: string; status: string; parent_unchanged: boolean };
}

export async function cancelTransfer(txId: string) {
  const { data } = await api.post(
    "/authz/transfers/cancel",
    { tx_id: txId },
    { headers: sessionHeaders() },
  );
  return data as { status: string };
}

export async function declineTransfer(txId: string) {
  const { data } = await api.post(
    "/authz/transfers/decline",
    { tx_id: txId },
    { headers: sessionHeaders() },
  );
  return data as { status: string };
}

export async function importDomain(bundle: Record<string, unknown>) {
  const { data } = await api.post(
    "/authz/domains/import",
    { bundle },
    { headers: sessionHeaders() },
  );
  return data as { imported: boolean; domain: DomainManifestView };
}

export async function fetchGroupsForAddress(address: string) {
  const { data } = await api.get("/groups", { params: { address } });
  return data as { groups: GroupData[]; count: number };
}

export async function fetchGroupByJoinCode(joinCode: string) {
  const { data } = await api.get(`/groups/by-code/${joinCode}`);
  return data as { group_id: string; name: string; join_code: string; member_count: number };
}

export async function signJoinWithWallet(walletName: string, joinCode: string) {
  const { data } = await api.post("/groups/join-requests/sign-with-wallet", {
    wallet_name: walletName,
    join_code: joinCode,
  });
  return data as {
    message: string;
    request: { request_id: string; address: string; status: string };
  };
}

export async function fetchJoinRequests(groupId: string, actorAddress: string, status?: string) {
  const { data } = await api.get(`/groups/${groupId}/join-requests`, {
    params: { actor_address: actorAddress, status },
  });
  return data as {
    requests: Array<{
      request_id: string;
      address: string;
      status: string;
      created_at: string;
    }>;
    count: number;
  };
}

export async function approveJoinRequest(groupId: string, actorAddress: string, requestId: string) {
  const { data } = await api.post(`/groups/${groupId}/join-requests/${requestId}/approve`, {
    actor_address: actorAddress,
  });
  return data;
}

export async function rejectJoinRequest(groupId: string, actorAddress: string, requestId: string) {
  const { data } = await api.post(`/groups/${groupId}/join-requests/${requestId}/reject`, {
    actor_address: actorAddress,
  });
  return data;
}

export async function inviteGroupMember(
  groupId: string,
  actorAddress: string,
  address: string,
  role: string = "contributor",
) {
  const { data } = await api.post(`/groups/${groupId}/members`, {
    actor_address: actorAddress,
    address,
    role,
  });
  return data as GroupData;
}

export async function promoteGroupMember(
  groupId: string,
  actorAddress: string,
  targetAddress: string,
  role: string,
) {
  const { data } = await api.post(`/groups/${groupId}/members/${targetAddress}/role`, {
    actor_address: actorAddress,
    role,
  });
  return data as GroupData;
}

export async function fetchRtlegEvents() {
  const { data } = await api.get("/rtleg/events");
  return data.events as Array<{
    event_id: string;
    timestamp: string;
    session_id: string;
    agent: string;
    event_type: string;
    payload?: Record<string, unknown>;
  }>;
}

export async function fetchChain(params?: {
  visibility?: string;
  groupId?: string;
}): Promise<ChainBlock[]> {
  const { data } = await api.get("/chain", {
    params: {
      visibility: params?.visibility,
      group_id: params?.groupId,
    },
  });
  return data.blocks as ChainBlock[];
}

export async function createWallet(name: string, password: string) {
  const { data } = await api.post("/wallet/create", { name, password });
  return data as {
    name: string;
    address: string;
    address_v2?: string;
    public_key_hex: string;
    public_key_b64: string;
    /** Clé privée (seed Ed25519, 32 bytes en hex). Affichée UNE SEULE FOIS. */
    seed_hex: string;
    WARNING: string;
    hybrid: boolean;
  };
}

// Auth endpoints
export async function authLogin(name: string, password: string) {
  const { data } = await api.post("/auth/login", { name, password });
  return data as { session_token: string; wallet_name: string; address: string; expires_in: number };
}

export async function authChallenge() {
  const { data } = await api.get("/auth/challenge");
  return data as { challenge: string; expires_in: number };
}

export async function authVerify(address: string, challenge: string, signature: string) {
  const { data } = await api.post("/auth/verify", { address, challenge, signature });
  return data as { session_token: string; wallet_name: string; address: string; expires_in: number };
}

export async function authLogout(sessionToken: string) {
  await api.post("/auth/logout", {}, { headers: { Authorization: `Bearer ${sessionToken}` } });
}

export type WebAuthnPublicKey = Record<string, unknown>;

export async function webauthnRegisterOptions(name: string, modality: "fingerprint" | "face" | "both", createWallet = true) {
  const { data } = await api.post("/auth/webauthn/register/options", {
    name,
    modality,
    create_wallet: createWallet,
  });
  return data as {
    publicKey: WebAuthnPublicKey;
    create_wallet: boolean;
    raw_biometric_never_stored: boolean;
    modality: string;
    next_modality?: string | null;
  };
}

export async function webauthnRegisterVerify(
  name: string,
  modality: "fingerprint" | "face" | "both",
  credential: unknown,
  createWallet = true,
) {
  const { data } = await api.post("/auth/webauthn/register/verify", {
    name,
    modality,
    credential,
    create_wallet: createWallet,
  });
  return data as {
    ok: boolean;
    session_token: string;
    wallet_name: string;
    address: string;
    expires_in: number;
    seed_hex?: string;
    WARNING?: string;
    wallet_created: boolean;
    enrolled: string;
  };
}

export async function webauthnLoginOptions(name: string, modality?: "fingerprint" | "face") {
  try {
    const { data } = await api.post("/auth/webauthn/login/options", { name, modality });
    return data as { publicKey: WebAuthnPublicKey };
  } catch (err: unknown) {
    // R385: distinguish wallet_unknown (404) from service unavailable (503/502/network)
    const ax = err as { response?: { status?: number; data?: { detail?: string } } };
    const status = ax?.response?.status;
    const detail = ax?.response?.data?.detail;
    if (status === 404 && detail === "wallet_unknown") {
      // Wallet exists only on another node — clear diagnostic, not a generic error
      throw new Error("wallet_unknown_on_this_node: Ce wallet n'est pas connu de ce nœud. Réessayez ou utilisez votre seed_hex.");
    }
    if (status === 503 || status === 502 || !status) {
      throw new Error("service_unavailable: Le service est momentanément indisponible. Réessayez dans quelques secondes.");
    }
    throw err;
  }
}

export async function webauthnLoginVerify(name: string, credential: unknown) {
  const { data } = await api.post("/auth/webauthn/login/verify", { name, credential });
  return data as {
    ok: boolean;
    session_token: string;
    wallet_name: string;
    address: string;
    expires_in: number;
    modality?: string;
  };
}

// ─── R358 — routes anonymes (zéro nom utilisateur) ───────────────────────────

/** Démarre la cérémonie WebAuthn sans aucun nom fourni par l'utilisateur. */
export async function anonRegisterOptions(createWallet = true) {
  const { data } = await api.post("/auth/anon/register/options", {
    create_wallet: createWallet,
  });
  return data as {
    publicKey: WebAuthnPublicKey;
    create_wallet: boolean;
    raw_biometric_never_stored: boolean;
  };
}

/** Vérifie l'attestation WebAuthn et crée le wallet automatiquement.
 *  wallet_name = "w-<sha256(credential_id)[:16]>" — dérivé côté serveur.
 */
export async function anonRegisterVerify(credential: unknown, createWallet = true) {
  const { data } = await api.post("/auth/anon/register/verify", {
    credential,
    create_wallet: createWallet,
  });
  return data as {
    ok: boolean;
    wallet_name: string;
    address: string;
    session_token: string;
    expires_in: number;
    wallet_created: boolean;
    seed_hex?: string;
    WARNING?: string;
    unique_human_proven: boolean;
    certified: boolean;
  };
}

export async function webauthnStatus(name: string) {
  const { data } = await api.get("/auth/webauthn/status", { params: { name } });
  return data as {
    wallet_name: string;
    wallet_exists: boolean;
    fingerprint_enrolled: boolean;
    face_webauthn_enrolled: boolean;
    face_camera_enrolled: boolean;
    raw_biometric_stored: boolean;
  };
}

export async function faceEnrollOptions(name: string, createWallet = true) {
  const { data } = await api.post("/auth/face/enroll/options", { name, create_wallet: createWallet });
  return data as { nonce: string; liveness_required: boolean; camera_facing_mode: string };
}

export async function faceEnrollVerify(body: {
  name: string;
  nonce: string;
  device_secret: string;
  liveness_ok: boolean;
  create_wallet?: boolean;
}) {
  const { data } = await api.post("/auth/face/enroll/verify", body);
  return data as {
    ok: boolean;
    session_token: string;
    wallet_name: string;
    address: string;
    expires_in: number;
    seed_hex?: string;
    WARNING?: string;
    wallet_created: boolean;
  };
}

export async function faceLoginOptions(name: string) {
  const { data } = await api.post("/auth/face/login/options", { name });
  return data as { nonce: string };
}

export async function faceLogin(body: {
  name: string;
  nonce: string;
  device_secret: string;
  liveness_ok: boolean;
}) {
  const { data } = await api.post("/auth/face/login", body);
  return data as {
    ok: boolean;
    session_token: string;
    wallet_name: string;
    address: string;
    expires_in: number;
  };
}

export async function fetchBlockDetail(index: number) {
  const { data } = await api.get(`/chain/block/${index}`);
  return data.block as ChainBlock;
}

export async function fetchChainVerify() {
  const { data } = await api.get("/chain/verify");
  return data as { valid: boolean; message: string; block_count: number };
}

export async function fetchDemoLiveLog() {
  const { data } = await api.get("/dashboard/logs/demo-live");
  return data as { content: string; lines: string[]; line_count: number };
}

export async function fetchMiningLatest() {
  const { data } = await api.get("/dashboard/logs/mining-latest");
  return data as { path: string; data: Record<string, unknown> };
}

export async function fetchMiningStatus() {
  const { data } = await api.get("/dashboard/mining/status");
  return data as {
    block_count: number;
    current_reward_artcb: number;
    blocks_until_halving: number | null;
    remaining_supply_artcb?: number | null;
    halving_removed?: boolean;
    total_rewards_artcb: number;
    pol_score: number;
  };
}

export async function fetchFoundersAllocation() {
  const { data } = await api.get("/dashboard/founders/allocation");
  return data as {
    founders_total_artcb: number;
    balances: Array<{ founder_id: number; name: string; balance_artcb: number }>;
  };
}

export async function fetchWalletRewards(address: string) {
  const { data } = await api.get(`/dashboard/wallet/${encodeURIComponent(address)}/rewards`);
  return data as {
    rewards: Array<{ block_index: number; reward_artcb: number; pol_score: number; timestamp: string }>;
    total_artcb: number;
  };
}

export async function fetchHealth() {
  const { data } = await api.get("/health");
  return data as { status: string; chain?: { valid?: boolean } };
}

export async function fetchConnectors() {
  const { data } = await api.get("/connectors");
  return data as {
    connectors: Array<{
      connector_id: string;
      provider: string;
      label: string;
      config: Record<string, string>;
      api_key_masked?: string;
      kind: string;
      last_test_ok?: boolean | null;
      last_test_message?: string | null;
    }>;
    llm_providers: string[];
    data_source_providers: string[];
    storage: string;
  };
}

export async function saveConnector(body: {
  provider: string;
  label: string;
  api_key: string;
  config?: Record<string, string>;
}) {
  const { data } = await api.post("/connectors", body);
  return data;
}

export async function deleteConnector(connectorId: string) {
  const { data } = await api.delete(`/connectors/${connectorId}`);
  return data;
}

export async function testConnector(connectorId: string) {
  const { data } = await api.post(`/connectors/${connectorId}/test`);
  return data as { ok: boolean; message: string };
}

export async function learnFromSource(
  connectorId: string,
  opts: { use_llm?: boolean; llm_provider?: string; limit?: number } = {},
) {
  const { data } = await api.post(`/connectors/${connectorId}/learn`, {
    connector_id: connectorId,
    ...opts,
  });
  return data as {
    graph_id: string;
    node_count: number;
    chars_ingested: number;
    message: string;
  };
}

export function chainQueryParams(visibility: string, groupId: string | null) {
  if (visibility === "group" && groupId) return { groupId };
  if (visibility !== "private") return { visibility };
  return {};
}

export async function fetchPolScore() {
  const { data } = await api.get("/pol/score");
  return data;
}

export async function fetchConnectorFormats() {
  const { data } = await api.get("/connectors/formats");
  return data as { formats: Record<string, string[]>; total_extensions: number };
}

export function wsUrl(sessionId: string): string {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  const host = window.location.host;
  return `${proto}://${host}/ws/graph/${sessionId}`;
}

// --- Governance ---
export async function fetchGovernanceProposals(status?: string) {
  const { data } = await api.get("/governance/proposals", { params: status ? { status } : {} });
  return data as { proposals: Array<Record<string, unknown>>; count: number };
}

export async function createGovernanceProposal(body: {
  title: string;
  description: string;
  version: string;
  proposal_id?: string;
}) {
  const { data } = await api.post("/governance/proposals", body);
  return data;
}

export async function castGovernanceVote(proposalId: string, walletAddress: string, choice: "yes" | "no") {
  const { data } = await api.post("/governance/vote", {
    proposal_id: proposalId,
    wallet_address: walletAddress,
    choice,
  });
  return data as { requires_rollback: boolean };
}

// --- P2P / Pool : backend-only — supprimé du frontend R398 ---
// Ces endpoints restent accessibles via API directe ou agents.
// Pages /network et /memorize déjà retirées depuis R359/R379.

export async function runMiningPipeline(body: {
  text: string;
  session_id?: string;
  use_llm?: boolean;
  actor_address?: string;
  wallet_name?: string;
  visibility?: string;
  group_id?: string | null;
  use_distributed_pool?: boolean;
  encrypt_transport?: boolean;
  auto_finalize?: boolean;
  chunk_chars?: number;
}) {
  const { data } = await api.post("/mining/pipeline", body);
  return data as Record<string, unknown>;
}

// --- Notifications ---
export async function fetchNotificationChannels() {
  const { data } = await api.get("/notifications/channels");
  return data as { channels: Array<Record<string, unknown>>; count: number };
}

export async function saveNotificationChannel(body: {
  channel_type: "telegram";
  label: string;
  secret: string;
  config?: Record<string, string>;
}) {
  const { data } = await api.post("/notifications/channels", body);
  return data;
}

// --------------------------------------------------------------------------
// API Keys public
// --------------------------------------------------------------------------
export type ApiKeyRecord = {
  key_id: string;
  label: string;
  scopes: string[];
  created_at: number;
  expires_at: number | null;
  last_used_at: number | null;
  active: boolean;
  key_preview: string;
};

export async function listApiKeys(): Promise<{ keys: ApiKeyRecord[]; count: number }> {
  const { data } = await api.get("/api-keys/list", { headers: sessionHeaders() });
  return data;
}

export async function generateApiKey(body: {
  label: string;
  scopes?: string[];
  expires_days?: number | null;
}): Promise<{
  key_id: string;
  label: string;
  token: string;
  key_preview: string;
  scopes: string[];
  created_at: number;
  expires_at: number | null;
  message: string;
}> {
  const { data } = await api.post("/api-keys/generate", body, { headers: sessionHeaders() });
  return data;
}

export async function revokeApiKey(keyId: string): Promise<{ revoked: boolean; key_id: string }> {
  const { data } = await api.delete(`/api-keys/${keyId}`, { headers: sessionHeaders() });
  return data;
}

export async function getApiKeyMe(token: string): Promise<ApiKeyRecord> {
  const { data } = await api.get("/api-keys/me", {
    headers: { Authorization: `Bearer ${token}` },
  });
  return data;
}

// --------------------------------------------------------------------------
// AI Agent — statut, raisonnement, recherche, export, webhooks
// R424 — postAiMemo / fetchAiMemory / AiMemo supprimés du frontend (backend-only)
//         /ai/memo et /ai/memory restent accessibles via API directe ou agents.
// --------------------------------------------------------------------------

export async function fetchAiStatus(token?: string): Promise<Record<string, unknown>> {
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const { data } = await api.get("/ai/status", { headers });
  return data;
}

export async function chainSearch(
  q: string,
  opts?: { top_k?: number; visibility?: string },
  token?: string,
): Promise<{ query: string; results: Record<string, unknown>[]; count: number }> {
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const { data } = await api.get("/chain/search", { params: { q, ...opts }, headers });
  return data;
}

export async function chainExport(
  opts?: { format?: string; visibility?: string; include_symbols?: boolean },
  token?: string,
): Promise<Record<string, unknown>> {
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const { data } = await api.get("/chain/export", { params: opts, headers });
  return data;
}

export async function fetchWebhooks(token?: string): Promise<{ webhooks: Record<string, unknown>[]; count: number }> {
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const { data } = await api.get("/webhooks/list", { headers });
  return data;
}

export async function registerWebhook(
  body: { url: string; label: string; events?: string[]; secret?: string },
  token?: string,
): Promise<Record<string, unknown>> {
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const { data } = await api.post("/webhooks/register", body, { headers });
  return data;
}

export async function deleteWebhook(hookId: string, token?: string): Promise<{ revoked: boolean }> {
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const { data } = await api.delete(`/webhooks/${hookId}`, { headers });
  return data;
}

// --------------------------------------------------------------------------
// P0-C — Identité biométrique on-chain (2026-09-16)
// --------------------------------------------------------------------------

export type HumanIdentityRecord = {
  human_id: string;
  commitment: string;
  template_hash: string;
  helper_data: string;
  algorithm: string;
  biometric_version: number;
  status: string;
  created_at: string;
  wallet_address: string | null;
  unique_human_proven: false;
  node_id: string | null;
};

export type BiometricEnrollResponse = {
  ok: boolean;
  human_id: string;
  status: string;
  human_identity_record: HumanIdentityRecord;
  commitment_public: Record<string, unknown>;
  private_for_client: {
    secret_hex: string;
    blinding_hex: string;
    WARNING: string;
  };
  unique_human_proven: false;
  certified: false;
  note: string;
};

export type UniquenessCheckResponse = {
  match_found: boolean;
  existing_human_id: string | null;
  match_score: number;
  certified: false;
  unique_human_proven: false;
  note: string;
};

/** POST /api/v1/identity/biometric/enroll
 *  template_hex = modèle biométrique normalisé en hex (jamais l'image brute).
 *  wallet_address optionnel.
 */
export async function biometricEnroll(
  template_hex: string,
  wallet_address?: string,
): Promise<BiometricEnrollResponse> {
  const { data } = await api.post("/identity/biometric/enroll", {
    template_hex,
    wallet_address: wallet_address || undefined,
  });
  return data as BiometricEnrollResponse;
}

/** POST /api/v1/identity/biometric/uniqueness-check */
export async function biometricUniquenessCheck(
  template_hex: string,
): Promise<UniquenessCheckResponse> {
  const { data } = await api.post("/identity/biometric/uniqueness-check", {
    template_hex,
  });
  return data as UniquenessCheckResponse;
}

/** GET /api/v1/identity/biometric/{human_id} */
export async function fetchHumanIdentity(human_id: string): Promise<HumanIdentityRecord & { found: boolean }> {
  const { data } = await api.get(`/identity/biometric/${encodeURIComponent(human_id)}`);
  return data;
}

/** GET /api/v1/identity/biometric/ */
export async function listHumanIdentities(): Promise<{ count: number; human_ids: string[]; unique_human_proven: false }> {
  const { data } = await api.get("/identity/biometric/");
  return data;
}

// ─── ADD_DEVICE — R350–R354 (2026-09-17) ────────────────────────────────────

export interface AddDeviceOptionsResponse {
  challenge: string;
  human_id: string;
  expires_in: number;
  instructions: string;
  forbidden: string[];
  certified_100: false;
  unique_human_proven: false;
}

export interface AddDeviceVerifyRequest {
  challenge: string;
  existing_template_hex: string;
  new_device_credential_hex: string;
  new_device_hint?: string;
}

export interface AddDeviceVerifyResponse {
  device_added: true;
  device_id: string;
  human_id: string;
  wallet_address: string;
  device_hint: string;
  devices_count: number;
  max_devices: number;
  unique_human_proven: false;
  certified_100: false;
  note: string;
}

export interface DeviceRecord {
  device_id: string;
  device_hint: string;
  created_at: number;
  revoked: boolean;
}

export interface DeviceListResponse {
  human_id: string;
  devices: DeviceRecord[];
  count: number;
  active_count: number;
  certified_100: false;
}

/** POST /api/v1/identity/device/add-options — Étape 1 : challenge ADD_DEVICE */
export async function addDeviceOptions(
  human_id: string,
  new_device_hint = "unknown",
): Promise<AddDeviceOptionsResponse> {
  const { data } = await api.post("/identity/device/add-options", { human_id, new_device_hint });
  return data as AddDeviceOptionsResponse;
}

/** POST /api/v1/identity/device/add-verify — Étape 2 : vérification biométrique + enregistrement */
export async function addDeviceVerify(
  body: AddDeviceVerifyRequest,
): Promise<AddDeviceVerifyResponse> {
  const { data } = await api.post("/identity/device/add-verify", body);
  return data as AddDeviceVerifyResponse;
}

/** GET /api/v1/identity/device/{human_id}/devices — Lister les appareils d'une identité */
export async function listDevices(human_id: string): Promise<DeviceListResponse> {
  const { data } = await api.get(`/identity/device/${encodeURIComponent(human_id)}/devices`);
  return data as DeviceListResponse;
}

// ─── REFLEX STATUS — R350–R354 ────────────────────────────────────────────────
// R424 — ReflexStatusResponse + fetchReflexStatus supprimés du frontend (backend-only)
//         /api/v1/reflex/status reste accessible via API directe ou agents.
