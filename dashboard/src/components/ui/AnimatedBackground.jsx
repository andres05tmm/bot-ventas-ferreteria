// -- AnimatedBackground.jsx --------------------------------------------------
// Canvas aurora + partículas rojo Ferretería Punto Rojo.
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

    const COUNT    = 50
    const MAX_DIST = 120
    let animId
    let particles  = []
    let t_anim     = 0

    function resize() {
      canvas.width  = window.innerWidth
      canvas.height = window.innerHeight
    }

    class Particle {
      constructor() { this.reset() }
      reset() {
        this.x     = Math.random() * canvas.width
        this.y     = Math.random() * canvas.height
        this.vx    = (Math.random() - 0.5) * 0.35
        this.vy    = (Math.random() - 0.5) * 0.35
        this.r     = Math.random() * 1.8 + 0.6
        this.alpha = Math.random() * 0.038 + 0.008
      }
      update() {
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

    function drawAuroras() {
      t_anim += 0.004
      const blobs = [
        {
          cx: canvas.width  * 0.15 + Math.sin(t_anim)         * 80,
          cy: canvas.height * 0.25 + Math.cos(t_anim * 0.7)   * 50,
          r:  canvas.width  * 0.40,
          a:  0.055,
        },
        {
          cx: canvas.width  * 0.82 + Math.cos(t_anim * 0.8)   * 60,
          cy: canvas.height * 0.72 + Math.sin(t_anim * 1.1)   * 40,
          r:  canvas.width  * 0.30,
          a:  0.030,
        },
        {
          cx: canvas.width  * 0.50 + Math.sin(t_anim * 0.55)  * 45,
          cy: canvas.height * 0.08 + Math.cos(t_anim * 0.9)   * 28,
          r:  canvas.width  * 0.22,
          a:  0.022,
        },
      ]

      blobs.forEach(({ cx, cy, r, a }) => {
        const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, r)
        g.addColorStop(0, `rgba(200,32,14,${a})`)
        g.addColorStop(1, 'rgba(200,32,14,0)')
        ctx.fillStyle = g
        ctx.fillRect(0, 0, canvas.width, canvas.height)
      })
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
            ctx.lineWidth   = 0.5
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
    return () => {
      cancelAnimationFrame(animId)
      window.removeEventListener('resize', resize)
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
