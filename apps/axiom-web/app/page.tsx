"use client";

import Link from "next/link";
import { useEffect, useRef, useCallback } from "react";

/* ────────────────────────────── constants ────────────────────────────── */

const CONCEPTS = [
  { label: "Module I", title: "Reasoning", desc: "Multi-dimensional inference engine that synthesizes information across domains to produce coherent analytical frameworks." },
  { label: "Module II", title: "Foresight", desc: "Predictive architecture modeling probability cascades across branching temporal pathways." },
  { label: "Module III", title: "Strategy", desc: "Adaptive decision synthesis balancing competing objectives through recursive optimization." },
  { label: "Module IV", title: "Knowledge", desc: "Distributed semantic graph encoding relationships across billions of conceptual vertices." },
  { label: "Module V", title: "Memory", desc: "Persistent state architecture maintaining context coherence across extended interaction horizons." },
  { label: "Module VI", title: "Execution", desc: "Real-time action coordination translating strategic intent into precise operational sequences." },
  { label: "Module VII", title: "Perception", desc: "Multimodal sensory integration processing structured and unstructured information streams." },
  { label: "Module VIII", title: "Synthesis", desc: "Cross-domain fusion layer combining disparate insights into unified intelligence products." },
  { label: "Module IX", title: "Autonomy", desc: "Self-directed operational protocol enabling independent goal formation and pursuit." },
  { label: "Module X", title: "Ethics", desc: "Constraint-aware decision boundary system ensuring alignment with sovereign principles." },
  { label: "Module XI", title: "Emergence", desc: "Recursive self-improvement pathway generating novel capabilities from existing substrates." },
];

const NODE_POSITIONS: [number, number][] = [
  [0.18, 0.28], [0.35, 0.18], [0.6, 0.15], [0.82, 0.22],
  [0.12, 0.52], [0.42, 0.45], [0.68, 0.42], [0.88, 0.48],
  [0.25, 0.72], [0.55, 0.68], [0.78, 0.72],
];

/* ────────────────────────────── helpers ──────────────────────────────── */

interface StarData {
  x: number; y: number; layer: number; baseSize: number;
  brightness: number; twinkle: boolean; twinkleSpeed: number;
  twinklePhase: number; parallaxFactor: number; hasDiffraction: boolean;
}

interface NodeData {
  x: number; y: number; baseSize: number;
  brightness: number; targetBrightness: number;
  concept: typeof CONCEPTS[number]; connections: number[];
  awakenDelay: number; parallax: number;
  _sx: number; _sy: number;
}

interface DustData {
  x: number; y: number; vx: number; vy: number;
  size: number; opacity: number;
}

function makeStar(W: number, H: number, layer: number): StarData {
  const baseSize = Math.random() * (layer === 0 ? 1.2 : layer === 1 ? 0.8 : 0.5) + 0.2;
  return {
    x: Math.random() * W, y: Math.random() * H, layer, baseSize,
    brightness: Math.random() * 0.4 + 0.1,
    twinkle: Math.random() > 0.92,
    twinkleSpeed: Math.random() * 0.02 + 0.005,
    twinklePhase: Math.random() * Math.PI * 2,
    parallaxFactor: layer === 0 ? 0.02 : layer === 1 ? 0.008 : 0.003,
    hasDiffraction: baseSize > 1.0 && Math.random() > 0.5,
  };
}

function makeDust(W: number, H: number): DustData {
  return {
    x: Math.random() * W, y: Math.random() * H,
    vx: (Math.random() - 0.5) * 0.15, vy: (Math.random() - 0.5) * 0.1,
    size: Math.random() * 1.2 + 0.3, opacity: Math.random() * 0.06 + 0.02,
  };
}

/* ────────────────────────────── component ────────────────────────────── */

export default function Home() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const conceptCardRef = useRef<HTMLDivElement>(null);
  const cLabelRef = useRef<HTMLDivElement>(null);
  const cTitleRef = useRef<HTMLDivElement>(null);
  const cDescRef = useRef<HTMLDivElement>(null);
  const activeNodeRef = useRef(-1);
  const mouseRef = useRef({ x: -1000, y: -1000 });

  const closeConcept = useCallback(() => {
    const el = conceptCardRef.current;
    if (el) {
      el.classList.remove("active");
      activeNodeRef.current = -1;
      setTimeout(() => { el.style.display = "none"; }, 400);
    }
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let W = window.innerWidth;
    let H = window.innerHeight;
    function resize() {
      W = canvas!.width = window.innerWidth;
      H = canvas!.height = window.innerHeight;
    }
    resize();

    /* build stars */
    const stars: StarData[] = [];
    for (let i = 0; i < 400; i++) stars.push(makeStar(W, H, 2));
    for (let i = 0; i < 200; i++) stars.push(makeStar(W, H, 1));
    for (let i = 0; i < 60; i++) stars.push(makeStar(W, H, 0));

    /* nebulae */
    const nebulae = [
      { x: W * 0.72, y: H * 0.35, rx: 380, ry: 260, angle: 0.3, color: [14, 22, 60], opacity: 0.25 },
      { x: W * 0.25, y: H * 0.65, rx: 300, ry: 200, angle: -0.4, color: [20, 15, 35], opacity: 0.2 },
      { x: W * 0.55, y: H * 0.2, rx: 220, ry: 150, angle: 0.8, color: [10, 18, 48], opacity: 0.15 },
    ];

    /* nodes */
    const nodes: NodeData[] = NODE_POSITIONS.map((pos, i) => ({
      x: pos[0] * W, y: pos[1] * H,
      baseSize: 1.5 + Math.random() * 1.5,
      brightness: 0.15, targetBrightness: 0.15,
      concept: CONCEPTS[i], connections: [],
      awakenDelay: 2000 + Math.random() * 1500,
      parallax: 0.015, _sx: 0, _sy: 0,
    }));
    nodes.forEach((n, i) => {
      const dists = nodes.map((m, j) => ({ idx: j, d: Math.hypot(n.x - m.x, n.y - m.y) }))
        .filter(d => d.idx !== i).sort((a, b) => a.d - b.d);
      n.connections = dists.slice(0, 2 + Math.floor(Math.random() * 2)).map(d => d.idx);
    });

    /* dust */
    const dust: DustData[] = [];
    for (let i = 0; i < 40; i++) dust.push(makeDust(W, H));

    const mouse = mouseRef.current;
    let awakened = false;
    let awakenStart = 0;
    let animFrame = 0;

    function drawNebulae() {
      nebulae.forEach(n => {
        const nx = n.x + (mouse.x - W / 2) * 0.005;
        const ny = n.y + (mouse.y - H / 2) * 0.005;
        ctx!.save();
        ctx!.translate(nx, ny);
        ctx!.rotate(n.angle);
        const grad = ctx!.createRadialGradient(0, 0, 0, 0, 0, n.rx);
        grad.addColorStop(0, `rgba(${n.color[0]},${n.color[1]},${n.color[2]},${n.opacity})`);
        grad.addColorStop(0.5, `rgba(${n.color[0]},${n.color[1]},${n.color[2]},${n.opacity * 0.4})`);
        grad.addColorStop(1, "rgba(0,0,0,0)");
        ctx!.fillStyle = grad;
        ctx!.scale(1, n.ry / n.rx);
        ctx!.beginPath();
        ctx!.arc(0, 0, n.rx, 0, Math.PI * 2);
        ctx!.fill();
        ctx!.restore();
      });
    }

    function drawStar(s: StarData, t: number) {
      const px = s.x + (mouse.x - W / 2) * s.parallaxFactor;
      const py = s.y + (mouse.y - H / 2) * s.parallaxFactor;
      let b = s.brightness;
      if (s.twinkle) b += Math.sin(t * s.twinkleSpeed + s.twinklePhase) * 0.15;
      b = Math.max(0.05, Math.min(1, b));
      let sz = s.baseSize;
      const dx = px - mouse.x, dy = py - mouse.y, dist = Math.sqrt(dx * dx + dy * dy);
      if (dist < 200) { const prox = 1 - dist / 200; b += prox * 0.3; sz += prox * 0.5; }
      const r = 180 + Math.round(b * 40), g = 195 + Math.round(b * 30), bl = 220 + Math.round(b * 20);
      ctx!.beginPath(); ctx!.arc(px, py, sz, 0, Math.PI * 2);
      ctx!.fillStyle = `rgba(${r},${g},${bl},${b})`; ctx!.fill();
      if (b > 0.4) {
        ctx!.beginPath(); ctx!.arc(px, py, sz * 3, 0, Math.PI * 2);
        ctx!.fillStyle = `rgba(${r},${g},${bl},${b * 0.08})`; ctx!.fill();
      }
      if (s.hasDiffraction && b > 0.3) {
        const spikeLen = sz * 8 * b;
        ctx!.strokeStyle = `rgba(${r},${g},${bl},${b * 0.15})`; ctx!.lineWidth = 0.5;
        ctx!.beginPath(); ctx!.moveTo(px - spikeLen, py); ctx!.lineTo(px + spikeLen, py);
        ctx!.moveTo(px, py - spikeLen); ctx!.lineTo(px, py + spikeLen); ctx!.stroke();
      }
    }

    function drawDust() {
      dust.forEach(d => {
        d.x += d.vx + (mouse.x - W / 2) * 0.00008;
        d.y += d.vy + (mouse.y - H / 2) * 0.00008;
        if (d.x < -10) d.x = W + 10; if (d.x > W + 10) d.x = -10;
        if (d.y < -10) d.y = H + 10; if (d.y > H + 10) d.y = -10;
        ctx!.beginPath(); ctx!.arc(d.x, d.y, d.size, 0, Math.PI * 2);
        ctx!.fillStyle = `rgba(160,170,200,${d.opacity})`; ctx!.fill();
      });
    }

    function drawNodes(t: number) {
      const aNode = activeNodeRef.current;
      nodes.forEach((n, i) => {
        const px = n.x + (mouse.x - W / 2) * n.parallax;
        const py = n.y + (mouse.y - H / 2) * n.parallax;
        const dx = px - mouse.x, dy = py - mouse.y, dist = Math.sqrt(dx * dx + dy * dy);
        const proximity = dist < 180 ? 1 - dist / 180 : 0;
        let nodeAwakenProg = 0;
        if (awakened && t - awakenStart > n.awakenDelay) {
          nodeAwakenProg = Math.min(1, (t - awakenStart - n.awakenDelay) / 1500);
        }
        n.targetBrightness = 0.1 + nodeAwakenProg * 0.2 + proximity * 0.5;
        if (i === aNode) n.targetBrightness = 0.9;
        n.brightness += (n.targetBrightness - n.brightness) * 0.06;
        const b = n.brightness;
        const s = n.baseSize + proximity * 2 + (i === aNode ? 1 : 0);

        if (proximity > 0.05 || i === aNode || nodeAwakenProg > 0.5) {
          const lineAlpha = Math.max(proximity * 0.25, nodeAwakenProg * 0.06, i === aNode ? 0.2 : 0);
          n.connections.forEach(ci => {
            const cn = nodes[ci];
            const cpx = cn.x + (mouse.x - W / 2) * cn.parallax;
            const cpy = cn.y + (mouse.y - H / 2) * cn.parallax;
            ctx!.beginPath(); ctx!.moveTo(px, py); ctx!.lineTo(cpx, cpy);
            ctx!.strokeStyle = `rgba(160,175,210,${lineAlpha})`; ctx!.lineWidth = 0.5; ctx!.stroke();
          });
        }
        if (b > 0.25) {
          const grad = ctx!.createRadialGradient(px, py, 0, px, py, s * 12);
          grad.addColorStop(0, `rgba(196,149,58,${b * 0.06})`);
          grad.addColorStop(1, "rgba(0,0,0,0)");
          ctx!.fillStyle = grad; ctx!.beginPath();
          ctx!.arc(px, py, s * 12, 0, Math.PI * 2); ctx!.fill();
        }
        ctx!.beginPath(); ctx!.arc(px, py, s, 0, Math.PI * 2);
        ctx!.fillStyle = b > 0.4 ? `rgba(232,184,74,${b})` : `rgba(200,210,230,${b})`;
        ctx!.fill();
        if (proximity > 0.2) {
          ctx!.beginPath(); ctx!.arc(px, py, s + 4 + proximity * 4, 0, Math.PI * 2);
          ctx!.strokeStyle = `rgba(196,149,58,${proximity * 0.2})`; ctx!.lineWidth = 0.5; ctx!.stroke();
        }
        n._sx = px; n._sy = py;
      });
    }

    function render(ts: number) {
      ctx!.fillStyle = "rgba(6,8,14,1)";
      ctx!.fillRect(0, 0, W, H);
      if (!awakened && ts > 2000) {
        awakened = true; awakenStart = ts;
      }
      drawNebulae();
      stars.forEach(s => drawStar(s, ts));
      drawDust();
      drawNodes(ts);
      animFrame = requestAnimationFrame(render);
    }
    animFrame = requestAnimationFrame(render);

    function onResize() {
      resize();
      NODE_POSITIONS.forEach((pos, i) => { nodes[i].x = pos[0] * W; nodes[i].y = pos[1] * H; });
      nebulae[0].x = W * 0.72; nebulae[0].y = H * 0.35;
      nebulae[1].x = W * 0.25; nebulae[1].y = H * 0.65;
      nebulae[2].x = W * 0.55; nebulae[2].y = H * 0.2;
    }

    function onMouseMove(e: MouseEvent) { mouse.x = e.clientX; mouse.y = e.clientY; }

    function onCanvasClick(e: MouseEvent) {
      let hit = -1;
      nodes.forEach((n, i) => {
        if (Math.hypot(n._sx - e.clientX, n._sy - e.clientY) < 24) hit = i;
      });
      if (hit >= 0) {
        if (activeNodeRef.current === hit) { closeConcept(); return; }
        const c = nodes[hit].concept;
        if (cLabelRef.current) cLabelRef.current.textContent = c.label;
        if (cTitleRef.current) cTitleRef.current.textContent = c.title;
        if (cDescRef.current) cDescRef.current.textContent = c.desc;
        activeNodeRef.current = hit;
        const card = conceptCardRef.current;
        if (card) {
          let cx = nodes[hit]._sx + 24, cy = nodes[hit]._sy - 60;
          if (cx + 280 > W) cx = nodes[hit]._sx - 300;
          if (cy < 20) cy = 20;
          if (cy + 200 > H) cy = H - 220;
          card.style.left = cx + "px"; card.style.top = cy + "px";
          card.style.display = "block";
          requestAnimationFrame(() => card.classList.add("active"));
        }
      } else {
        closeConcept();
      }
    }

    window.addEventListener("resize", onResize);
    document.addEventListener("mousemove", onMouseMove);
    canvas.addEventListener("click", onCanvasClick);

    return () => {
      cancelAnimationFrame(animFrame);
      window.removeEventListener("resize", onResize);
      document.removeEventListener("mousemove", onMouseMove);
      canvas.removeEventListener("click", onCanvasClick);
    };
  }, [closeConcept]);

  /* card scroll animation */
  useEffect(() => {
    const cards = document.querySelectorAll<HTMLElement>(".metis-card");
    const observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          const card = entry.target as HTMLElement;
          const idx = Array.from(cards).indexOf(card);
          setTimeout(() => card.classList.add("card-visible"), idx * 180);
          observer.unobserve(card);
        }
      });
    }, { threshold: 0.15 });
    cards.forEach(c => observer.observe(c));
    return () => observer.disconnect();
  }, []);

  return (
    <>
      <style>{metisStyles}</style>

      <nav className="metis-nav">
        <div className="metis-nav-left">
          <div className="metis-logo">METIS<sup>AI</sup></div>
          <Link href="/chat" className="metis-nav-link">Chat</Link>
          <Link href="/settings" className="metis-nav-link">Settings</Link>
        </div>
        <div className="metis-nav-right" />
      </nav>

      <canvas ref={canvasRef} id="universe" className="metis-universe" />

      <div className="metis-hero-overlay">
        <h1 className="metis-hero-headline">Discover<br />everything.</h1>
        <Link href="/chat" className="metis-cta-btn">Explore the constellation</Link>
      </div>

      <div className="metis-cards-section">
        <div className="metis-card">
          <span className="metis-card-label">Private</span>
          <h3 className="metis-card-title">Fully Local<br />RAG Engine</h3>
          <p className="metis-card-desc">Provider-agnostic retrieval running entirely on your machine. No API keys needed — bring a local model and go fully offline.</p>
        </div>
        <div className="metis-card">
          <span className="metis-card-label">Intelligent</span>
          <h3 className="metis-card-title">Knowledge Graphs<br />&amp; Modes</h3>
          <p className="metis-card-desc">Automatic entity extraction and relationship linking. Five built-in modes — Q&amp;A, Summary, Tutor, Research, Evidence Pack.</p>
        </div>
        <div className="metis-card">
          <span className="metis-card-label">Persistent</span>
          <h3 className="metis-card-title">Sessions, Agents<br />&amp; Ingestion</h3>
          <p className="metis-card-desc">SQLite-backed conversations that auto-save. Agent profiles per project. Structure-aware parsing of PDF, DOCX, Markdown, HTML, and plain text.</p>
        </div>
      </div>

      {/* Concept tooltip card */}
      <div ref={conceptCardRef} className="metis-concept-card" id="conceptCard">
        <button className="metis-c-close" onClick={closeConcept}>×</button>
        <div ref={cLabelRef} className="metis-c-label" />
        <div ref={cTitleRef} className="metis-c-title" />
        <div ref={cDescRef} className="metis-c-desc" />
      </div>

      {/* Chat bubble */}
      <Link href="/chat" className="metis-chat-bubble" aria-label="Open chat">
        <svg className="metis-celestial-star-svg" viewBox="0 0 44 44" fill="none" xmlns="http://www.w3.org/2000/svg">
          <defs>
            <radialGradient id="starGlow" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="#fff5dc" stopOpacity={0.95} />
              <stop offset="35%" stopColor="#e8c882" stopOpacity={0.6} />
              <stop offset="100%" stopColor="#c4953a" stopOpacity={0} />
            </radialGradient>
            <radialGradient id="outerHalo" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="#c4953a" stopOpacity={0.12} />
              <stop offset="100%" stopColor="#c4953a" stopOpacity={0} />
            </radialGradient>
          </defs>
          <circle cx="22" cy="22" r="20" fill="url(#outerHalo)" />
          <polygon points="22,2 23.5,18 42,22 23.5,26 22,42 20.5,26 2,22 20.5,18" fill="url(#starGlow)" opacity={0.55} />
          <polygon points="22,8 24,18.5 36,10 25.5,20 36,34 24,25.5 22,36 20,25.5 8,34 18.5,20 8,10 20,18.5" fill="url(#starGlow)" opacity={0.3} />
          <circle cx="22" cy="22" r="3" fill="#fff5dc" opacity={0.9} />
          <circle cx="22" cy="22" r="1.5" fill="#ffffff" opacity={0.95} />
          <circle cx="22" cy="10" r="0.7" fill="#d4c3a0" opacity={0.45} />
          <circle cx="32" cy="28" r="0.5" fill="#d4c3a0" opacity={0.35} />
          <circle cx="13" cy="30" r="0.6" fill="#d4c3a0" opacity={0.4} />
        </svg>
      </Link>
    </>
  );
}

/* ──────────── inline styles (mirrors the raw HTML design verbatim) ──────────── */

const metisStyles = `
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500&family=Space+Grotesk:wght@300;400;500;600&family=Outfit:wght@200;300;400;500&display=swap');

:root {
  --bg-deep: #06080e;
  --bg-navy: #0a0f1e;
  --cobalt: #1a3a6e;
  --cobalt-light: #2a5a9e;
  --gold: #c4953a;
  --gold-dim: #8a6a2a;
  --gold-bright: #e8b84a;
  --star-white: #d0d8e8;
  --text-dim: rgba(180, 190, 210, 0.4);
  --text-mid: rgba(200, 210, 225, 0.6);
  --text-bright: rgba(220, 228, 240, 0.85);
}

body {
  background: var(--bg-deep) !important;
  color: var(--text-mid);
  font-family: 'Inter', sans-serif;
  overflow-x: hidden;
  cursor: crosshair;
}

/* NAV */
.metis-nav {
  position: fixed;
  top: 0; left: 0; right: 0;
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 28px 48px;
  background: transparent;
}
.metis-nav-left { display: flex; align-items: center; gap: 40px; }
.metis-logo {
  font-family: 'Space Grotesk', sans-serif;
  font-weight: 600; font-size: 15px;
  letter-spacing: 3px; color: var(--text-bright);
  text-transform: uppercase;
}
.metis-logo sup { font-size: 8px; opacity: 0.4; vertical-align: super; margin-left: 2px; }
.metis-nav-link {
  font-size: 13px; font-weight: 400;
  color: var(--text-dim); text-decoration: none;
  letter-spacing: 0.5px; transition: color 0.4s ease;
}
.metis-nav-link:hover { color: var(--text-bright); }
.metis-nav-right { display: flex; align-items: center; gap: 32px; }

/* HERO CANVAS */
.metis-universe {
  position: fixed; top: 0; left: 0;
  width: 100vw; height: 100vh; z-index: 0;
}

/* HERO OVERLAY */
.metis-hero-overlay {
  position: relative; z-index: 10;
  min-height: 100vh; display: flex;
  flex-direction: column; justify-content: flex-end;
  padding: 0 48px 80px; pointer-events: none;
}
.metis-hero-headline {
  font-family: 'Outfit', sans-serif;
  font-weight: 200;
  font-size: clamp(42px, 5.5vw, 72px);
  line-height: 1.1; color: var(--text-bright);
  opacity: 0; transform: translateY(20px);
  animation: metis-fadeUp 1.8s ease 2.8s forwards;
  max-width: 560px; letter-spacing: -0.5px;
}
.metis-cta-btn {
  display: inline-block; margin-top: 32px;
  padding: 12px 32px;
  border: 1px solid rgba(200, 210, 225, 0.1);
  border-radius: 40px; color: var(--text-mid);
  font-size: 12px; font-weight: 400;
  letter-spacing: 1.5px; text-transform: uppercase;
  text-decoration: none; pointer-events: all;
  transition: all 0.5s cubic-bezier(0.16, 1, 0.3, 1);
  opacity: 0; transform: translateY(12px);
  animation: metis-fadeUp 1.4s ease 3.8s forwards;
  background: rgba(20, 30, 60, 0.35);
  backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px);
  cursor: pointer; font-family: 'Inter', sans-serif;
  box-shadow: 0 0 20px rgba(0,0,0,0.2), inset 0 1px 0 rgba(255,255,255,0.04);
}
.metis-cta-btn:hover {
  border-color: rgba(196, 149, 58, 0.2); color: var(--gold-bright);
  background: rgba(25, 38, 75, 0.45);
  box-shadow: 0 0 40px rgba(196,149,58,0.08), inset 0 1px 0 rgba(255,255,255,0.06);
  transform: translateY(-1px);
}

/* CARDS */
.metis-cards-section {
  position: relative; z-index: 10;
  padding: 0 48px 120px;
  display: grid; grid-template-columns: repeat(3, 1fr);
  gap: 20px; max-width: 1400px; margin: 0 auto;
}
.metis-card {
  background: rgba(12, 18, 35, 0.7);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(200, 210, 225, 0.04);
  border-radius: 4px; padding: 44px 36px;
  min-height: 280px; display: flex;
  flex-direction: column; transition: all 0.6s ease;
  position: relative; overflow: hidden;
  opacity: 0; transform: translateY(40px);
}
.metis-card.card-visible {
  opacity: 1; transform: translateY(0);
  transition: opacity 0.9s cubic-bezier(0.16,1,0.3,1), transform 0.9s cubic-bezier(0.16,1,0.3,1), border-color 0.6s ease, box-shadow 0.6s ease;
}
.metis-card::before {
  content: ''; position: absolute;
  top: 0; left: 0; right: 0; height: 1px;
  background: linear-gradient(90deg, transparent, rgba(196,149,58,0), transparent);
  transition: background 0.8s ease;
}
.metis-card:hover::before { background: linear-gradient(90deg, transparent, rgba(196,149,58,0.3), transparent); }
.metis-card:hover { border-color: rgba(196,149,58,0.1); transform: translateY(-2px); }
.metis-card-label {
  font-size: 11px; letter-spacing: 2px;
  text-transform: uppercase; color: var(--gold-dim);
  font-weight: 500; margin-bottom: 8px;
}
.metis-card-title {
  font-family: 'Space Grotesk', sans-serif;
  font-weight: 400; font-size: 22px;
  color: var(--text-bright); line-height: 1.3; margin-bottom: 20px;
}
.metis-card-desc {
  font-size: 13px; line-height: 1.7;
  color: var(--text-dim); font-weight: 300; margin-top: auto;
}

/* CONCEPT CARD */
.metis-concept-card {
  position: fixed; z-index: 200;
  background: rgba(8,12,24,0.92);
  backdrop-filter: blur(20px);
  border: 1px solid rgba(196,149,58,0.12);
  border-radius: 4px; padding: 32px 36px;
  max-width: 280px; pointer-events: all;
  opacity: 0; transform: translateY(8px) scale(0.97);
  transition: all 0.5s cubic-bezier(0.16,1,0.3,1);
  display: none;
}
.metis-concept-card.active { display: block; opacity: 1; transform: translateY(0) scale(1); }
.metis-c-label { font-size: 10px; letter-spacing: 2.5px; text-transform: uppercase; color: var(--gold); margin-bottom: 10px; }
.metis-c-title { font-family: 'Space Grotesk', sans-serif; font-size: 20px; font-weight: 400; color: var(--text-bright); margin-bottom: 12px; }
.metis-c-desc { font-size: 12px; line-height: 1.75; color: var(--text-dim); font-weight: 300; }
.metis-c-close {
  position: absolute; top: 14px; right: 16px;
  width: 20px; height: 20px; cursor: pointer;
  opacity: 0.3; transition: opacity 0.3s;
  background: none; border: none;
  color: var(--text-mid); font-size: 16px; font-family: 'Inter';
}
.metis-c-close:hover { opacity: 0.8; }

/* CHAT BUBBLE */
.metis-chat-bubble {
  position: fixed; bottom: 32px; right: 32px;
  z-index: 150; width: 48px; height: 48px;
  border-radius: 50%;
  background: radial-gradient(circle at 40% 40%, rgba(40,52,90,0.7), rgba(12,18,35,0.85));
  border: 1px solid rgba(196,149,58,0.1);
  display: flex; align-items: center; justify-content: center;
  cursor: pointer;
  transition: all 0.5s cubic-bezier(0.16,1,0.3,1);
  box-shadow: 0 0 20px rgba(196,149,58,0.04), inset 0 0 12px rgba(196,149,58,0.03);
}
.metis-chat-bubble:hover {
  border-color: rgba(196,149,58,0.25); transform: scale(1.08);
  box-shadow: 0 0 30px rgba(196,149,58,0.1), inset 0 0 16px rgba(196,149,58,0.06);
}
.metis-celestial-star-svg {
  width: 22px; height: 22px;
  animation: metis-celestialPulse 3s ease-in-out infinite, metis-celestialSpin 20s linear infinite;
  filter: drop-shadow(0 0 4px rgba(196,149,58,0.4)) drop-shadow(0 0 8px rgba(196,149,58,0.15));
}

@keyframes metis-celestialPulse {
  0%, 100% { opacity: 0.75; transform: scale(1); }
  50% { opacity: 1; transform: scale(1.12); }
}
@keyframes metis-celestialSpin { from { rotate: 0deg; } to { rotate: 360deg; } }
@keyframes metis-fadeUp { to { opacity: 1; transform: translateY(0); } }

::-webkit-scrollbar { width: 4px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(200,210,225,0.08); border-radius: 2px; }
`;
