# R470 — Bandeau 3 boutons Contact + Déploiement live 85561c5

**Date :** 2026-09-25  
**SHA commit :** `85561c5`  
**Branche :** `main`  
**Précédent SHA :** `ffcc2de` (R469)  
**Tests :** DO-178C gate 124/124 PASS  
**CERTIFIED_100=false**

---

## Objectif

1. Ajouter un point d'entrée visible dans le dashboard vers les 3 tunnels de contact (PRO / DEV / ORG) créés en R469 — ils existaient en code mais n'étaient accessibles par aucun lien dans l'UI.
2. Déployer le code `85561c5` (R469+R470) sur les 3 nœuds live N2/N3/N4.

---

## État avant R470

| Élément | État |
|---------|------|
| Routes `/contact/*` | ✅ Existaient (R469) |
| Boutons/liens visibles dans UI | ❌ Aucun — tunnels inaccessibles sans URL manuelle |
| `DashboardLayout.tsx` sidebar | ❌ Pas de section CONTACT |
| Nœuds live N2/N3/N4 | Sur SHA antérieur à R469 |

---

## Modifications R470

### 1. `frontend/src/pages/Home.tsx` — Bandeau 3 boutons

**Avant (ligne 65) :**
```tsx
  return (
    <div className="mc-page">
      <h1 className="dashboard-title">{t('home_title')}</h1>

      {/* UX-2 FIX: Bandeau onboarding ... */}
```

**Après :**
```tsx
      {/* R470 — Bandeau de contact 3 tunnels : Pro / Developer / Organization */}
      <div className="panel mc-contact-banner" style={{ ... borderColor: "var(--mc-accent, #3b82d4)", ... }}>
        <div>
          <p>Connect with ARTCB</p>
          <p>Choose your profile to get in touch with the team</p>
        </div>
        <div style={{ display: "flex", gap: "0.5rem" }}>
          <Link to="/contact/pro"          style={{ background: "#3b82d4" }}>👤 PRO</Link>
          <Link to="/contact/developer"    style={{ background: "#6366f1" }}>💻 DEV</Link>
          <Link to="/contact/organization" style={{ background: "#0f766e" }}>🏢 ORG</Link>
        </div>
      </div>
```

### 2. `frontend/src/layout/DashboardLayout.tsx` — Section CONTACT sidebar

**Avant (ligne 40) :**
```tsx
    { section: "SYSTEM", items: [...] },
  ];
```

**Après :**
```tsx
    { section: "SYSTEM", items: [...] },
    { section: "CONTACT", items: [
      { to: "/contact/pro",          label: "PRO", icon: "👤" },
      { to: "/contact/developer",    label: "DEV", icon: "💻" },
      { to: "/contact/organization", label: "ORG", icon: "🏢" },
    ]},
  ];
```

---

## Déploiement live

### Méthode utilisée

- N2 (OVH2 `151.80.107.29`) : SSH via relay SSM (port 22 inaccessible depuis Mac — L-054)
- N4 (OVH4 `91.134.45.8`) : SSH via relay SSM
- N3 (AWS3) : SSM direct

### Anomalies rencontrées et résolues

| Anomalie | Cause | Résolution |
|----------|-------|-----------|
| N2/N4 SSH timeout depuis Mac | Port 22 bloqué réseau local (L-054) | Relay SSM via instance AWS |
| `sha_ok=False` dans script initial | Comparaison SHA complet vs court | Sonde directe corrigée |
| `git rev-parse` vide via SSM→SSH | `safe.directory` non configuré | `git config --global --add safe.directory` ajouté |
| `HEALTH_DOWN` post-restart 7s | Service non encore UP en 7s (TLS) | Sonde séparée après délai |

### Résultat final confirmé (sonde directe)

| Nœud | SHA | Status |
|------|-----|--------|
| N3 (AWS3) | `85561c5666ee` | ✅ healthy |
| N2 (OVH2) | `85561c5666eedefdc62529e0f9965be2bc0110a3` | ✅ healthy |
| N4 (OVH4) | `85561c5666eedefdc62529e0f9965be2bc0110a3` | ✅ healthy |

**OVH1 = BLOQUÉ (D-036) — non déployé intentionnellement.**

---

## Architecture Contact complète (R469+R470)

```
artcb.me (Dashboard)
│
├── Bandeau Home.tsx — boutons 👤PRO 💻DEV 🏢ORG  ← R470
├── Sidebar DashboardLayout — section CONTACT       ← R470
│
├── /contact/pro          → ContactPro.tsx          ← R469
├── /contact/developer    → ContactDeveloper.tsx    ← R469
└── /contact/organization → ContactOrganization.tsx ← R469
         ↓ POST /api/v1/contact
    contact_routes.py (FastAPI)                      ← R469
         ↓
    data/contacts/contact_*.json (stockage local)
```

---

## Limites documentées

- Les tunnels Contact sont côté frontend SPA (HashRouter) — ils requièrent que le frontend React soit servi. Sur les nœuds live, le frontend est servi par le backend FastAPI via `StaticFiles`.
- `email-validator` non installé (EmailStr retiré en R469) — validation email est basique (min_length=3).
- Pas de notification par email à l'équipe ARTCB (stockage local uniquement, MVP).

---

**CERTIFIED_100=false** — Invariant absolu maintenu.
