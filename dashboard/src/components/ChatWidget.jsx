/**
 * ChatWidget.jsx — Asistente IA Ferretería · v2
 */

import { useState, useRef, useEffect, useCallback } from 'react'

const API_BASE = import.meta.env.VITE_API_URL || ''

// ── Estilos inyectados como <style> ─────────────────────────────────────────
const CSS = `
  @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600&display=swap');

  @keyframes fw-bounce {
    0%,80%,100% { transform: scale(0.6); opacity: 0.4; }
    40%         { transform: scale(1);   opacity: 1;   }
  }
  @keyframes fw-pop {
    0%   { transform: scale(0.88) translateY(14px); opacity: 0; }
    100% { transform: scale(1)    translateY(0);    opacity: 1; }
  }
  @keyframes fw-msg {
    0%   { transform: translateY(5px); opacity: 0; }
    100% { transform: translateY(0);   opacity: 1; }
  }
  @keyframes fw-pulse {
    0%,100% { box-shadow: 0 0 0 0   rgba(200,32,14,.45), 0 4px 14px rgba(200,32,14,.4); }
    60%     { box-shadow: 0 0 0 10px rgba(200,32,14,.0),  0 4px 14px rgba(200,32,14,.4); }
  }

  /* Panel principal */
  .fw-panel {
    font-family: 'DM Sans', system-ui, sans-serif;
    position: fixed;
    bottom: 24px; right: 24px;
    z-index: 9999;
    width: 368px; height: 560px;
    border-radius: 22px;
    background: #FFFFFF;
    box-shadow: 0 4px 6px rgba(0,0,0,.04), 0 12px 28px rgba(0,0,0,.14), 0 32px 56px rgba(0,0,0,.1);
    display: flex; flex-direction: column;
    overflow: hidden;
    animation: fw-pop .24s cubic-bezier(.34,1.56,.64,1) forwards;
    border: 1px solid rgba(0,0,0,.07);
  }

  /* Header degradado rojo */
  .fw-header {
    background: linear-gradient(130deg, #B81D0C 0%, #D42010 45%, #E83520 100%);
    padding: 15px 16px 13px;
    display: flex; align-items: center; gap: 11px;
    flex-shrink: 0;
    position: relative; overflow: hidden;
  }
  .fw-header::before {
    content: ''; position: absolute;
    top: -28px; right: -16px;
    width: 90px; height: 90px; border-radius: 50%;
    background: rgba(255,255,255,.07); pointer-events: none;
  }
  .fw-header::after {
    content: ''; position: absolute;
    bottom: -22px; left: 72px;
    width: 64px; height: 64px; border-radius: 50%;
    background: rgba(255,255,255,.05); pointer-events: none;
  }

  .fw-avatar {
    width: 38px; height: 38px; border-radius: 11px;
    background: rgba(255,255,255,.18);
    border: 1px solid rgba(255,255,255,.28);
    display: flex; align-items: center; justify-content: center;
    flex-shrink: 0;
  }

  .fw-hname {
    color: #fff; font-size: 14.5px; font-weight: 600;
    letter-spacing: -.015em; line-height: 1.2;
  }
  .fw-hstatus {
    display: flex; align-items: center; gap: 5px; margin-top: 2px;
  }
  .fw-dot {
    width: 6px; height: 6px; border-radius: 50%;
    background: #86EFAC; box-shadow: 0 0 0 2px rgba(134,239,172,.28);
    transition: background .3s;
  }
  .fw-dot.busy { background: #FCD34D; box-shadow: 0 0 0 2px rgba(252,211,77,.25); }
  .fw-hstatus span {
    color: rgba(255,255,255,.75); font-size: 11.5px; font-weight: 400;
  }

  .fw-hbtn {
    font-family: inherit;
    background: rgba(255,255,255,.12); border: 1px solid rgba(255,255,255,.18);
    border-radius: 7px; padding: 4px 9px;
    color: rgba(255,255,255,.82); font-size: 11px; font-weight: 500;
    cursor: pointer; transition: background .15s;
  }
  .fw-hbtn:hover { background: rgba(255,255,255,.22); }

  .fw-xbtn {
    background: rgba(255,255,255,.13); border: 1px solid rgba(255,255,255,.2);
    border-radius: 8px; width: 28px; height: 28px;
    display: flex; align-items: center; justify-content: center;
    cursor: pointer; color: rgba(255,255,255,.88);
    transition: background .15s; flex-shrink: 0;
  }
  .fw-xbtn:hover { background: rgba(255,255,255,.24); }

  /* Área de mensajes */
  .fw-msgs {
    flex: 1; overflow-y: auto;
    padding: 14px 13px;
    display: flex; flex-direction: column; gap: 3px;
    background: #F7F6F4;
    scroll-behavior: smooth;
  }
  .fw-msgs::-webkit-scrollbar { width: 3px; }
  .fw-msgs::-webkit-scrollbar-thumb { background: rgba(0,0,0,.1); border-radius: 4px; }

  /* Pantalla de bienvenida */
  .fw-welcome {
    flex: 1; display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    text-align: center; padding: 20px; gap: 5px;
  }
  .fw-wicon {
    width: 50px; height: 50px; border-radius: 15px;
    background: linear-gradient(135deg, #B81D0C, #E83520);
    display: flex; align-items: center; justify-content: center;
    margin-bottom: 6px;
    box-shadow: 0 6px 18px rgba(200,32,14,.28);
  }
  .fw-wtitle {
    font-size: 15.5px; font-weight: 600;
    color: #1A1A1A; letter-spacing: -.02em;
  }
  .fw-wsub {
    font-size: 12.5px; line-height: 1.55;
    color: #888; max-width: 230px; margin-top: 2px;
  }
  .fw-chips {
    display: flex; flex-wrap: wrap; gap: 6px;
    justify-content: center; margin-top: 12px;
  }
  .fw-chip {
    font-family: inherit;
    font-size: 12px; font-weight: 500;
    padding: 5px 12px; border-radius: 20px;
    border: 1.5px solid rgba(200,32,14,.28);
    color: #B81D0C; background: rgba(200,32,14,.05);
    cursor: pointer; transition: all .15s; white-space: nowrap;
  }
  .fw-chip:hover {
    background: rgba(200,32,14,.1); border-color: rgba(200,32,14,.45);
    transform: translateY(-1px);
  }

  /* Burbujas */
  .fw-row {
    display: flex; flex-direction: column;
    animation: fw-msg .16s ease forwards;
  }
  .fw-row.u { align-items: flex-end;   margin-top: 7px; }
  .fw-row.b { align-items: flex-start; margin-top: 7px; }

  .fw-bbl {
    max-width: 82%; padding: 9px 13px;
    font-size: 13.5px; line-height: 1.55;
    white-space: pre-wrap; word-break: break-word;
  }
  .fw-bbl.u {
    background: linear-gradient(135deg, #B81D0C 0%, #D93018 100%);
    color: #fff;
    border-radius: 17px 17px 4px 17px;
    box-shadow: 0 2px 8px rgba(180,30,12,.28);
  }
  .fw-bbl.b {
    background: #FFFFFF; color: #1A1A1A;
    border-radius: 17px 17px 17px 4px;
    border: 1px solid rgba(0,0,0,.07);
    box-shadow: 0 1px 4px rgba(0,0,0,.06);
  }

  .fw-badge {
    font-size: 11.5px; font-weight: 500;
    color: #166534; background: #F0FDF4;
    border: 1px solid #BBF7D0; border-radius: 20px;
    padding: 3px 10px; margin-top: 5px;
  }

  /* Indicador de escritura */
  .fw-typing {
    display: flex; align-items: center; gap: 4px;
    padding: 11px 15px; margin-top: 7px;
    background: #FFFFFF; align-self: flex-start;
    border-radius: 17px 17px 17px 4px;
    border: 1px solid rgba(0,0,0,.07);
    box-shadow: 0 1px 4px rgba(0,0,0,.05);
    animation: fw-msg .16s ease forwards;
  }
  .fw-td {
    width: 7px; height: 7px; border-radius: 50%;
    background: #C8200E; opacity: .45;
    animation: fw-bounce 1.2s infinite;
  }
  .fw-td:nth-child(2) { animation-delay: .15s; }
  .fw-td:nth-child(3) { animation-delay: .30s; }

  /* Footer */
  .fw-footer {
    padding: 9px 11px 11px;
    background: #FFFFFF;
    border-top: 1px solid rgba(0,0,0,.07);
    display: flex; gap: 7px; align-items: flex-end;
    flex-shrink: 0;
  }

  .fw-iwrap {
    flex: 1; background: #F2F1EF;
    border-radius: 13px; border: 1.5px solid transparent;
    transition: border-color .15s, background .15s;
    display: flex; align-items: flex-end;
  }
  .fw-iwrap:focus-within {
    border-color: rgba(180,30,12,.38); background: #FFF;
  }

  .fw-ta {
    width: 100%; resize: none; border: none;
    background: transparent; padding: 8px 11px;
    font-family: 'DM Sans', system-ui, sans-serif;
    font-size: 13.5px; line-height: 1.45;
    color: #1A1A1A; outline: none;
    max-height: 96px; min-height: 36px;
    overflow-y: auto;
  }
  .fw-ta::placeholder { color: #B0ABA5; }
  .fw-ta::-webkit-scrollbar { display: none; }

  .fw-sbtn {
    width: 38px; height: 38px; border-radius: 11px;
    border: none; cursor: pointer; flex-shrink: 0;
    display: flex; align-items: center; justify-content: center;
    background: linear-gradient(135deg, #B81D0C, #D93018);
    color: #fff; transition: opacity .15s, transform .1s;
    box-shadow: 0 3px 10px rgba(180,30,12,.3);
  }
  .fw-sbtn:hover:not(:disabled) { opacity: .88; transform: scale(1.05); }
  .fw-sbtn:active:not(:disabled) { transform: scale(.95); }
  .fw-sbtn:disabled {
    background: #DDDAD6; box-shadow: none; cursor: default;
    color: #aaa;
  }

  /* FAB */
  .fw-fab {
    position: fixed; bottom: 24px; right: 24px;
    z-index: 9999;
    width: 56px; height: 56px; border-radius: 17px;
    background: linear-gradient(135deg, #B81D0C 0%, #D93018 60%, #E84020 100%);
    border: none; cursor: pointer;
    display: flex; align-items: center; justify-content: center;
    box-shadow: 0 4px 14px rgba(180,30,12,.42), 0 1px 4px rgba(0,0,0,.18);
    animation: fw-pulse 2.8s ease infinite;
    transition: transform .15s, box-shadow .15s;
    position: fixed;
  }
  .fw-fab:hover {
    transform: scale(1.07) translateY(-1px);
    box-shadow: 0 8px 22px rgba(180,30,12,.5), 0 2px 6px rgba(0,0,0,.2);
    animation: none;
  }
  .fw-fab:active { transform: scale(.95); }
  .fw-fab-dot {
    position: absolute; top: -3px; right: -3px;
    width: 11px; height: 11px; border-radius: 50%;
    background: #22C55E; border: 2px solid #fff;
  }
`

let _cssInjected = false
function injectCSS() {
  if (_cssInjected || document.getElementById('fw-css')) return
  _cssInjected = true
  const el = document.createElement('style')
  el.id = 'fw-css'
  el.textContent = CSS
  document.head.appendChild(el)
}

// ── Íconos ───────────────────────────────────────────────────────────────────
const IcoWrench = ({ s = 20, c = 'white' }) => (
  <svg width={s} height={s} viewBox="0 0 24 24" fill="none"
    stroke={c} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M14.7 6.3a1 1 0 000 1.4l1.6 1.6a1 1 0 001.4 0l3.77-3.77a6 6 0 01-7.94 7.94l-6.91 6.91a2.12 2.12 0 01-3-3l6.91-6.91a6 6 0 017.94-7.94l-3.76 3.76z"/>
  </svg>
)

const IcoX = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
    <path d="M18 6L6 18M6 6l12 12"/>
  </svg>
)

const IcoSend = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
    <line x1="22" y1="2" x2="11" y2="13"/>
    <polygon points="22 2 15 22 11 13 2 9 22 2"/>
  </svg>
)

const IcoFab = () => (
  <svg width="25" height="25" viewBox="0 0 24 24" fill="none"
    stroke="white" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/>
    <line x1="8" y1="10" x2="16" y2="10"/>
    <line x1="8" y1="14" x2="13" y2="14"/>
  </svg>
)

const CHIPS = ['Inventario bajo', 'Total hoy', 'Estado de caja', 'Registrar gasto']

// ── Componente ───────────────────────────────────────────────────────────────
export default function ChatWidget({ nombreUsuario = 'Dashboard' }) {
  const [open, setOpen]           = useState(false)
  const [input, setInput]         = useState('')
  const [loading, setLoading]     = useState(false)
  const [messages, setMessages]   = useState([])
  const [historial, setHistorial] = useState([])

  const endRef   = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => { injectCSS() }, [])
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, loading])
  useEffect(() => { if (open) setTimeout(() => inputRef.current?.focus(), 280) }, [open])

  const resize = (el) => {
    if (!el) return
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 96) + 'px'
  }

  const enviar = useCallback(async (override) => {
    const texto = (override || input).trim()
    if (!texto || loading) return

    setMessages(p => [...p, { role: 'user', content: texto }])
    const prev = [...historial]
    setHistorial(p => [...p, { role: 'user', content: `${nombreUsuario}: ${texto}` }])
    setInput('')
    if (inputRef.current) inputRef.current.style.height = '36px'
    setLoading(true)

    try {
      const res = await fetch(`${API_BASE}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mensaje: texto, nombre: nombreUsuario, historial: prev }),
      })
      if (!res.ok) {
        const e = await res.json().catch(() => ({}))
        throw new Error(e.detail || `Error ${res.status}`)
      }
      const data = await res.json()
      const respuesta = data.respuesta || '(Sin respuesta)'
      setMessages(p => [...p, { role: 'assistant', content: respuesta, acciones: data.acciones }])
      setHistorial(p => [...p, { role: 'assistant', content: respuesta }])
    } catch (err) {
      setMessages(p => [...p, { role: 'assistant', content: `⚠️ ${err.message}` }])
    } finally {
      setLoading(false)
      setTimeout(() => inputRef.current?.focus(), 60)
    }
  }, [input, loading, historial, nombreUsuario])

  const onKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); enviar() }
  }

  // FAB
  if (!open) return (
    <button className="fw-fab" onClick={() => setOpen(true)} title="Asistente IA">
      <IcoFab />
      <div className="fw-fab-dot" />
    </button>
  )

  // Panel
  return (
    <div className="fw-panel">

      {/* Header */}
      <div className="fw-header">
        <div className="fw-avatar"><IcoWrench s={20} /></div>
        <div style={{ flex: 1 }}>
          <div className="fw-hname">Asistente Ferretería</div>
          <div className="fw-hstatus">
            <div className={`fw-dot${loading ? ' busy' : ''}`} />
            <span>{loading ? 'Procesando...' : 'En línea'}</span>
          </div>
        </div>
        {messages.length > 0 && (
          <button className="fw-hbtn"
            onClick={() => { setMessages([]); setHistorial([]) }}>
            Limpiar
          </button>
        )}
        <button className="fw-xbtn" onClick={() => setOpen(false)}><IcoX /></button>
      </div>

      {/* Mensajes */}
      <div className="fw-msgs">
        {messages.length === 0 && !loading ? (
          <div className="fw-welcome">
            <div className="fw-wicon"><IcoWrench s={24} /></div>
            <div className="fw-wtitle">¿En qué te ayudo?</div>
            <div className="fw-wsub">
              Registra ventas, consulta inventario, revisa la caja, gestiona gastos y más.
            </div>
            <div className="fw-chips">
              {CHIPS.map(c => (
                <button key={c} className="fw-chip" onClick={() => enviar(c)}>{c}</button>
              ))}
            </div>
          </div>
        ) : (
          <>
            {messages.map((m, i) => (
              <div key={i} className={`fw-row ${m.role === 'user' ? 'u' : 'b'}`}>
                <div className={`fw-bbl ${m.role === 'user' ? 'u' : 'b'}`}>{m.content}</div>
                {m.acciones && (m.acciones.ventas > 0 || m.acciones.gastos > 0) && (
                  <div className="fw-badge">
                    ✓ {[
                      m.acciones.ventas > 0 && `${m.acciones.ventas} venta(s) registrada(s)`,
                      m.acciones.gastos > 0 && `${m.acciones.gastos} gasto(s) registrado(s)`,
                    ].filter(Boolean).join(' · ')}
                  </div>
                )}
              </div>
            ))}
            {loading && (
              <div className="fw-typing">
                <div className="fw-td" /><div className="fw-td" /><div className="fw-td" />
              </div>
            )}
          </>
        )}
        <div ref={endRef} />
      </div>

      {/* Input */}
      <div className="fw-footer">
        <div className="fw-iwrap">
          <textarea
            ref={inputRef}
            className="fw-ta"
            value={input}
            onChange={e => { setInput(e.target.value); resize(e.target) }}
            onKeyDown={onKey}
            placeholder="Escribe un mensaje…"
            rows={1}
            disabled={loading}
          />
        </div>
        <button className="fw-sbtn" onClick={() => enviar()}
          disabled={!input.trim() || loading} title="Enviar (Enter)">
          <IcoSend />
        </button>
      </div>
    </div>
  )
}
