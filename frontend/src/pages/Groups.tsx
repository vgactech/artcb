import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  approveJoinRequest,
  createGroup,
  createOrganization,
  exportDomain,
  fetchDomains,
  fetchGroupsForAddress,
  fetchJoinRequests,
  fetchWallets,
  importDomain,
  locateDomain,
  promoteGroupMember,
  rejectJoinRequest,
} from "../api/client";
import type { DomainManifestView, GroupData, OrgCreated } from "../api/client";
import { useDashboard } from "../context/DashboardContext";
import { useTranslation } from "../i18n/useTranslation";

export function Groups() {
  const { t } = useTranslation();
  const { actorAddress, setActorAddress, setGroupId } = useDashboard();
  const [wallets, setWallets] = useState<Array<{ address: string; name: string }>>([]);
  const [groups, setGroups] = useState<GroupData[]>([]);
  const [newName, setNewName] = useState("");
  const [selectedGroup, setSelectedGroup] = useState<GroupData | null>(null);
  const [pending, setPending] = useState<
    Array<{ request_id: string; address: string; status: string; created_at: string }>
  >([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [orgName, setOrgName] = useState("");
  const [storageMode, setStorageMode] = useState("artcb_managed");
  const [selectedNodes, setSelectedNodes] = useState("");
  const [lastOrg, setLastOrg] = useState<OrgCreated | null>(null);
  const [domains, setDomains] = useState<DomainManifestView[]>([]);
  const [importText, setImportText] = useState("");
  const [exportText, setExportText] = useState("");
  const [locateText, setLocateText] = useState("");

  const loadGroups = async (address: string) => {
    if (!address) return;
    const data = await fetchGroupsForAddress(address);
    setGroups(data.groups);
  };

  const loadPending = async (groupId: string) => {
    if (!actorAddress) return;
    try {
      const data = await fetchJoinRequests(groupId, actorAddress, "pending");
      setPending(data.requests);
    } catch {
      setPending([]);
    }
  };

  useEffect(() => {
    fetchWallets()
      .then((list) => {
        setWallets(list);
        if (list.length && !actorAddress) setActorAddress(list[0].address);
      })
      .catch(() => setWallets([]));
  }, [actorAddress, setActorAddress]);

  const loadDomains = async () => {
    try {
      const data = await fetchDomains();
      setDomains(data.domains);
    } catch {
      setDomains([]);
    }
  };

  useEffect(() => {
    if (actorAddress) loadGroups(actorAddress).catch(() => setGroups([]));
    loadDomains();
  }, [actorAddress]);

  useEffect(() => {
    if (selectedGroup) loadPending(selectedGroup.group_id);
  }, [selectedGroup, actorAddress]);

  const handleCreateOrg = async () => {
    if (!orgName.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const extra = selectedNodes
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      const org = await createOrganization(orgName.trim(), storageMode, extra);
      setLastOrg(org);
      setOrgName("");
      await loadDomains();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  const handleExport = async (domainId: string) => {
    setLoading(true);
    setError(null);
    try {
      const bundle = await exportDomain(domainId);
      setExportText(JSON.stringify(bundle, null, 2));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  const handleImport = async () => {
    if (!importText.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const bundle = JSON.parse(importText) as Record<string, unknown>;
      await importDomain(bundle);
      setImportText("");
      await loadDomains();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  const handleLocate = async (domainId: string) => {
    try {
      const loc = await locateDomain(domainId);
      setLocateText(
        loc.hosted_here
          ? `Hébergé ici (${loc.this_node}). Le nœud n'est pas propriétaire.`
          : `Pas hébergé ici. Hôtes autorisés : ${loc.authorized_nodes.join(", ")}`,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const handleCreate = async () => {
    if (!newName.trim() || !actorAddress) return;
    setLoading(true);
    setError(null);
    try {
      const g = await createGroup(newName.trim(), actorAddress);
      setNewName("");
      setSelectedGroup(g);
      setGroupId(g.group_id);
      await loadGroups(actorAddress);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  const handleApprove = async (requestId: string) => {
    if (!selectedGroup) return;
    setLoading(true);
    try {
      await approveJoinRequest(selectedGroup.group_id, actorAddress, requestId);
      const g = await fetchGroupsForAddress(actorAddress);
      const updated = g.groups.find((x) => x.group_id === selectedGroup.group_id);
      if (updated) setSelectedGroup(updated);
      await loadPending(selectedGroup.group_id);
      await loadGroups(actorAddress);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  const handleReject = async (requestId: string) => {
    if (!selectedGroup) return;
    setLoading(true);
    try {
      await rejectJoinRequest(selectedGroup.group_id, actorAddress, requestId);
      await loadPending(selectedGroup.group_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  const handlePromote = async (target: string) => {
    if (!selectedGroup) return;
    setLoading(true);
    try {
      const g = await promoteGroupMember(selectedGroup.group_id, actorAddress, target, "admin");
      setSelectedGroup(g);
      await loadGroups(actorAddress);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  const isFounder = selectedGroup?.founder_address === actorAddress;
  const isAdmin =
    selectedGroup?.members.some((m) => m.address === actorAddress && m.role === "admin") ?? false;

  return (
    <div className="mc-page">
      <h1 className="dashboard-title">
        {t('nav_groups')}{" "}
        <Link to="/groups/join" className="mc-link-pill">
          Rejoindre →
        </Link>
      </h1>

      <div className="panel">
        <h2>{t('common_wallet')}</h2>
        {wallets.length ? (
          /* BUG-R7: forcer onChange même quand la 1ère option est déjà affichée
             en initialisant actorAddress dès le chargement (fait dans useEffect),
             et en ajoutant une option vide initiale si actorAddress est encore vide */
          <select
            value={actorAddress || ""}
            onChange={(e) => setActorAddress(e.target.value)}
            aria-label="Sélectionner un wallet actif"
          >
            {!actorAddress && (
              <option value="" disabled>— choisir un wallet —</option>
            )}
            {wallets.map((w) => (
              <option key={w.address} value={w.address}>
                {w.name} — {w.address.slice(0, 12)}…
              </option>
            ))}
          </select>
        ) : (
          <p className="mc-muted">
            Créez un wallet sur <Link to="/wallets">Wallets</Link>.
          </p>
        )}
      </div>

      <div className="panel">
        <h2>Créer une organisation</h2>
        <p className="mc-muted">
          Vous n&apos;avez pas besoin d&apos;installer un nœud. Le serveur auquel vous êtes
          connecté <strong>héberge</strong> le Genesis. Votre wallet en reste le{" "}
          <strong>propriétaire</strong>.
        </p>
        <div className="toolbar">
          <input
            value={orgName}
            onChange={(e) => setOrgName(e.target.value)}
            placeholder="Nom de l'organisation"
          />
          <select
            value={storageMode}
            onChange={(e) => setStorageMode(e.target.value)}
            aria-label="Mode de stockage du domaine"
          >
            <option value="artcb_managed">Hébergé par ARTCB</option>
            <option value="selected_nodes">Choisir des nœuds</option>
            <option value="personal">Mon serveur (plus tard)</option>
            <option value="hybrid">Hybride</option>
          </select>
          <button className="primary" onClick={handleCreateOrg} disabled={loading || !actorAddress}>
            Créer l&apos;organisation
          </button>
        </div>
        {(storageMode === "selected_nodes" || storageMode === "hybrid") && (
          <input
            value={selectedNodes}
            onChange={(e) => setSelectedNodes(e.target.value)}
            placeholder="Nœuds autorisés (ids séparés par des virgules)"
            style={{ marginTop: "0.5rem", width: "100%" }}
          />
        )}
        {lastOrg && (
          <div className="panel mc-slot" style={{ marginTop: "1rem" }}>
            <p>
              Organisation <strong>{lastOrg.name}</strong> — le nœud n&apos;est pas propriétaire.
            </p>
            <p className="mc-mono">ORG {lastOrg.organization_id}</p>
            <p className="mc-mono">DOMAIN {lastOrg.domain.domain_id}</p>
            <p className="mc-mono">HASH {lastOrg.content_hash.slice(0, 16)}…</p>
            <p className="mc-muted">{lastOrg.ownership.cest_a_dire}</p>
          </div>
        )}
      </div>

      <div className="panel">
        <h2>Domaines ({domains.length})</h2>
        <p className="mc-muted">
          Identité publique : fondateur + hash. Le corps Genesis reste sur le nœud hôte.
          Ancrage chaîne globale : pas encore (journal local).
        </p>
        {locateText && <p className="mc-muted">{locateText}</p>}
        <ul className="mc-checklist-list">
          {domains.map((d) => (
            <li key={d.domain_id}>
              <strong>{d.domain_type}</strong> {d.subject_id} · {d.storage_mode}
              <button type="button" onClick={() => handleLocate(d.domain_id)} disabled={loading}>
                Localiser
              </button>
              {d.founder_address === actorAddress && (
                <button type="button" onClick={() => handleExport(d.domain_id)} disabled={loading}>
                  Exporter
                </button>
              )}
            </li>
          ))}
        </ul>
        {exportText && (
          <textarea readOnly value={exportText} rows={8} style={{ width: "100%" }} />
        )}
        <h3>Importer un domaine (signature fondateur via session)</h3>
        <textarea
          value={importText}
          onChange={(e) => setImportText(e.target.value)}
          placeholder="Coller le JSON d'export"
          rows={6}
          style={{ width: "100%" }}
        />
        <button type="button" onClick={handleImport} disabled={loading || !actorAddress}>
          Importer
        </button>
      </div>

      <div className="panel mc-groups-panel">
        <h2>{t('common_create')} {t('common_group')}</h2>
        <div className="toolbar">
          <input
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder={t('common_group')}
          />
          <button className="primary" onClick={handleCreate} disabled={loading || !actorAddress}>
            {t('common_create')}
          </button>
        </div>
        {error && <p className="mc-error">{error}</p>}
      </div>

      <div className="panel">
        <h2>{t('common_groups')} ({groups.length})</h2>
        <ul className="mc-checklist-list">
          {groups.map((g) => (
            <li key={g.group_id}>
              <button
                type="button"
                onClick={() => {
                  setSelectedGroup(g);
                  setGroupId(g.group_id);
                }}
              >
                {g.name}
              </button>
              <span className="mc-muted"> · {g.members.length} membres</span>
            </li>
          ))}
        </ul>
      </div>

      {selectedGroup && (
        <div className="panel">
          <h2>{selectedGroup.name}</h2>
          <p className="mc-muted">ID: {selectedGroup.group_id}</p>

          <div className="panel mc-slot mc-slot-gold" style={{ marginBottom: "1rem" }}>
            <h3>Code invitation (partager sans demander le wallet)</h3>
            <p className="mc-kpi-value">{selectedGroup.join_code ?? "—"}</p>
            <p className="mc-muted">
              L&apos;invité utilise <Link to="/groups/join">Rejoindre un groupe</Link> et signe avec
              son wallet — vous ne voyez son adresse qu&apos;après sa demande signée.
            </p>
          </div>

          {(isFounder || isAdmin) && pending.length > 0 && (
            <div className="panel">
              <h3>Demandes en attente ({pending.length})</h3>
              <ul className="mc-checklist-list">
                {pending.map((req) => (
                  <li key={req.request_id}>
                    <span className="mc-mono">{req.address.slice(0, 20)}…</span>
                    <button onClick={() => handleApprove(req.request_id)} disabled={loading}>
                      Approuver
                    </button>
                    <button onClick={() => handleReject(req.request_id)} disabled={loading}>
                      Refuser
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {selectedGroup.members.map((m) => (
            <div key={m.address} className="mc-player-row">
              <div className="mc-player-head">
                {m.role === "founder" ? "F" : m.role === "admin" ? "A" : "G"}
              </div>
              <div>
                <strong>{m.role}</strong> — {m.address.slice(0, 20)}…
                {isFounder && m.role === "contributor" && (
                  <button
                    type="button"
                    style={{ marginLeft: "0.5rem" }}
                    onClick={() => handlePromote(m.address)}
                    disabled={loading}
                  >
                    Nommer admin
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
