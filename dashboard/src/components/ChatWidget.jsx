/**
 * ChatWidget.jsx — Asistente de IA flotante para el Dashboard
 *
 * - Burbuja flotante en esquina inferior derecha
 * - Historial de conversación en estado React (independiente del bot de Telegram)
 * - Llama a POST /chat del backend, que usa la misma lógica de ai.py
 * - Los registros (ventas, gastos, compras) se ejecutan exactamente igual que en el bot
 */

import { useState, useRef, useEffect, useCallback } from 'react'

const API_BASE = import.meta.env.VITE_API_URL || ''

// ── Estilos en objeto (sin Tailwind, sin CSS externo) ────────────────────────
const S = {
  // Burbuja flotante
  bubble: (open) => ({
    position: 'fixed',
    bottom: '24px',
    right: '24px',
    zIndex: 9999,
    width: open ? '380px' : '56px',
    height: open ? '560px' : '56px',
    borderRadius: open ? '16px' : '50%',
    background: 'var(--color-background-secondary)',
    border: '1px solid var(--color-border-secondary)',
    boxShadow: '0 8px 32px rgba(0,0,0,0.18)',
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
    transition: 'width 0.25s cubic-bezier(.4,0,.2,1), height 0.25s cubic-bezier(.4,0,.2,1), border-radius 0.2s',
  }),

  // Botón de abrir/cerrar (cuando está cerrado)
  toggleBtn: {
    position: 'absolute',
    inset: 0,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    cursor: 'pointer',
    background: 'none',
    border: 'none',
    padding: 0,
  },

  // Header del panel
  header: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '12px 16px',
    borderBottom: '1px solid var(--color-border-tertiary)',
    flexShrink: 0,
  },

  headerInfo: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
  },

  headerTitle: {
    fontSize: '14px',
    fontWeight: 500,
    color: 'var(--color-text-primary)',
    lineHeight: 1.2,
  },

  headerSub: {
    fontSize: '11px',
    color: 'var(--color-text-tertiary)',
  },

  closeBtn: {
    background: 'none',
    border: 'none',
    cursor: 'pointer',
    color: 'var(--color-text-tertiary)',
    padding: '4px',
    borderRadius: '6px',
    display: 'flex',
    alignItems: 'center',
    lineHeight: 1,
  },

  // Área de mensajes
  messages: {
    flex: 1,
    overflowY: 'auto',
    padding: '12px 14px',
    display: 'flex',
    flexDirection: 'column',
    gap: '10px',
    scrollBehavior: 'smooth',
  },

  // Burbuja de mensaje
  msgBubble: (role) => ({
    maxWidth: '88%',
    alignSelf: role === 'user' ? 'flex-end' : 'flex-start',
    background: role === 'user'
      ? 'var(--color-background-info)'
      : 'var(--color-background-primary)',
    border: role === 'user'
      ? '1px solid var(--color-border-info)'
      : '1px solid var(--color-border-tertiary)',
    borderRadius: role === 'user' ? '14px 14px 4px 14px' : '14px 14px 14px 4px',
    padding: '9px 13px',
    fontSize: '13px',
    lineHeight: 1.55,
    color: role === 'user' ? 'var(--color-text-info)' : 'var(--color-text-primary)',
    whiteSpace: 'pre-wrap',
    wordBreak: 'break-word',
  }),

  // Indicador de escritura
  typing: {
    display: 'flex',
    gap: '4px',
    alignItems: 'center',
    padding: '10px 13px',
    alignSelf: 'flex-start',
    background: 'var(--color-background-primary)',
    border: '1px solid var(--color-border-tertiary)',
    borderRadius: '14px 14px 14px 4px',
  },

  dot: (delay) => ({
    width: '6px',
    height: '6px',
    borderRadius: '50%',
    background: 'var(--color-text-tertiary)',
    animation: 'chatDotBounce 1.2s infinite',
    animationDelay: delay,
  }),

  // Indicador de acción ejecutada (venta, gasto registrado)
  actionBadge: {
    alignSelf: 'flex-start',
    fontSize: '11px',
    color: 'var(--color-text-success)',
    background: 'var(--color-background-success)',
    border: '1px solid var(--color-border-success)',
    borderRadius: '8px',
    padding: '3px 9px',
    marginTop: '-4px',
  },

  // Footer con input
  footer: {
    padding: '10px 12px',
    borderTop: '1px solid var(--color-border-tertiary)',
    display: 'flex',
    gap: '8px',
    alignItems: 'flex-end',
    flexShrink: 0,
    background: 'var(--color-background-secondary)',
  },

  input: {
    flex: 1,
    resize: 'none',
    border: '1px solid var(--color-border-secondary)',
    borderRadius: '10px',
    padding: '8px 11px',
    fontSize: '13px',
    lineHeight: 1.4,
    background: 'var(--color-background-primary)',
    color: 'var(--color-text-primary)',
    outline: 'none',
    maxHeight: '96px',
    minHeight: '38px',
    fontFamily: 'inherit',
  },

  sendBtn: (disabled) => ({
    width: '36px',
    height: '36px',
    borderRadius: '10px',
    border: 'none',
    cursor: disabled ? 'default' : 'pointer',
    background: disabled ? 'var(--color-border-secondary)' : 'var(--color-text-info)',
    color: '#fff',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
    transition: 'background 0.15s',
  }),

  // Mensaje de bienvenida (pantalla vacía)
  welcome: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '8px',
    padding: '20px',
    textAlign: 'center',
    color: 'var(--color-text-tertiary)',
    fontSize: '13px',
  },
}

// ── Íconos SVG inline ────────────────────────────────────────────────────────
const IconBot = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="11" width="18" height="10" rx="3"/>
    <path d="M9 11V7a3 3 0 0 1 6 0v4"/>
    <circle cx="9" cy="16" r="1" fill="currentColor" stroke="none"/>
    <circle cx="15" cy="16" r="1" fill="currentColor" stroke="none"/>
  </svg>
)

const IconClose = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth="2" strokeLinecap="round">
    <path d="M18 6L6 18M6 6l12 12"/>
  </svg>
)

const IconSend = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M22 2L11 13M22 2L15 22l-4-9-9-4 20-7z"/>
  </svg>
)

const IconChat = ({ color }) => (
  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke={color || 'white'}
    strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
  </svg>
)

// ── Keyframes (inyectados una vez) ───────────────────────────────────────────
const KEYFRAMES = `
@keyframes chatDotBounce {
  0%, 80%, 100% { transform: translateY(0); opacity: 0.4; }
  40%           { transform: translateY(-5px); opacity: 1; }
}
`
let _kfInjected = false
function injectKeyframes() {
  if (_kfInjected) return
  _kfInjected = true
  const el = document.createElement('style')
  el.textContent = KEYFRAMES
  document.head.appendChild(el)
}

// ── Componente principal ─────────────────────────────────────────────────────
export default function ChatWidget({ nombreUsuario = 'Dashboard' }) {
  const [open, setOpen]       = useState(false)
  const [input, setInput]     = useState('')
  const [loading, setLoading] = useState(false)
  const [messages, setMessages] = useState([])   // [{ role, content, acciones? }]
  // Historial en formato Claude: [{ role: 'user'|'assistant', content: string }]
  const [historial, setHistorial] = useState([])

  const messagesEndRef = useRef(null)
  const inputRef       = useRef(null)

  useEffect(() => { injectKeyframes() }, [])

  // Auto-scroll al último mensaje
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  // Focus al input cuando se abre
  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 250)
  }, [open])

  // Auto-resize del textarea
  const handleInputChange = (e) => {
    setInput(e.target.value)
    e.target.style.height = 'auto'
    e.target.style.height = Math.min(e.target.scrollHeight, 96) + 'px'
  }

  const enviar = useCallback(async () => {
    const texto = input.trim()
    if (!texto || loading) return

    const msgUser = { role: 'user', content: texto }

    // Agregar mensaje del usuario a la UI
    setMessages(prev => [...prev, msgUser])
    // Agregar al historial Claude
    const nuevoHistorial = [...historial, { role: 'user', content: `${nombreUsuario}: ${texto}` }]
    setHistorial(nuevoHistorial)

    setInput('')
    if (inputRef.current) inputRef.current.style.height = '38px'
    setLoading(true)

    try {
      const res = await fetch(`${API_BASE}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          mensaje: texto,
          nombre: nombreUsuario,
          historial: historial,   // historial PREVIO (sin el mensaje actual, ai.py lo agrega)
        }),
      })

      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail || `Error ${res.status}`)
      }

      const data = await res.json()
      const respuesta = data.respuesta || '(Sin respuesta)'

      // Agregar respuesta del asistente
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: respuesta,
        acciones: data.acciones,
      }])

      // Actualizar historial con la respuesta de Claude
      setHistorial(prev => [...prev, { role: 'assistant', content: respuesta }])

    } catch (err) {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: `⚠️ Error al conectar con el asistente: ${err.message}`,
      }])
    } finally {
      setLoading(false)
      setTimeout(() => inputRef.current?.focus(), 50)
    }
  }, [input, loading, historial, nombreUsuario])

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      enviar()
    }
  }

  const limpiarChat = () => {
    setMessages([])
    setHistorial([])
  }

  // ── Render ──────────────────────────────────────────────────────────────────
  return (
    <div style={S.bubble(open)}>

      {/* ── Botón de apertura (cuando está cerrado) ── */}
      {!open && (
        <button style={S.toggleBtn} onClick={() => setOpen(true)} title="Abrir asistente IA">
          <div style={{
            width: 56, height: 56, borderRadius: '50%',
            background: 'linear-gradient(135deg, #D42010 0%, #A01808 100%)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            boxShadow: '0 4px 16px rgba(212,32,16,0.4)',
          }}>
            <IconChat color="white" />
          </div>
        </button>
      )}

      {/* ── Panel de chat (cuando está abierto) ── */}
      {open && (
        <>
          {/* Header */}
          <div style={S.header}>
            <div style={S.headerInfo}>
              <div style={{
                width: 34, height: 34, borderRadius: '50%',
                background: 'linear-gradient(135deg, #D42010 0%, #A01808 100%)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                color: 'white', flexShrink: 0,
              }}>
                <IconBot />
              </div>
              <div>
                <div style={S.headerTitle}>Asistente Ferretería</div>
                <div style={S.headerSub}>
                  {loading ? 'Escribiendo...' : 'En línea'}
                </div>
              </div>
            </div>
            <div style={{ display: 'flex', gap: '4px' }}>
              {messages.length > 0 && (
                <button
                  style={{ ...S.closeBtn, fontSize: '11px', padding: '4px 8px' }}
                  onClick={limpiarChat}
                  title="Limpiar chat"
                >
                  Limpiar
                </button>
              )}
              <button style={S.closeBtn} onClick={() => setOpen(false)} title="Cerrar">
                <IconClose />
              </button>
            </div>
          </div>

          {/* Mensajes */}
          <div style={S.messages}>
            {messages.length === 0 && !loading && (
              <div style={S.welcome}>
                <div style={{ fontSize: '28px', marginBottom: '4px' }}>🔧</div>
                <div style={{ fontWeight: 500, color: 'var(--color-text-secondary)', fontSize: '14px' }}>
                  ¿En qué te ayudo?
                </div>
                <div>
                  Puedes registrar ventas, consultar inventario, agregar gastos, revisar precios y más.
                </div>
              </div>
            )}

            {messages.map((msg, i) => (
              <div key={i} style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <div style={S.msgBubble(msg.role)}>
                  {msg.content}
                </div>
                {msg.acciones && (msg.acciones.ventas > 0 || msg.acciones.gastos > 0) && (
                  <div style={S.actionBadge}>
                    ✓ {[
                      msg.acciones.ventas > 0 && `${msg.acciones.ventas} venta(s) registrada(s)`,
                      msg.acciones.gastos > 0 && `${msg.acciones.gastos} gasto(s) registrado(s)`,
                    ].filter(Boolean).join(' · ')}
                  </div>
                )}
              </div>
            ))}

            {loading && (
              <div style={S.typing}>
                <div style={S.dot('0s')} />
                <div style={S.dot('0.2s')} />
                <div style={S.dot('0.4s')} />
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Input */}
          <div style={S.footer}>
            <textarea
              ref={inputRef}
              style={S.input}
              value={input}
              onChange={handleInputChange}
              onKeyDown={handleKeyDown}
              placeholder="Escribe un mensaje… (Enter para enviar)"
              rows={1}
              disabled={loading}
            />
            <button
              style={S.sendBtn(!input.trim() || loading)}
              onClick={enviar}
              disabled={!input.trim() || loading}
              title="Enviar"
            >
              <IconSend />
            </button>
          </div>
        </>
      )}
    </div>
  )
}
