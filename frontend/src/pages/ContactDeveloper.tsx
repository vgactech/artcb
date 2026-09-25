import { useState } from "react";

// R468 — Tunnel de contact pour les développeurs
// Questions techniques : stack, objectif intégration, environnement

interface DevFormData {
  integration_goal: string;
  stack: string;
  env: string;
  name: string;
  email: string;
  github: string;
  linkedin: string;
}

const INTEGRATION_GOALS = [
  { value: "api", label: "Utiliser l'API ARTCB" },
  { value: "build_integration", label: "Développer une intégration" },
  { value: "run_node", label: "Exécuter un nœud" },
  { value: "build_agent", label: "Construire un agent IA" },
  { value: "contribute", label: "Contribuer au protocole" },
  { value: "other", label: "Autre" },
];

const STACKS = [
  { value: "python", label: "Python" },
  { value: "javascript", label: "JavaScript / TypeScript" },
  { value: "rust", label: "Rust" },
  { value: "go", label: "Go" },
  { value: "c_cpp", label: "C / C++" },
  { value: "other", label: "Autre" },
];

const ENVS = [
  { value: "prototype", label: "Prototype / Exploration" },
  { value: "production", label: "Production" },
  { value: "research", label: "Recherche" },
  { value: "infrastructure", label: "Infrastructure / DevOps" },
];

const TOTAL_STEPS = 4;

export function ContactDeveloper() {
  const [step, setStep] = useState(0);
  const [form, setForm] = useState<DevFormData>({
    integration_goal: "",
    stack: "",
    env: "",
    name: "",
    email: "",
    github: "",
    linkedin: "",
  });
  const [submitted, setSubmitted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const progress = Math.round((step / TOTAL_STEPS) * 100);

  const selectOption = (field: keyof DevFormData, value: string) => {
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
          contact_type: "developer",
          integration_goal: form.integration_goal,
          stack: form.stack,
          env: form.env,
          name: form.name,
          email: form.email,
          github: form.github,
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
            Merci <strong>{form.name || "à vous"}</strong>. Notre équipe technique
            vous contactera à l'adresse <strong>{form.email}</strong>.
          </p>
          <p className="mc-contact-text mc-contact-muted">
            Profil : Développeur · {STACKS.find(s => s.value === form.stack)?.label ?? form.stack}
            {form.integration_goal ? ` · ${INTEGRATION_GOALS.find(g => g.value === form.integration_goal)?.label ?? form.integration_goal}` : ""}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="mc-contact-tunnel">
      <div className="mc-contact-header">
        <span className="mc-contact-badge mc-contact-badge-dev">DEV</span>
        <h1 className="mc-contact-title">ARTCB pour les développeurs</h1>
        <p className="mc-contact-subtitle">
          Explorez les possibilités d'intégration, les API, les composants et l'infrastructure ARTCB.
        </p>
        <div className="mc-contact-progress">
          <div className="mc-contact-progress-bar" style={{ width: `${progress}%` }} />
        </div>
        <p className="mc-contact-step-label">Étape {step + 1} sur {TOTAL_STEPS}</p>
      </div>

      {/* Étape 0 : objectif intégration */}
      {step === 0 && (
        <div className="mc-contact-step">
          <h2 className="mc-contact-question">Que voulez-vous faire avec ARTCB ?</h2>
          <div className="mc-contact-options">
            {INTEGRATION_GOALS.map((g) => (
              <button
                key={g.value}
                className="mc-contact-option"
                onClick={() => selectOption("integration_goal", g.value)}
              >
                {g.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Étape 1 : stack */}
      {step === 1 && (
        <div className="mc-contact-step">
          <h2 className="mc-contact-question">Quelle technologie utilisez-vous principalement ?</h2>
          <div className="mc-contact-options">
            {STACKS.map((s) => (
              <button
                key={s.value}
                className="mc-contact-option"
                onClick={() => selectOption("stack", s.value)}
              >
                {s.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Étape 2 : environnement */}
      {step === 2 && (
        <div className="mc-contact-step">
          <h2 className="mc-contact-question">Quel est votre environnement cible ?</h2>
          <div className="mc-contact-options">
            {ENVS.map((e) => (
              <button
                key={e.value}
                className="mc-contact-option"
                onClick={() => selectOption("env", e.value)}
              >
                {e.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Étape 3 : coordonnées */}
      {step === 3 && (
        <div className="mc-contact-step">
          <h2 className="mc-contact-question">Souhaitez-vous être contacté par un ingénieur ARTCB ?</h2>
          <p className="mc-contact-muted">
            Profil : Dev · {STACKS.find(s => s.value === form.stack)?.label} ·{" "}
            {INTEGRATION_GOALS.find(g => g.value === form.integration_goal)?.label} ·{" "}
            {ENVS.find(e => e.value === form.env)?.label}
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
                placeholder="dev@domaine.com"
                required
              />
            </label>
            <label className="mc-contact-label">
              GitHub (optionnel)
              <input
                className="mc-contact-input"
                type="url"
                value={form.github}
                onChange={(e) => setForm((f) => ({ ...f, github: e.target.value }))}
                placeholder="https://github.com/…"
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
            {submitting ? "Envoi…" : "Contacter l'équipe technique →"}
          </button>
          <p className="mc-contact-legal">
            Vos coordonnées sont transmises à l'équipe technique ARTCB uniquement.
          </p>
        </div>
      )}
    </div>
  );
}
