/** WebAuthn helpers — fingerprint / Face ID / Windows Hello. No raw biometric leaves the device.
 *  R384 : validation des options avant tout appel navigator.credentials pour éviter les crashes
 *  "undefined.challenge" causés par une réponse API mal structurée ou absente.
 */

function bufToB64u(buf: ArrayBuffer): string {
  const bytes = new Uint8Array(buf);
  let bin = "";
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function b64uToBuf(text: string): ArrayBuffer {
  const pad = "=".repeat((4 - (text.length % 4)) % 4);
  const b64 = (text + pad).replace(/-/g, "+").replace(/_/g, "/");
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out.buffer;
}

export function webauthnSupported(): boolean {
  return typeof window !== "undefined" && !!window.PublicKeyCredential;
}

export async function platformAuthenticatorAvailable(): Promise<boolean> {
  if (!webauthnSupported()) return false;
  try {
    return await PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable();
  } catch {
    return false;
  }
}

type JsonOptions = Record<string, unknown>;

/**
 * R384 — Valide que les options WebAuthn reçues du serveur sont exploitables
 * avant tout appel à navigator.credentials. Lance une erreur explicite si une
 * propriété obligatoire est absente ou invalide, plutôt qu'un crash
 * "undefined.challenge" opaque dans le moteur JS.
 */
function validateWebAuthnOptions(publicKey: unknown, context: "create" | "get"): JsonOptions {
  if (publicKey === null || publicKey === undefined) {
    throw new Error(
      `webauthn_options_missing : le serveur n'a pas renvoyé publicKey (contexte=${context}). ` +
      "Vérifiez que le wallet existe et que la credential est bien enregistrée sur ce nœud."
    );
  }
  if (typeof publicKey !== "object" || Array.isArray(publicKey)) {
    throw new Error(`webauthn_options_invalid : publicKey doit être un objet (contexte=${context})`);
  }
  const opts = publicKey as JsonOptions;
  if (typeof opts.challenge !== "string" || opts.challenge.length === 0) {
    throw new Error(
      `webauthn_challenge_missing : publicKey.challenge absent ou vide (contexte=${context}). ` +
      "Le serveur n'a peut-être pas trouvé la credential pour ce wallet."
    );
  }
  return opts;
}

function decodeCreateOptions(publicKey: JsonOptions): PublicKeyCredentialCreationOptions {
  const user = publicKey.user as Record<string, string>;
  return {
    ...publicKey,
    challenge: b64uToBuf(publicKey.challenge as string),
    user: {
      ...user,
      id: b64uToBuf(user.id),
    },
    excludeCredentials: ((publicKey.excludeCredentials as Array<{ id: string; type: PublicKeyCredentialType }>) || []).map(
      (c) => ({ ...c, id: b64uToBuf(c.id) }),
    ),
  } as PublicKeyCredentialCreationOptions;
}

function decodeRequestOptions(publicKey: JsonOptions): PublicKeyCredentialRequestOptions {
  return {
    ...publicKey,
    challenge: b64uToBuf(publicKey.challenge as string),
    allowCredentials: ((publicKey.allowCredentials as Array<{ id: string; type: PublicKeyCredentialType }>) || []).map(
      (c) => ({ ...c, id: b64uToBuf(c.id) }),
    ),
  } as PublicKeyCredentialRequestOptions;
}

export function serializeCredential(cred: PublicKeyCredential): {
  id: string;
  rawId: string;
  type: string;
  response: Record<string, string>;
  authenticatorAttachment?: string | null;
} {
  const resp = cred.response as AuthenticatorAttestationResponse | AuthenticatorAssertionResponse;
  const payload: Record<string, string> = {
    clientDataJSON: bufToB64u(resp.clientDataJSON),
  };
  if ("attestationObject" in resp) {
    payload.attestationObject = bufToB64u(resp.attestationObject);
  }
  if ("authenticatorData" in resp) {
    payload.authenticatorData = bufToB64u(resp.authenticatorData);
    payload.signature = bufToB64u(resp.signature);
    if (resp.userHandle) payload.userHandle = bufToB64u(resp.userHandle);
  }
  return {
    id: cred.id,
    rawId: bufToB64u(cred.rawId),
    type: cred.type,
    response: payload,
    authenticatorAttachment: cred.authenticatorAttachment,
  };
}

export async function createPlatformCredential(publicKey: unknown): Promise<PublicKeyCredential> {
  // R384 — valider avant d'appeler decodeCreateOptions pour éviter undefined.challenge
  const validated = validateWebAuthnOptions(publicKey, "create");
  const cred = await navigator.credentials.create({ publicKey: decodeCreateOptions(validated) });
  if (!cred || cred.type !== "public-key") {
    throw new Error("webauthn_create_cancelled");
  }
  return cred as PublicKeyCredential;
}

export async function getPlatformCredential(publicKey: unknown): Promise<PublicKeyCredential> {
  // R384 — valider avant d'appeler decodeRequestOptions pour éviter undefined.challenge
  const validated = validateWebAuthnOptions(publicKey, "get");
  const cred = await navigator.credentials.get({ publicKey: decodeRequestOptions(validated) });
  if (!cred || cred.type !== "public-key") {
    throw new Error("webauthn_get_cancelled");
  }
  return cred as PublicKeyCredential;
}
