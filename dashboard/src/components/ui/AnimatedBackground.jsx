// -- AnimatedBackground.jsx --------------------------------------------------
// Canvas aurora + partículas con repulsión al cursor — Ferretería Punto Rojo.
// Solo activo en theme "caramelo" (light mode).
// Respeta prefers-reduced-motion — no anima si el usuario lo pidió.
// ---------------------------------------------------------------------------
import { useEffect, useRef } from 'react'
import { useTheme } from '../shared.jsx'

export default function AnimatedBackground() {
  const t         = useTheme()
  const canvasRef = useRef(null)

  useEffect(() => {
    if (t.id !== 'caramelo') return

    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')

    // Respetar prefers-reduced-motion
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return

    const COUNT    = 60
    const MAX_DIST = 120
    const REPEL_R  = 80
    const REPEL_F  = 0.018

    let animId
    let particles  = []
    let t_anim     = 0
    let mouse      = { x: -9999, y: -9999 }

    function resize() {
      canvas.width  = window.innerWidth
      canvas.height = window.innerHeight
    }

    function onMouseMove(e) {
      mouse.x = e.clientX
      mouse.y = e.clientY
    }

    class Particle {
      constructor() { this.reset() }
      reset() {
        this.x     = Math.random() * canvas.width
        this.y     = Math.random() * canvas.height
        this.vx    = (Math.random() - 0.5) * (0.2 + Math.random() * 0.4)
        this.vy    = (Math.random() - 0.5) * (0.2 + Math.random() * 0.4)
        this.r     = Math.random() * 2 + 1
        this.alpha = Math.random() * 0.07 + 0.08
      }
      update() {
        // Repulsión suave del cursor
        const dx   = this.x - mouse.x
        const dy   = this.y - mouse.y
        const dist = Math.hypot(dx, dy)
        if (dist < REPEL_R && dist > 0) {
          const force = (REPEL_R - dist) / REPEL_R
          this.vx += (dx / dist) * force * REPEL_F
          this.vy += (dy / dist) * force * REPEL_F
        }

        // Amortiguación para evitar aceleración infinita
        this.vx *= 0.995
        this.vy *= 0.995

        this.x += this.vx
        this.y += this.vy
        if (this.x < 0 || this.x > canvas.width)  this.vx *= -1
        if (this.y < 0 || this.y > canvas.height)  this.vy *= -1
      }
      draw() {
        ctx.beginPath()
        ctx.arc(this.x, this.y, this.r, 0, Math.PI * 2)
        ctx.fillStyle = `rgba(200,32,14,${this.alpha})`
        ctx.fill()
      }
    }

    // Dibuja un orbe con blur simulado vía círculos concéntricos
    function drawOrb(cx, cy, r, alpha) {
      const steps = 6
      for (let i = steps; i >= 0; i--) {
        const ratio  = i / steps
        const radius = r * ratio
        const a      = alpha * (1 - ratio) * (1 - ratio)
        const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, radius)
        g.addColorStop(0, `rgba(200,32,14,${a})`)
        g.addColorStop(1, 'rgba(200,32,14,0)')
        ctx.fillStyle = g
        ctx.fillRect(0, 0, canvas.width, canvas.height)
      }
    }

    function drawAuroras() {
      t_anim += 0.003

      const orbs = [
        {
          cx: canvas.width  * 0.15 + Math.sin(t_anim * 0.7)  * 90,
          cy: canvas.height * 0.25 + Math.cos(t_anim * 0.5)  * 60,
          r:  220,
          a:  0.13,
        },
        {
          cx: canvas.width  * 0.82 + Math.cos(t_anim * 0.6)  * 70,
          cy: canvas.height * 0.72 + Math.sin(t_anim * 0.8)  * 50,
          r:  180,
          a:  0.13,
        },
        {
          cx: canvas.width  * 0.50 + Math.sin(t_anim * 0.45) * 55,
          cy: canvas.height * 0.10 + Math.cos(t_anim * 0.65) * 35,
          r:  150,
          a:  0.13,
        },
      ]

      orbs.forEach(({ cx, cy, r, a }) => drawOrb(cx, cy, r, a))
    }

    function drawConnections() {
      for (let i = 0; i < particles.length; i++) {
        for (let j = i + 1; j < particles.length; j++) {
          const dx   = particles[i].x - particles[j].x
          const dy   = particles[i].y - particles[j].y
          const dist = Math.hypot(dx, dy)
          if (dist < MAX_DIST) {
            const alpha = (1 - dist / MAX_DIST) * 0.025
            ctx.beginPath()
            ctx.moveTo(particles[i].x, particles[i].y)
            ctx.lineTo(particles[j].x, particles[j].y)
            ctx.strokeStyle = `rgba(200,32,14,${alpha})`
            ctx.lineWidth   = 0.4
            ctx.stroke()
          }
        }
      }
    }

    function animate() {
      ctx.clearRect(0, 0, canvas.width, canvas.height)
      drawAuroras()
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

  if (t.id !== 'caramelo') return null

  return (
    <canvas
      ref={canvasRef}
      style={{
        position:      'fixed',
        inset:         0,
        width:         '100%',
        height:        '100%',
        pointerEvents: 'none',
        zIndex:        -1,
        willChange:    'transform',
      }}
    />
  )
}
