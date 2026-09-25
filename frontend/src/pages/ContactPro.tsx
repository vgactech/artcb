import { useState } from "react";
import { useTranslation } from "../i18n/useTranslation";

// R468 — Tunnel de contact pour les professionnels
// Formulaire conversationnel progressif : question → réponse → question suivante
// Objectif : qualifier le besoin avant de collecter les coordonnées

interface ProFormData {
  goal: string;
  sector: string;
  knowledge_level: string;
  name: string;
  email: string;
  phone: string;
  linkedin: string;
}

const GOALS = [
  { value: "discover", label: "Découvrir ARTCB" },
  { value: "use", label: "L'utiliser dans mon activité" },
  { value: "integrate", label: "L'intégrer à mes outils" },
  { value: "opportunity", label: "Explorer une opportunité" },
  { value: "other", label: "Autre" },
];

const SECTORS = [
  { value: "tech", label: "Technologie / Numérique" },
  { value: "finance", label: "Finance / Banque" },
  { value: "industry", label: "Industrie" },
  { value: "research", label: "Recherche / Académique" },
  { value: "consulting", label: "Conseil / Stratégie" },
  { value: "creative", label: "Création / Médias" },
  { value: "public", label: "Secteur public" },
  { value: "other", label: "Autre" },
];

const KNOWLEDGE_LEVELS = [
  { value: "discovering", label: "Je découvre ARTCB" },
  { value: "familiar", label: "Je connais déjà le projet" },
  { value: "technical", label: "Je suis techniquement expérimenté" },
];

const TOTAL_STEPS = 4; // 3 questions + coordonnées

export function ContactPro() {
  const { t } = useTranslation();
  const [step, setStep] = useState(0);
  const [form, setForm] = useState<ProFormData>({
    goal: "",
    sector: "",
    knowledge_level: "",
    name: "",
    email: "",
    phone: "",
    linkedin: "",
  });
  const [submitted, setSubmitted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const progress = Math.round(((step) / TOTAL_STEPS) * 100);

  const selectOption = (field: keyof ProFormData, value: string) => {
    setForm((f) => ({ ...f, [field]: value }));
    setStep((s) => s + 1);
  };

  const handleSubmit = async () => {
    if (!form.email.trim()) {
      setError("L'email est requis.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const resp = await fetch("/api/v1/contact", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          contact_type: "pro",
          goal: form.goal,
          sector: form.sector,
          knowledge_level: form.knowledge_level,
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
            Merci <strong>{form.name || "à vous"}</strong>. Nous reviendrons vers vous
            rapidement à l'adresse <strong>{form.email}</strong>.
          </p>
          <p className="mc-contact-text mc-contact-muted">
            Profil enregistré : Professionnel · {SECTORS.find(s => s.value === form.sector)?.label ?? form.sector}
            {form.knowledge_level ? ` · ${KNOWLEDGE_LEVELS.find(k => k.value === form.knowledge_level)?.label ?? form.knowledge_level}` : ""}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="mc-contact-tunnel">
      <div className="mc-contact-header">
        <span className="mc-contact-badge mc-contact-badge-pro">PRO</span>
        <h1 className="mc-contact-title">ARTCB pour les professionnels</h1>
        <p className="mc-contact-subtitle">
          Découvrez comment ARTCB peut vous apporter une valeur concrète dans votre activité.
        </p>
        <div className="mc-contact-progress">
          <div className="mc-contact-progress-bar" style={{ width: `${progress}%` }} />
        </div>
        <p className="mc-contact-step-label">Étape {step + 1} sur {TOTAL_STEPS}</p>
      </div>

      {/* Étape 0 : objectif */}
      {step === 0 && (
        <div className="mc-contact-step">
          <h2 className="mc-contact-question">Que recherchez-vous ?</h2>
          <div className="mc-contact-options">
            {GOALS.map((g) => (
              <button
                key={g.value}
                className="mc-contact-option"
                onClick={() => selectOption("goal", g.value)}
              >
                {g.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Étape 1 : secteur */}
      {step === 1 && (
        <div className="mc-contact-step">
          <h2 className="mc-contact-question">Dans quel domaine travaillez-vous ?</h2>
          <div className="mc-contact-options">
            {SECTORS.map((s) => (
              <button
                key={s.value}
                className="mc-contact-option"
                onClick={() => selectOption("sector", s.value)}
              >
                {s.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Étape 2 : niveau */}
      {step === 2 && (
        <div className="mc-contact-step">
          <h2 className="mc-contact-question">Quel est votre niveau de connaissance d'ARTCB ?</h2>
          <div className="mc-contact-options">
            {KNOWLEDGE_LEVELS.map((k) => (
              <button
                key={k.value}
                className="mc-contact-option"
                onClick={() => selectOption("knowledge_level", k.value)}
              >
                {k.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Étape 3 : coordonnées */}
      {step === 3 && (
        <div className="mc-contact-step">
          <h2 className="mc-contact-question">Comment pouvons-nous vous contacter ?</h2>
          <p className="mc-contact-muted">
            Profil : Professionnel · {GOALS.find(g => g.value === form.goal)?.label} ·{" "}
            {SECTORS.find(s => s.value === form.sector)?.label}
          </p>
          <div className="mc-contact-fields">
            <label className="mc-contact-label">
              Nom (optionnel)
              <input
                className="mc-contact-input"
                type="text"
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                placeholder="Votre nom"
              />
            </label>
            <label className="mc-contact-label">
              Email <span className="mc-contact-required">*</span>
              <input
                className="mc-contact-input"
                type="email"
                value={form.email}
                onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
                placeholder="vous@domaine.com"
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
                placeholder="+33 6 00 00 00 00"
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
            {submitting ? "Envoi…" : "Envoyer ma demande →"}
          </button>
          <p className="mc-contact-legal">
            Vos coordonnées sont transmises à l'équipe ARTCB uniquement.
            Aucune revente ni utilisation commerciale sans votre consentement.
          </p>
        </div>
      )}
    </div>
  );
}
