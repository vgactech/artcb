import axios from "axios";
import type { IRGraph, PolMetrics, ChainBlock } from "../types";

const api = axios.create({ baseURL: "/api/v1" });

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
  const { data } = await api.get("/wallet/list");
  return data.wallets as Array<{ address: string; name: string }>;
}

export async function fetchWalletBalance(address: string) {
  const { data } = await api.get(`/wallet/balance/${address}`);
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

export async function createGroup(name: string, founderAddress: string) {
  const { data } = await api.post("/groups", { name, founder_address: founderAddress });
  return data as GroupData;
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
  const { data } = await api.post("/auth/webauthn/login/options", { name, modality });
  return data as { publicKey: WebAuthnPublicKey };
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

// --- P2P ---
export async function fetchP2PStatus() {
  const { data } = await api.get("/p2p/status");
  return data as Record<string, unknown>;
}

export async function fetchP2PPeers() {
  const { data } = await api.get("/p2p/peers");
  return data as { peers: Array<Record<string, unknown>>; count: number };
}

export async function addP2PPeer(body: {
  host: string;
  port: number;
  kem_public_key_hex: string;
  label?: string;
}) {
  const { data } = await api.post("/p2p/peers", body);
  return data;
}

export async function syncP2PAll(fromIndex = 0) {
  const { data } = await api.post("/p2p/sync", null, { params: { from_index: fromIndex } });
  return data as { results: unknown[]; peer_count: number };
}

// --- Pool calcul distribué E2E ---
export async function fetchPoolStatus() {
  const { data } = await api.get("/pool/status");
  return data as Record<string, unknown>;
}

export async function fetchPoolJobs() {
  const { data } = await api.get("/pool/jobs");
  return data as { jobs: Array<Record<string, unknown>>; count: number };
}

export async function createPoolJob(body: {
  text: string;
  visibility?: string;
  group_id?: string;
  actor_address?: string;
  wallet_name?: string;
  chunk_chars?: number;
  auto_dispatch?: boolean;
  encrypt_transport?: boolean;
}) {
  const { data } = await api.post("/pool/jobs", body);
  return data as { job: Record<string, unknown>; encrypted_transport: boolean };
}

export async function processAllPoolIncoming(body: {
  wallet_name?: string;
  contributor_address?: string;
}) {
  const { data } = await api.post("/pool/incoming/process-all", body);
  return data as { processed: Array<Record<string, unknown>>; count: number };
}

export async function finalizePoolJob(jobId: string, fullText: string) {
  const { data } = await api.post(`/pool/jobs/${jobId}/finalize`, { full_text: fullText });
  return data as Record<string, unknown>;
}

export async function fetchPoolPreferences() {
  const { data } = await api.get("/pool/preferences");
  return data as { preferences: Record<string, unknown> };
}

export async function savePoolPreferences(body: Record<string, unknown>) {
  const { data } = await api.put("/pool/preferences", body);
  return data;
}

export async function runPoolMining(body: {
  text: string;
  use_distributed_pool?: boolean;
  encrypt_transport?: boolean;
  visibility?: string;
  group_id?: string | null;
  actor_address?: string;
  wallet_name?: string;
  auto_finalize?: boolean;
  chunk_chars?: number;
}) {
  const { data } = await api.post("/pool/run", body);
  return data as Record<string, unknown>;
}

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
  const { data } = await api.get("/api-keys/list");
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
  const { data } = await api.post("/api-keys/generate", body);
  return data;
}

export async function revokeApiKey(keyId: string): Promise<{ revoked: boolean; key_id: string }> {
  const { data } = await api.delete(`/api-keys/${keyId}`);
  return data;
}

export async function getApiKeyMe(token: string): Promise<ApiKeyRecord> {
  const { data } = await api.get("/api-keys/me", {
    headers: { Authorization: `Bearer ${token}` },
  });
  return data;
}

// --------------------------------------------------------------------------
// AI Agent — mémoire, raisonnement, recherche, export, webhooks
// --------------------------------------------------------------------------

export type AiMemo = {
  block_index: number;
  block_hash: string;
  graph_id: string;
  timestamp: string;
  pol_score: number;
  memo_type: string;
  agent_id: string;
  session_id: string;
  tags: string[];
  source: string;
};

export async function fetchAiStatus(token?: string): Promise<Record<string, unknown>> {
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const { data } = await api.get("/ai/status", { headers });
  return data;
}

export async function postAiMemo(
  body: {
    content: string;
    memo_type?: string;
    tags?: string[];
    session_id?: string;
    wallet_name?: string | null;
    visibility?: string;
  },
  token?: string,
): Promise<Record<string, unknown>> {
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const { data } = await api.post("/ai/memo", body, { headers });
  return data;
}

export async function fetchAiMemory(
  opts?: { limit?: number; memo_type?: string },
  token?: string,
): Promise<{ memos: AiMemo[]; count: number }> {
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const { data } = await api.get("/ai/memory", { params: opts, headers });
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
