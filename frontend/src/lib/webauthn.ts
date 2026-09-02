/** WebAuthn helpers — fingerprint / Face ID / Windows Hello. No raw biometric leaves the device. */

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

export async function createPlatformCredential(publicKey: JsonOptions): Promise<PublicKeyCredential> {
  const cred = await navigator.credentials.create({ publicKey: decodeCreateOptions(publicKey) });
  if (!cred || cred.type !== "public-key") {
    throw new Error("webauthn_create_cancelled");
  }
  return cred as PublicKeyCredential;
}

export async function getPlatformCredential(publicKey: JsonOptions): Promise<PublicKeyCredential> {
  const cred = await navigator.credentials.get({ publicKey: decodeRequestOptions(publicKey) });
  if (!cred || cred.type !== "public-key") {
    throw new Error("webauthn_get_cancelled");
  }
  return cred as PublicKeyCredential;
}
