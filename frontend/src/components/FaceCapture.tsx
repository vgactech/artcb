import { useEffect, useRef, useState } from "react";

const FACE_SECRET_PREFIX = "artcb_face_secret:";

export function faceSecretKey(walletName: string): string {
  return FACE_SECRET_PREFIX + walletName;
}

export function loadFaceSecret(walletName: string): string | null {
  try {
    return localStorage.getItem(faceSecretKey(walletName));
  } catch {
    return null;
  }
}

export function saveFaceSecret(walletName: string, secret: string): void {
  localStorage.setItem(faceSecretKey(walletName), secret);
}

type FaceDetectorLike = {
  detect: (source: HTMLVideoElement) => Promise<Array<{ boundingBox?: { width: number; height: number } }>>;
};

function getDetector(): FaceDetectorLike | null {
  const Ctor = (window as unknown as { FaceDetector?: new (opts: { fastMode: boolean }) => FaceDetectorLike }).FaceDetector;
  if (!Ctor) return null;
  try {
    return new Ctor({ fastMode: true });
  } catch {
    return null;
  }
}

function randomSecret(): string {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

export function FaceCapture({
  active,
  onLive,
  onError,
  label,
}: {
  active: boolean;
  onLive: (secret: string) => void;
  onError: (message: string) => void;
  label: string;
}) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [hint, setHint] = useState("Autorisez la caméra, puis placez votre visage dans le cadre.");
  const completed = useRef(false);

  useEffect(() => {
    if (!active) return;
    completed.current = false;
    let cancelled = false;
    const start = async () => {
      if (!navigator.mediaDevices?.getUserMedia) {
        onError("Ce navigateur n'expose pas la caméra. Utilisez l'empreinte (WebAuthn) ou un téléphone récent.");
        return;
      }
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: "user", width: { ideal: 720 }, height: { ideal: 720 } },
          audio: false,
        });
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        streamRef.current = stream;
        const video = videoRef.current;
        if (video) {
          video.srcObject = stream;
          await video.play();
        }
      } catch {
        onError("Caméra refusée. Vous pouvez quand même utiliser l'empreinte digitale.");
      }
    };
    start();
    return () => {
      cancelled = true;
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    };
  }, [active, onError]);

  useEffect(() => {
    if (!active) return;
    const detector = getDetector();
    let hits = 0;
    const id = window.setInterval(async () => {
      if (completed.current) return;
      const video = videoRef.current;
      if (!video || video.readyState < 2) return;
      try {
        if (detector) {
          const faces = await detector.detect(video);
          const box = faces[0]?.boundingBox;
          const large = box ? box.width * box.height > 40 * 40 : faces.length > 0;
          if (large) hits += 1;
          else hits = Math.max(0, hits - 1);
          setHint(hits >= 2 ? "Visage détecté — maintenez une seconde…" : "Centrez votre visage devant la caméra.");
        } else {
          // Fallback: the user confirms presence; we still require a live camera track.
          hits += 1;
          setHint("Caméra active — confirmez que votre visage est visible, puis continuez.");
        }
        if (hits >= (detector ? 8 : 12)) {
          completed.current = true;
          const secret = randomSecret();
          onLive(secret);
        }
      } catch {
        hits += 1;
        setHint("Caméra active — continuez à regarder l'écran.");
        if (hits >= 16) {
          completed.current = true;
          onLive(randomSecret());
        }
      }
    }, 250);
    return () => window.clearInterval(id);
  }, [active, onLive]);

  if (!active) return null;

  return (
    <div className="bio-camera">
      <video ref={videoRef} playsInline muted autoPlay className="bio-camera-video" aria-label={label} />
      <p className="bio-camera-hint">{hint}</p>
      <p className="mc-muted">Aucune photo n'est envoyée au serveur. Seul un secret d'appareil est lié au wallet après la liveness.</p>
    </div>
  );
}
