import React, { useEffect, useRef, useState, useCallback } from 'react';

const SELFIE_STEPS = [
  { id: 'center', label: 'Mira de frente',       emoji: '😐', duration: 3000 },
  { id: 'left',   label: 'Gira a la izquierda',  emoji: '👈', duration: 3000 },
  { id: 'right',  label: 'Gira a la derecha',    emoji: '👉', duration: 3000 },
  { id: 'up',     label: 'Mira hacia arriba',     emoji: '👆', duration: 2800 },
  { id: 'smile',  label: '¡Sonríe!',              emoji: '😁', duration: 2500 },
];
const DOC_STABLE_MS = 10000;

function scoreDoc(ctx, x, y, w, h) {
  const imageData = ctx.getImageData(x, y, w, h).data;
  let sum = 0, sumSq = 0, n = 0;
  for (let i = 0; i < imageData.length; i += 16) {
    const g = imageData[i] * 0.299 + imageData[i + 1] * 0.587 + imageData[i + 2] * 0.114;
    sum += g; sumSq += g * g; n++;
  }
  const mean = sum / n;
  const variance = sumSq / n - mean * mean;
  const stdDev = Math.sqrt(Math.max(0, variance));
  const brightOk = mean > 55 && mean < 225 ? 1 : 0.2;
  return Math.min(1, stdDev / 42) * brightOk;
}

export default function CameraCapture({ mode = 'selfie', onCapture, onClose }) {
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const streamRef = useRef(null);
  const capturedRef = useRef(false);
  const rafRef = useRef(null);
  const stepTimerRef = useRef(null);
  const docStableRef = useRef(null);

  const [ready, setReady] = useState(false);
  const [error, setError] = useState(null);
  const [flash, setFlash] = useState(false);
  const [captured, setCaptured] = useState(false);

  // Selfie state
  const [stepIdx, setStepIdx] = useState(0);
  const [stepPct, setStepPct] = useState(0);
  const stepStartRef = useRef(null);

  // Document state
  const [docScore, setDocScore] = useState(0);
  const [docStablePct, setDocStablePct] = useState(0);
  const docScoreRef = useRef(0);

  const doCapture = useCallback(() => {
    if (capturedRef.current || !videoRef.current) return;
    capturedRef.current = true;
    setFlash(true);
    setTimeout(() => setFlash(false), 250);
    setCaptured(true);

    const video = videoRef.current;
    const cvs = document.createElement('canvas');
    cvs.width = video.videoWidth || 640;
    cvs.height = video.videoHeight || 480;
    const ctx = cvs.getContext('2d');
    if (mode === 'selfie') {
      ctx.translate(cvs.width, 0);
      ctx.scale(-1, 1);
    }
    ctx.drawImage(video, 0, 0, cvs.width, cvs.height);
    const dataUrl = cvs.toDataURL('image/jpeg', 0.88);
    streamRef.current?.getTracks().forEach(t => t.stop());
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    if (stepTimerRef.current) clearTimeout(stepTimerRef.current);
    if (docStableRef.current) clearInterval(docStableRef.current);
    setTimeout(() => onCapture(dataUrl), 500);
  }, [mode, onCapture]);

  // Use ref to break circular dependency between advanceStep ↔ scheduleNextStep
  const advanceStepRef = useRef(null);

  const scheduleNextStep = useCallback((idx) => {
    if (stepTimerRef.current) clearTimeout(stepTimerRef.current);
    const dur = SELFIE_STEPS[idx]?.duration ?? 2000;
    stepTimerRef.current = setTimeout(() => advanceStepRef.current?.(), dur);
  }, []);

  const advanceStep = useCallback(() => {
    setStepIdx(prev => {
      const next = prev + 1;
      if (next >= SELFIE_STEPS.length) {
        doCapture();
        return prev;
      }
      stepStartRef.current = performance.now();
      setStepPct(0);
      scheduleNextStep(next);
      return next;
    });
  }, [doCapture, scheduleNextStep]);

  // Keep ref in sync
  useEffect(() => { advanceStepRef.current = advanceStep; }, [advanceStep]);

  // RAF loop for progress animation and doc scoring
  useEffect(() => {
    if (!ready || captured) return;

    const tick = () => {
      const now = performance.now();

      if (mode === 'selfie') {
        if (stepStartRef.current !== null) {
          const elapsed = now - stepStartRef.current;
          const dur = SELFIE_STEPS[stepIdx]?.duration ?? 2000;
          setStepPct(Math.min(100, (elapsed / dur) * 100));
        }
      } else {
        // Document mode: analyse canvas
        const video = videoRef.current;
        const canvas = canvasRef.current;
        if (video && canvas && video.readyState >= 2) {
          const ctx = canvas.getContext('2d');
          canvas.width = video.videoWidth || 640;
          canvas.height = video.videoHeight || 480;
          ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
          const vw = canvas.width, vh = canvas.height;
          const gw = Math.floor(vw * 0.72), gh = Math.floor(vw * 0.45);
          const gx = Math.floor((vw - gw) / 2), gy = Math.floor((vh - gh) / 2);
          const score = scoreDoc(ctx, gx, gy, gw, gh);
          docScoreRef.current = score;
          setDocScore(score);
        }
      }

      rafRef.current = requestAnimationFrame(tick);
    };

    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [ready, captured, mode, stepIdx]);

  // Doc stable timer
  useEffect(() => {
    if (mode !== 'document' || captured) return;
    if (docScore >= 0.55) {
      if (!docStableRef.current) {
        const start = performance.now();
        const interval = setInterval(() => {
          if (docScoreRef.current < 0.55) {
            clearInterval(interval);
            docStableRef.current = null;
            setDocStablePct(0);
            return;
          }
          const pct = Math.min(100, ((performance.now() - start) / DOC_STABLE_MS) * 100);
          setDocStablePct(pct);
          if (pct >= 100) {
            clearInterval(interval);
            docStableRef.current = null;
            doCapture();
          }
        }, 50);
        docStableRef.current = interval;
      }
    } else {
      if (docStableRef.current) {
        clearInterval(docStableRef.current);
        docStableRef.current = null;
      }
      setDocStablePct(0);
    }
  }, [docScore, mode, captured, doCapture]);

  // Start camera
  useEffect(() => {
    let cancelled = false;
    async function start() {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: mode === 'selfie' ? 'user' : 'environment', width: { ideal: 1280 }, height: { ideal: 720 } },
          audio: false,
        });
        if (cancelled) { stream.getTracks().forEach(t => t.stop()); return; }
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          videoRef.current.onloadedmetadata = () => {
            videoRef.current.play();
            setReady(true);
            if (mode === 'selfie') {
              stepStartRef.current = performance.now();
              scheduleNextStep(0);
            }
          };
        }
      } catch (e) {
        if (!cancelled) setError('No se pudo acceder a la cámara. Verifica los permisos.');
      }
    }
    start();
    return () => {
      cancelled = true;
      streamRef.current?.getTracks().forEach(t => t.stop());
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      if (stepTimerRef.current) clearTimeout(stepTimerRef.current);
      if (docStableRef.current) clearInterval(docStableRef.current);
    };
  }, []); // eslint-disable-line

  const step = SELFIE_STEPS[stepIdx];

  // SVG progress ring
  const RING_R = 130;
  const RING_CIRC = 2 * Math.PI * RING_R;

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 9999,
      background: 'rgba(0,0,0,0.97)',
      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
    }}>
      {/* Flash overlay */}
      {flash && (
        <div style={{
          position: 'absolute', inset: 0, background: 'white', zIndex: 10001,
          opacity: flash ? 1 : 0, transition: 'opacity 0.25s',
          pointerEvents: 'none',
        }} />
      )}

      {/* Close */}
      <button onClick={onClose} style={{
        position: 'absolute', top: 20, right: 20, zIndex: 10002,
        background: 'rgba(255,255,255,0.15)', border: 'none', borderRadius: '50%',
        width: 44, height: 44, cursor: 'pointer', color: 'white', fontSize: 22,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>✕</button>

      {error ? (
        <div style={{ color: '#ff6b6b', textAlign: 'center', padding: 32, maxWidth: 300 }}>
          <div style={{ fontSize: 48, marginBottom: 16 }}>📷</div>
          <p style={{ color: 'white', marginBottom: 8, fontWeight: 600 }}>Sin acceso a cámara</p>
          <p style={{ color: '#aaa', fontSize: 14 }}>{error}</p>
          <button onClick={onClose} style={{
            marginTop: 20, background: '#0a55ff', color: 'white', border: 'none',
            borderRadius: 12, padding: '12px 28px', cursor: 'pointer', fontSize: 15,
          }}>Cerrar</button>
        </div>
      ) : (
        <>
          {/* Title */}
          <p style={{ color: 'rgba(255,255,255,0.7)', fontSize: 13, marginBottom: 16, letterSpacing: 0.5, textTransform: 'uppercase' }}>
            {mode === 'selfie' ? 'Verificación facial' : 'Escanear documento'}
          </p>

          {/* Camera + guide container */}
          <div style={{ position: 'relative', width: 300, height: mode === 'selfie' ? 300 : 200 }}>
            {/* Hidden canvas for doc analysis */}
            <canvas ref={canvasRef} style={{ display: 'none' }} />

            {/* Video */}
            <video
              ref={videoRef}
              autoPlay
              playsInline
              muted
              style={{
                width: '100%', height: '100%',
                objectFit: 'cover',
                borderRadius: mode === 'selfie' ? '50%' : 16,
                transform: mode === 'selfie' ? 'scaleX(-1)' : 'none',
                display: 'block',
              }}
            />

            {/* Selfie: SVG oval guide + progress ring */}
            {mode === 'selfie' && (
              <svg
                style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', overflow: 'visible' }}
                viewBox="0 0 300 300"
              >
                {/* Dark mask outside oval */}
                <defs>
                  <mask id="oval-mask">
                    <rect width="300" height="300" fill="white" />
                    <ellipse cx="150" cy="150" rx="130" ry="130" fill="black" />
                  </mask>
                </defs>
                <rect width="300" height="300" fill="rgba(0,0,0,0.45)" mask="url(#oval-mask)" />
                {/* Progress ring */}
                <circle
                  cx="150" cy="150" r={RING_R}
                  fill="none" stroke="rgba(255,255,255,0.15)" strokeWidth="3"
                />
                <circle
                  cx="150" cy="150" r={RING_R}
                  fill="none" stroke="#4ade80" strokeWidth="3"
                  strokeDasharray={RING_CIRC}
                  strokeDashoffset={RING_CIRC * (1 - stepPct / 100)}
                  strokeLinecap="round"
                  transform="rotate(-90 150 150)"
                  style={{ transition: 'stroke-dashoffset 0.1s linear' }}
                />
              </svg>
            )}

            {/* Document: corner markers */}
            {mode === 'document' && (
              <svg style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }} viewBox="0 0 300 200">
                {[
                  [10, 10, 'M10,40 L10,10 L40,10'],
                  [260, 10, 'M260,10 L290,10 L290,40'],
                  [10, 160, 'M10,160 L10,190 L40,190'],
                  [260, 160, 'M290,160 L290,190 L260,190'],
                ].map(([, , d], i) => (
                  <path key={i} d={d} fill="none"
                    stroke={docScore >= 0.55 ? '#4ade80' : 'white'}
                    strokeWidth="3" strokeLinecap="round"
                    style={{ transition: 'stroke 0.3s' }}
                  />
                ))}
              </svg>
            )}
          </div>

          {/* Selfie: step label */}
          {mode === 'selfie' && !captured && (
            <div style={{ marginTop: 28, textAlign: 'center' }}>
              <div style={{ fontSize: 42, marginBottom: 8 }}>{step?.emoji}</div>
              <p style={{ color: 'white', fontSize: 20, fontWeight: 600, margin: 0 }}>{step?.label}</p>
              <p style={{ color: 'rgba(255,255,255,0.5)', fontSize: 13, marginTop: 6 }}>
                Paso {stepIdx + 1} de {SELFIE_STEPS.length}
              </p>
            </div>
          )}

          {/* Document: score feedback + stability bar */}
          {mode === 'document' && !captured && (
            <div style={{ marginTop: 24, textAlign: 'center', width: 300 }}>
              <p style={{ color: 'white', fontSize: 17, fontWeight: 600, margin: '0 0 6px' }}>
                {docScore >= 0.55
                  ? docStablePct >= 100 ? '¡Capturando!' : 'Documento detectado — mantén firme'
                  : docScore >= 0.3
                    ? 'Acerca el documento al marco'
                    : 'Coloca tu cédula dentro del marco'}
              </p>
              {/* Stability bar */}
              <div style={{
                height: 5, borderRadius: 3, overflow: 'hidden',
                background: 'rgba(255,255,255,0.15)', marginTop: 10,
              }}>
                <div style={{
                  height: '100%',
                  width: `${docStablePct}%`,
                  background: docStablePct >= 80 ? '#4ade80' : '#facc15',
                  borderRadius: 3,
                  transition: 'width 0.1s linear, background 0.3s',
                }} />
              </div>
              <p style={{ color: 'rgba(255,255,255,0.4)', fontSize: 12, marginTop: 6 }}>
                {docStablePct > 0 ? 'Analizando...' : 'Detección automática activa'}
              </p>
            </div>
          )}

          {/* Captured confirmation */}
          {captured && (
            <div style={{ marginTop: 28, textAlign: 'center' }}>
              <div style={{ fontSize: 42 }}>✅</div>
              <p style={{ color: '#4ade80', fontSize: 18, fontWeight: 600, marginTop: 8 }}>
                {mode === 'selfie' ? '¡Selfie capturada!' : '¡Documento capturado!'}
              </p>
            </div>
          )}

          {/* Manual capture fallback */}
          {!captured && ready && (
            <button onClick={doCapture} style={{
              marginTop: 24,
              background: 'rgba(255,255,255,0.12)', border: '1px solid rgba(255,255,255,0.25)',
              borderRadius: 14, padding: '10px 28px', color: 'rgba(255,255,255,0.7)',
              cursor: 'pointer', fontSize: 14,
            }}>
              Capturar manualmente
            </button>
          )}

          {!ready && !error && (
            <p style={{ color: 'rgba(255,255,255,0.5)', marginTop: 20, fontSize: 14 }}>
              Iniciando cámara...
            </p>
          )}
        </>
      )}
    </div>
  );
}
