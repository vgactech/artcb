import { useState } from "react";

// R468 — Tunnel de contact pour les organisations
// Qualification B2B : type, taille, secteur, projet, besoin sécurité

interface OrgFormData {
  intent: string;
  org_type: string;
  size: string;
  topic: string;
  org_name: string;
  role: string;
  name: string;
  email: string;
  phone: string;
  linkedin: string;
}

const INTENTS = [
  { value: "integrate_process", label: "Intégrer ARTCB à nos processus" },
  { value: "pilot", label: "Piloter un test / POC" },
  { value: "deploy", label: "Déployer un environnement" },
  { value: "partnership", label: "Étudier un partenariat" },
  { value: "use_case", label: "Étudier un cas d'usage" },
  { value: "other", label: "Autre" },
];

const ORG_TYPES = [
  { value: "company", label: "Entreprise privée" },
  { value: "public", label: "Administration / Secteur public" },
  { value: "association", label: "Association / ONG" },
  { value: "research", label: "Laboratoire / Recherche" },
  { value: "other", label: "Autre" },
];

const SIZES = [
  { value: "1_10", label: "1 – 10 personnes" },
  { value: "11_50", label: "11 – 50 personnes" },
  { value: "51_250", label: "51 – 250 personnes" },
  { value: "251_1000", label: "251 – 1 000 personnes" },
  { value: "1000_plus", label: "Plus de 1 000 personnes" },
];

const TOPICS = [
  { value: "ai_agents", label: "IA / Agents autonomes" },
  { value: "data_knowledge", label: "Données / Connaissance" },
  { value: "security", label: "Sécurité" },
  { value: "identity", label: "Identité numérique" },
  { value: "infrastructure", label: "Infrastructure / Cloud" },
  { value: "blockchain", label: "Blockchain / Traçabilité" },
  { value: "other", label: "Autre" },
];

const TOTAL_STEPS = 5;

export function ContactOrganization() {
  const [step, setStep] = useState(0);
  const [form, setForm] = useState<OrgFormData>({
    intent: "",
    org_type: "",
    size: "",
    topic: "",
    org_name: "",
    role: "",
    name: "",
    email: "",
    phone: "",
    linkedin: "",
  });
  const [submitted, setSubmitted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const progress = Math.round((step / TOTAL_STEPS) * 100);

  const selectOption = (field: keyof OrgFormData, value: string) => {
    setForm((f) => ({ ...f, [field]: value }));
    setStep((s) => s + 1);
  };

  const handleSubmit = async () => {
    if (!form.email.trim()) {
      setError("L'email professionnel est requis.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const resp = await fetch("/api/v1/contact", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          contact_type: "organization",
          intent: form.intent,
          org_type: form.org_type,
          size: form.size,
          topic: form.topic,
          org_name: form.org_name,
          role: form.role,
          name: form.name,
          email: form.email,
          phone: form.phone,
          linkedin: form.linkedin,
        }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      setSubmitted(true);
    } catch (e: unknown) {
      setError(`Erreur lors de l'envoi : ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setSubmitting(false);
    }
  };

  if (submitted) {
    return (
      <div className="mc-contact-tunnel">
        <div className="mc-contact-success">
          <h2 className="mc-contact-title">◆ Demande reçue</h2>
          <p className="mc-contact-text">
            Merci <strong>{form.name || "à vous"}</strong>. Notre équipe vous contactera
            à l'adresse <strong>{form.email}</strong> pour étudier votre projet.
          </p>
          <p className="mc-contact-text mc-contact-muted">
            Profil : Organisation · {ORG_TYPES.find(o => o.value === form.org_type)?.label ?? form.org_type}
            {form.size ? ` · ${SIZES.find(s => s.value === form.size)?.label ?? form.size}` : ""}
            {form.topic ? ` · ${TOPICS.find(t => t.value === form.topic)?.label ?? form.topic}` : ""}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="mc-contact-tunnel">
      <div className="mc-contact-header">
        <span className="mc-contact-badge mc-contact-badge-org">ORG</span>
        <h1 className="mc-contact-title">ARTCB pour les organisations</h1>
        <p className="mc-contact-subtitle">
          Intégrez ARTCB à vos processus, vos équipes et vos systèmes existants.
        </p>
        <div className="mc-contact-progress">
          <div className="mc-contact-progress-bar" style={{ width: `${progress}%` }} />
        </div>
        <p className="mc-contact-step-label">Étape {step + 1} sur {TOTAL_STEPS}</p>
      </div>

      {/* Étape 0 : intention */}
      {step === 0 && (
        <div className="mc-contact-step">
          <h2 className="mc-contact-question">Que souhaitez-vous faire avec ARTCB ?</h2>
          <div className="mc-contact-options">
            {INTENTS.map((i) => (
              <button
                key={i.value}
                className="mc-contact-option"
                onClick={() => selectOption("intent", i.value)}
              >
                {i.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Étape 1 : type d'organisation */}
      {step === 1 && (
        <div className="mc-contact-step">
          <h2 className="mc-contact-question">Quel est votre type d'organisation ?</h2>
          <div className="mc-contact-options">
            {ORG_TYPES.map((o) => (
              <button
                key={o.value}
                className="mc-contact-option"
                onClick={() => selectOption("org_type", o.value)}
              >
                {o.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Étape 2 : taille */}
      {step === 2 && (
        <div className="mc-contact-step">
          <h2 className="mc-contact-question">Quelle est la taille de votre organisation ?</h2>
          <div className="mc-contact-options">
            {SIZES.map((s) => (
              <button
                key={s.value}
                className="mc-contact-option"
                onClick={() => selectOption("size", s.value)}
              >
                {s.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Étape 3 : sujet principal */}
      {step === 3 && (
        <div className="mc-contact-step">
          <h2 className="mc-contact-question">Quel est votre sujet principal ?</h2>
          <div className="mc-contact-options">
            {TOPICS.map((t) => (
              <button
                key={t.value}
                className="mc-contact-option"
                onClick={() => selectOption("topic", t.value)}
              >
                {t.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Étape 4 : coordonnées */}
      {step === 4 && (
        <div className="mc-contact-step">
          <h2 className="mc-contact-question">Parlons de votre projet</h2>
          <p className="mc-contact-muted">
            Profil : {ORG_TYPES.find(o => o.value === form.org_type)?.label} ·{" "}
            {SIZES.find(s => s.value === form.size)?.label} ·{" "}
            {TOPICS.find(t => t.value === form.topic)?.label}
          </p>
          <div className="mc-contact-fields">
            <label className="mc-contact-label">
              Organisation (optionnel)
              <input
                className="mc-contact-input"
                type="text"
                value={form.org_name}
                onChange={(e) => setForm((f) => ({ ...f, org_name: e.target.value }))}
                placeholder="Nom de l'organisation"
              />
            </label>
            <label className="mc-contact-label">
              Votre fonction (optionnel)
              <input
                className="mc-contact-input"
                type="text"
                value={form.role}
                onChange={(e) => setForm((f) => ({ ...f, role: e.target.value }))}
                placeholder="DSI, Directeur technique, Responsable…"
              />
            </label>
            <label className="mc-contact-label">
              Votre nom (optionnel)
              <input
                className="mc-contact-input"
                type="text"
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                placeholder="Votre nom"
              />
            </label>
            <label className="mc-contact-label">
              Email professionnel <span className="mc-contact-required">*</span>
              <input
                className="mc-contact-input"
                type="email"
                value={form.email}
                onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
                placeholder="contact@organisation.com"
                required
              />
            </label>
            <label className="mc-contact-label">
              Téléphone (optionnel)
              <input
                className="mc-contact-input"
                type="tel"
                value={form.phone}
                onChange={(e) => setForm((f) => ({ ...f, phone: e.target.value }))}
                placeholder="+33 1 00 00 00 00"
              />
            </label>
            <label className="mc-contact-label">
              LinkedIn (optionnel)
              <input
                className="mc-contact-input"
                type="url"
                value={form.linkedin}
                onChange={(e) => setForm((f) => ({ ...f, linkedin: e.target.value }))}
                placeholder="https://linkedin.com/in/…"
              />
            </label>
          </div>
          {error && <p className="mc-contact-error">{error}</p>}
          <button
            className="mc-contact-submit"
            onClick={handleSubmit}
            disabled={submitting}
          >
            {submitting ? "Envoi…" : "Étudier notre projet avec ARTCB →"}
          </button>
          <p className="mc-contact-legal">
            Vos coordonnées sont transmises à l'équipe ARTCB. Traitement conforme RGPD.
            Aucun démarchage non sollicité.
          </p>
        </div>
      )}
    </div>
  );
}
