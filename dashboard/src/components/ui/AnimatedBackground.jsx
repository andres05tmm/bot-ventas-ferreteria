// -- AnimatedBackground.jsx --------------------------------------------------
// CSS animated gradient mesh + canvas particles — Ferretería Punto Rojo.
// Light mode: blobs CSS + partículas canvas (solo desktop).
// Dark modes: no background animado.
// Respeta prefers-reduced-motion.
// ---------------------------------------------------------------------------
import { useEffect, useRef } from 'react'
import { useTheme } from '../shared.jsx'

export default function AnimatedBackground() {
  const t         = useTheme()
  const canvasRef = useRef(null)
  const isLight   = t.id === 'caramelo'
  const noMotion  = typeof window !== 'undefined' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  const isMobile  = typeof window !== 'undefined' && window.innerWidth < 768

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || !isLight || noMotion || isMobile) return
    const ctx = canvas.getContext('2d')

    const COUNT    = 42
    const MAX_DIST = 112
    const REPEL_R  = 72
    const REPEL_F  = 0.014

    let animId
    let particles = []
    let mouse     = { x: -9999, y: -9999 }

    const resize = () => {
      canvas.width  = window.innerWidth
      canvas.height = window.innerHeight
    }
    const onMouseMove = e => { mouse.x = e.clientX; mouse.y = e.clientY }

    // Paleta cálida multicolor — más elegante que solo rojo
    const COLORS = [
      'rgba(200,32,14,',    // rojo marca
      'rgba(180,90,40,',    // ámbar cálido
      'rgba(80,120,200,',   // azul acero suave
    ]

    class Particle {
      constructor() { this.reset() }
      reset() {
        this.x     = Math.random() * canvas.width
        this.y     = Math.random() * canvas.height
        this.vx    = (Math.random() - 0.5) * 0.30
        this.vy    = (Math.random() - 0.5) * 0.30
        this.r     = Math.random() * 1.5 + 0.8
        this.alpha = Math.random() * 0.055 + 0.038
        this.col   = COLORS[Math.floor(Math.random() * COLORS.length)]
      }
      update() {
        const dx = this.x - mouse.x
        const dy = this.y - mouse.y
        const d  = Math.hypot(dx, dy)
        if (d < REPEL_R && d > 0) {
          const f = (REPEL_R - d) / REPEL_R
          this.vx += (dx / d) * f * REPEL_F
          this.vy += (dy / d) * f * REPEL_F
        }
        this.vx *= 0.996
        this.vy *= 0.996
        this.x  += this.vx
        this.y  += this.vy
        if (this.x < 0 || this.x > canvas.width)  this.vx *= -1
        if (this.y < 0 || this.y > canvas.height)  this.vy *= -1
      }
      draw() {
        ctx.beginPath()
        ctx.arc(this.x, this.y, this.r, 0, Math.PI * 2)
        ctx.fillStyle = `${this.col}${this.alpha})`
        ctx.fill()
      }
    }

    function drawConnections() {
      for (let i = 0; i < particles.length; i++) {
        for (let j = i + 1; j < particles.length; j++) {
          const dx = particles[i].x - particles[j].x
          const dy = particles[i].y - particles[j].y
          const d  = Math.hypot(dx, dy)
          if (d < MAX_DIST) {
            ctx.beginPath()
            ctx.moveTo(particles[i].x, particles[i].y)
            ctx.lineTo(particles[j].x, particles[j].y)
            ctx.strokeStyle = `rgba(200,32,14,${(1 - d / MAX_DIST) * 0.017})`
            ctx.lineWidth   = 0.35
            ctx.stroke()
          }
        }
      }
    }

    function animate() {
      ctx.clearRect(0, 0, canvas.width, canvas.height)
      particles.forEach(p => { p.update(); p.draw() })
      drawConnections()
      animId = requestAnimationFrame(animate)
    }

    resize()
    particles = Array.from({ length: COUNT }, () => new Particle())
    animate()
    window.addEventListener('resize', resize)
    window.addEventListener('mousemove', onMouseMove)
    return () => {
      cancelAnimationFrame(animId)
      window.removeEventListener('resize', resize)
      window.removeEventListener('mousemove', onMouseMove)
    }
  }, [t.id])

  if (!isLight) return null

  return (
    <>
      <style>{`
        .ab-blob {
          position: absolute;
          border-radius: 50%;
          pointer-events: none;
        }
        .ab-b1 {
          top: -18%; left: -12%;
          width: 68vw; height: 68vw;
          background: radial-gradient(circle, rgba(200,32,14,0.085) 0%, transparent 64%);
          filter: blur(48px);
          animation: abFloat1 30s ease-in-out infinite;
        }
        .ab-b2 {
          top: -2%; right: -16%;
          width: 58vw; height: 58vw;
          background: radial-gradient(circle, rgba(224,138,56,0.07) 0%, transparent 64%);
          filter: blur(56px);
          animation: abFloat2 38s ease-in-out infinite;
        }
        .ab-b3 {
          bottom: -22%; left: 22%;
          width: 62vw; height: 62vw;
          background: radial-gradient(circle, rgba(228,188,96,0.06) 0%, transparent 64%);
          filter: blur(64px);
          animation: abFloat3 34s ease-in-out infinite;
        }
        .ab-b4 {
          bottom: 6%; left: -10%;
          width: 40vw; height: 40vw;
          background: radial-gradient(circle, rgba(78,128,220,0.042) 0%, transparent 64%);
          filter: blur(48px);
          animation: abFloat4 44s ease-in-out infinite;
        }
        @keyframes abFloat1 {
          0%,100% { transform: translate(0,0) scale(1) }
          33%     { transform: translate(58px,-42px) scale(1.04) }
          66%     { transform: translate(-28px,30px) scale(0.97) }
        }
        @keyframes abFloat2 {
          0%,100% { transform: translate(0,0) scale(1) }
          33%     { transform: translate(-44px,54px) scale(0.96) }
          66%     { transform: translate(38px,-24px) scale(1.04) }
        }
        @keyframes abFloat3 {
          0%,100% { transform: translate(0,0) scale(1) }
          33%     { transform: translate(30px,44px) scale(1.03) }
          66%     { transform: translate(-50px,-18px) scale(0.98) }
        }
        @keyframes abFloat4 {
          0%,100% { transform: translate(0,0) scale(1) }
          33%     { transform: translate(-24px,-50px) scale(1.05) }
          66%     { transform: translate(34px,24px) scale(0.96) }
        }
        @media (prefers-reduced-motion: reduce) {
          .ab-blob { animation: none !important; }
        }
      `}</style>

      {/* Capa base sólida */}
      <div style={{
        position: 'fixed', inset: 0, zIndex: -3,
        background: '#F8F5F1',
        pointerEvents: 'none',
      }}/>

      {/* Blobs CSS animados */}
      <div style={{
        position: 'fixed', inset: 0, zIndex: -2,
        overflow: 'hidden', pointerEvents: 'none',
      }}>
        <div className="ab-blob ab-b1"/>
        <div className="ab-blob ab-b2"/>
        <div className="ab-blob ab-b3"/>
        <div className="ab-blob ab-b4"/>
      </div>

      {/* Canvas partículas (solo desktop) */}
      <canvas
        ref={canvasRef}
        style={{
          position: 'fixed', inset: 0,
          width: '100%', height: '100%',
          pointerEvents: 'none',
          zIndex: -1,
          willChange: 'transform',
        }}
      />
    </>
  )
}
