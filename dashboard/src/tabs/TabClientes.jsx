/*
 * TabClientes — CRUD de clientes (DIAN-aware).
 * Wave 2: migrado a primitives shadcn + tokens.
 */
import { useState, useEffect, useRef, useCallback } from 'react'
import { API_BASE } from '../components/shared.jsx'
import { useAuth } from '../hooks/useAuth.js'
import { useIsMobile } from '../components/shared.jsx'
import { Card } from '@/components/ui/card.jsx'
import { Button } from '@/components/ui/button.jsx'
import { Input } from '@/components/ui/input.jsx'
import { Label } from '@/components/ui/label.jsx'
import { Badge } from '@/components/ui/badge.jsx'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog.jsx'
import {
  Search, Plus, Pencil, Trash2, Users, MapPin, Loader2, ChevronLeft, ChevronRight, AlertCircle,
} from 'lucide-react'
import { cn } from '@/lib/utils'

const TIPOS_ID      = ['CC', 'NIT', 'CE', 'PAS', 'TI', 'RC']
const TIPOS_PERSONA = ['Natural', 'Jurídica']
const LIMIT = 50

// ─────────────────────────────────────────────────────────────────────────────

function initials(nombre) {
  if (!nombre) return '?'
  const w = nombre.trim().split(/\s+/)
  return w.length === 1 ? w[0].slice(0, 2).toUpperCase() : (w[0][0] + w[1][0]).toUpperCase()
}

const AVATAR_COLORS = ['bg-primary/15 text-primary', 'bg-success/15 text-success', 'bg-info/15 text-info', 'bg-warning/15 text-warning']

function Avatar({ nombre, size = 'md' }) {
  const idx = nombre ? nombre.charCodeAt(0) % AVATAR_COLORS.length : 0
  const dim = size === 'lg' ? 'size-10 text-sm' : 'size-9 text-xs'
  return (
    <div className={cn('rounded-full grid place-items-center font-bold border border-border shrink-0', AVATAR_COLORS[idx], dim)}>
      {initials(nombre)}
    </div>
  )
}

function TipoIdBadge({ tipo }) {
  return (
    <span className={cn(
      'inline-block text-[10px] font-bold px-1.5 py-0.5 rounded border',
      tipo === 'NIT' ? 'bg-info/10 text-info border-info/30' :
      tipo === 'CE'  ? 'bg-warning/10 text-warning border-warning/30' :
      'bg-primary-soft text-primary border-primary/30',
    )}>{tipo}</span>
  )
}

// ─────────────────────────────────────────────────────────────────────────────

// Exportado para reuso desde TabVentasRapidas (creación de cliente inline en el POS).
// Cuando `cliente` es null, `nombreInicial` pre-rellena el campo nombre.
export function ModalCliente({ cliente, nombreInicial = '', onClose, onGuardado, authFetch }) {
  const esEdit = !!cliente
  const [form, setForm] = useState({
    nombre:         cliente?.['Nombre tercero']  || nombreInicial || '',
    tipo_id:        cliente?.['Tipo ID']         || 'CC',
    identificacion: cliente?.['Identificacion']  || '',
    tipo_persona:   cliente?.['Tipo persona']    || 'Natural',
    correo:         cliente?.['Correo']          || '',
    telefono:       cliente?.['Telefono']        || '',
    direccion:      cliente?.['Direccion']       || '',
    municipio_dian: cliente?.['municipio_dian']  || 13001,
    pais_id:        cliente?.['pais_id']         || 45,
    regimen_fiscal: cliente?.['regimen_fiscal']  || 2,
    ciudad_nombre:  cliente?.['ciudad_nombre']   || 'Cartagena',
  })
  const [estado, setEstado] = useState('idle')
  const [errMsg, setErrMsg] = useState('')

  const [paises, setPaises]           = useState([])
  const [ciudades, setCiudades]       = useState([])
  const [ciudadQuery, setCiudadQuery] = useState(cliente?.['ciudad_nombre'] || '')
  const [ciudadOpen, setCiudadOpen]   = useState(false)
  const [loadingCiudades, setLoadingCiudades] = useState(false)

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  useEffect(() => {
    authFetch(`${API_BASE}/clientes/paises`)
      .then(r => r.json())
      .then(d => setPaises(d.paises || []))
      .catch(() => setPaises([{ matias_id: 45, codigo_a2: 'CO', nombre: 'Colombia' }]))
  }, []) // eslint-disable-line

  const buscarCiudades = useCallback(async (q, paisId) => {
    if (q.length < 2) { setCiudades([]); return }
    setLoadingCiudades(true)
    try {
      const r = await authFetch(`${API_BASE}/clientes/ciudades?pais_id=${paisId}&q=${encodeURIComponent(q)}`)
      const d = await r.json()
      setCiudades(d.ciudades || [])
    } catch { setCiudades([]) }
    finally { setLoadingCiudades(false) }
  }, [authFetch])

  useEffect(() => {
    const timer = setTimeout(() => buscarCiudades(ciudadQuery, form.pais_id), 300)
    return () => clearTimeout(timer)
  }, [ciudadQuery, form.pais_id, buscarCiudades])

  function seleccionarCiudad(c) {
    set('municipio_dian', c.dane_code)
    set('ciudad_nombre', c.nombre)
    setCiudadQuery(c.nombre + (c.departamento ? ` — ${c.departamento}` : ''))
    setCiudades([])
    setCiudadOpen(false)
  }

  async function guardar() {
    if (!form.nombre.trim()) { setErrMsg('El nombre es obligatorio'); return }
    setEstado('saving'); setErrMsg('')
    try {
      const url    = esEdit ? `${API_BASE}/clientes/${cliente.id}` : `${API_BASE}/clientes`
      const method = esEdit ? 'PATCH' : 'POST'
      const r = await authFetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'Error guardando')
      setEstado('ok')
      setTimeout(() => { onGuardado(d.cliente); onClose() }, 500)
    } catch (e) {
      setErrMsg(e.message)
      setEstado('err')
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{esEdit ? 'Editar cliente' : 'Nuevo cliente'}</DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <div>
            <Label>Nombre completo *</Label>
            <Input
              autoFocus
              value={form.nombre}
              placeholder="Ej: JUAN CARLOS PÉREZ"
              onChange={e => set('nombre', e.target.value)}
              onKeyDown={e => e.key === 'Enter' && guardar()}
            />
          </div>

          <div className="grid grid-cols-[120px_1fr] gap-3">
            <div>
              <Label>Tipo ID</Label>
              <select
                value={form.tipo_id}
                onChange={e => set('tipo_id', e.target.value)}
                className="w-full h-9 px-3 rounded-md border border-input bg-transparent text-sm"
              >
                {TIPOS_ID.map(t => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            <div>
              <Label>Número de identificación</Label>
              <Input
                value={form.identificacion}
                placeholder="Ej: 1234567890"
                onChange={e => set('identificacion', e.target.value)}
              />
            </div>
          </div>

          <div>
            <Label>Tipo de persona</Label>
            <div className="flex gap-2">
              {TIPOS_PERSONA.map(tp => (
                <button
                  key={tp}
                  onClick={() => set('tipo_persona', tp)}
                  className={cn(
                    'flex-1 h-9 rounded-md text-xs font-semibold border transition-colors',
                    form.tipo_persona === tp
                      ? 'bg-primary-soft text-primary border-primary'
                      : 'border-border text-muted-foreground hover:bg-surface-2',
                  )}
                >
                  {tp}
                </button>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Teléfono</Label>
              <Input value={form.telefono} placeholder="300 123 4567" onChange={e => set('telefono', e.target.value)} />
            </div>
            <div>
              <Label>Correo</Label>
              <Input value={form.correo} placeholder="cliente@email.com" type="email" onChange={e => set('correo', e.target.value)} />
            </div>
          </div>

          <div>
            <Label>Dirección</Label>
            <Input value={form.direccion} placeholder="Calle 10 # 5-20" onChange={e => set('direccion', e.target.value)} />
          </div>

          <div>
            <Label>País</Label>
            <select
              value={form.pais_id}
              onChange={e => {
                set('pais_id', Number(e.target.value))
                setCiudadQuery('')
                set('municipio_dian', null)
                set('ciudad_nombre', '')
              }}
              className="w-full h-9 px-3 rounded-md border border-input bg-transparent text-sm"
            >
              {paises.length > 0
                ? paises.map(p => <option key={p.matias_id} value={p.matias_id}>{p.nombre}</option>)
                : <option value={45}>Colombia</option>}
            </select>
          </div>

          <div className="relative">
            <Label>Ciudad</Label>
            <Input
              value={ciudadQuery}
              placeholder="Buscar ciudad..."
              onChange={e => { setCiudadQuery(e.target.value); setCiudadOpen(true) }}
              onFocus={() => ciudadQuery.length >= 2 && setCiudadOpen(true)}
              onBlur={() => setTimeout(() => setCiudadOpen(false), 200)}
            />
            {ciudadOpen && (loadingCiudades || ciudades.length > 0) && (
              <div className="absolute top-full left-0 right-0 mt-1 z-50 bg-surface border border-border rounded-md max-h-48 overflow-y-auto shadow-md">
                {loadingCiudades ? (
                  <div className="px-3 py-2 text-xs text-muted-foreground">Buscando…</div>
                ) : ciudades.map(c => (
                  <button
                    key={c.matias_id}
                    onMouseDown={() => seleccionarCiudad(c)}
                    className="w-full text-left px-3 py-2 text-xs hover:bg-surface-2 border-b border-border-subtle last:border-0"
                  >
                    <span className="font-semibold">{c.nombre}</span>
                    {c.departamento && <span className="text-muted-foreground"> — {c.departamento}</span>}
                  </button>
                ))}
              </div>
            )}
          </div>

          {(form.tipo_id === 'NIT' || form.tipo_persona === 'Jurídica') && (
            <div>
              <Label>Régimen fiscal</Label>
              <div className="flex gap-2">
                {[
                  { value: 2, label: 'No Responsable de IVA' },
                  { value: 1, label: 'Responsable de IVA' },
                ].map(({ value, label }) => (
                  <button
                    key={value}
                    onClick={() => set('regimen_fiscal', value)}
                    className={cn(
                      'flex-1 h-9 rounded-md text-xs font-semibold border transition-colors',
                      form.regimen_fiscal === value
                        ? 'bg-info/10 text-info border-info'
                        : 'border-border text-muted-foreground hover:bg-surface-2',
                    )}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        {errMsg && (
          <div className="flex items-center gap-2 p-3 rounded-md bg-destructive/10 border border-destructive/30 text-destructive text-xs">
            <AlertCircle className="size-3.5 shrink-0" />
            {errMsg}
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancelar</Button>
          <Button onClick={guardar} disabled={estado === 'saving' || estado === 'ok'}>
            {estado === 'saving' ? 'Guardando…' : estado === 'ok' ? '✓ Guardado' : esEdit ? 'Guardar cambios' : 'Crear cliente'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function ModalEliminar({ cliente, onClose, onEliminado, authFetch }) {
  const [estado, setEstado] = useState('idle')
  const [errMsg, setErrMsg] = useState('')

  async function eliminar() {
    setEstado('saving'); setErrMsg('')
    try {
      const r = await authFetch(`${API_BASE}/clientes/${cliente.id}`, { method: 'DELETE' })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'Error eliminando')
      setEstado('ok')
      setTimeout(() => { onEliminado(cliente.id); onClose() }, 500)
    } catch (e) {
      setErrMsg(e.message); setEstado('err')
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Eliminar cliente</DialogTitle>
        </DialogHeader>
        <div>
          <div className="text-sm font-medium">{cliente['Nombre tercero']}</div>
          <div className="text-xs text-muted-foreground mt-0.5">
            {cliente['Tipo ID']} {cliente['Identificacion']}
          </div>
        </div>
        <div className="flex items-start gap-2 p-3 rounded-md bg-warning/10 border border-warning/30 text-warning text-xs">
          <AlertCircle className="size-3.5 shrink-0 mt-0.5" />
          <span>Si el cliente tiene ventas previas, no podrá eliminarse.</span>
        </div>
        {errMsg && (
          <div className="text-xs text-destructive">{errMsg}</div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>{estado === 'ok' ? 'Cerrar' : 'Cancelar'}</Button>
          {estado !== 'ok' && (
            <Button variant="destructive" onClick={eliminar} disabled={estado === 'saving'}>
              {estado === 'saving' ? 'Eliminando…' : 'Sí, eliminar'}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ─────────────────────────────────────────────────────────────────────────────

function FilaDesktop({ cliente, onEdit, onDelete }) {
  return (
    <tr className="border-b border-border-subtle hover:bg-surface-2/40">
      <td className="px-4 py-3">
        <div className="flex items-center gap-3">
          <Avatar nombre={cliente['Nombre tercero']} />
          <div className="min-w-0">
            <div className="text-sm font-semibold truncate">{cliente['Nombre tercero']}</div>
            {cliente['Direccion'] && (
              <div className="text-[10px] text-muted-foreground flex items-center gap-1 mt-0.5 truncate">
                <MapPin className="size-3" />
                <span className="truncate">{cliente['Direccion']}</span>
              </div>
            )}
          </div>
        </div>
      </td>
      <td className="px-4 py-3">
        <div className="flex items-center gap-2">
          <TipoIdBadge tipo={cliente['Tipo ID']} />
          <span className="text-xs text-muted-foreground tabular">{cliente['Identificacion'] || '—'}</span>
        </div>
      </td>
      <td className="px-4 py-3 text-xs text-muted-foreground">{cliente['Tipo persona'] || '—'}</td>
      <td className="px-4 py-3 text-xs tabular">{cliente['Telefono'] || <span className="text-muted-foreground">—</span>}</td>
      <td className="px-4 py-3 text-xs max-w-44 truncate">{cliente['Correo'] || <span className="text-muted-foreground">—</span>}</td>
      <td className="px-4 py-3">
        <div className="flex gap-1 justify-end">
          <button onClick={onEdit} className="size-8 rounded-md hover:bg-surface-2 text-info grid place-items-center" title="Editar">
            <Pencil className="size-3.5" />
          </button>
          <button onClick={onDelete} className="size-8 rounded-md hover:bg-destructive/10 text-destructive grid place-items-center" title="Eliminar">
            <Trash2 className="size-3.5" />
          </button>
        </div>
      </td>
    </tr>
  )
}

function FilaMobile({ cliente, onEdit, onDelete }) {
  return (
    <div className="flex items-center gap-3 px-4 py-3 border-b border-border-subtle">
      <Avatar nombre={cliente['Nombre tercero']} size="lg" />
      <div className="flex-1 min-w-0">
        <div className="text-sm font-semibold truncate">{cliente['Nombre tercero']}</div>
        <div className="flex items-center gap-1.5 mt-1 flex-wrap">
          <TipoIdBadge tipo={cliente['Tipo ID']} />
          {cliente['Identificacion'] && (
            <span className="text-[11px] text-muted-foreground">{cliente['Identificacion']}</span>
          )}
          {cliente['Telefono'] && (
            <span className="text-[11px] text-muted-foreground">· {cliente['Telefono']}</span>
          )}
        </div>
      </div>
      <div className="flex gap-1 shrink-0">
        <button onClick={onEdit} className="size-9 rounded-md border border-info/30 bg-info/10 text-info grid place-items-center">
          <Pencil className="size-4" />
        </button>
        <button onClick={onDelete} className="size-9 rounded-md border border-destructive/30 bg-destructive/10 text-destructive grid place-items-center">
          <Trash2 className="size-4" />
        </button>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────

export default function TabClientes({ refreshKey }) {
  const isMobile = useIsMobile()
  const { authFetch } = useAuth()

  const [clientes,   setClientes]   = useState([])
  const [total,      setTotal]      = useState(0)
  const [offset,     setOffset]     = useState(0)
  const [busqueda,   setBusqueda]   = useState('')
  const [loading,    setLoading]    = useState(true)
  const [error,      setError]      = useState('')
  const [creando,    setCreando]    = useState(false)
  const [editando,   setEditando]   = useState(null)
  const [eliminando, setEliminando] = useState(null)
  const searchTimer = useRef(null)

  const cargar = useCallback(async (q, off) => {
    setLoading(true); setError('')
    try {
      const params = new URLSearchParams({ q: q || '', offset: off, limit: LIMIT })
      const r = await authFetch(`${API_BASE}/clientes?${params}`)
      if (!r.ok) { const d = await r.json(); throw new Error(d.detail || `Error ${r.status}`) }
      const d = await r.json()
      setClientes(d.clientes || [])
      setTotal(d.total || 0)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [authFetch])

  useEffect(() => { cargar(busqueda, offset) }, [refreshKey]) // eslint-disable-line

  function handleBusqueda(val) {
    setBusqueda(val)
    setOffset(0)
    clearTimeout(searchTimer.current)
    searchTimer.current = setTimeout(() => cargar(val, 0), 300)
  }

  function irPagina(nuevoOffset) {
    setOffset(nuevoOffset)
    cargar(busqueda, nuevoOffset)
  }

  function onClienteCreado(c) {
    setClientes(prev => prev.find(x => x.id === c.id) ? prev : [c, ...prev])
    setTotal(t => t + 1)
  }
  function onClienteEditado(c) {
    setClientes(prev => prev.map(x => x.id === c.id ? c : x))
  }
  function onClienteEliminado(id) {
    setClientes(prev => prev.filter(x => x.id !== id))
    setTotal(t => Math.max(0, t - 1))
  }

  const paginas = Math.ceil(total / LIMIT)
  const paginaActual = Math.floor(offset / LIMIT) + 1

  return (
    <div className="space-y-4">
      <header className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight flex items-center gap-2">
            <Users className="size-5 text-muted-foreground" /> Clientes
          </h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            {loading ? 'Cargando…' : `${total} clientes registrados`}
          </p>
        </div>
        <Button onClick={() => setCreando(true)}>
          <Plus className="size-4" /> Nuevo cliente
        </Button>
      </header>

      <div className="relative max-w-md">
        <Search className="size-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={busqueda}
          onChange={e => handleBusqueda(e.target.value)}
          placeholder="Buscar por nombre o identificación..."
          className="pl-9"
        />
      </div>

      <Card className="overflow-hidden">
        {loading && (
          <div className="flex items-center justify-center py-12 text-muted-foreground">
            <Loader2 className="size-5 animate-spin mr-2" /> Cargando…
          </div>
        )}

        {!loading && error && (
          <div className="p-4 text-destructive text-sm">{error}</div>
        )}

        {!loading && !error && clientes.length === 0 && (
          <p className="py-12 text-center text-sm text-muted-foreground">
            {busqueda ? 'Sin resultados para esa búsqueda.' : 'No hay clientes registrados aún.'}
          </p>
        )}

        {!loading && !error && clientes.length > 0 && (
          <>
            {isMobile ? (
              <div className="max-h-[calc(100dvh-280px)] overflow-y-auto">
                {clientes.map(c => (
                  <FilaMobile key={c.id} cliente={c} onEdit={() => setEditando(c)} onDelete={() => setEliminando(c)} />
                ))}
              </div>
            ) : (
              <div className="max-h-[calc(100dvh-320px)] overflow-auto min-h-80">
                <table className="w-full">
                  <thead className="sticky top-0 z-10 bg-surface-2/80 backdrop-blur">
                    <tr>
                      {['Cliente', 'Identificación', 'Tipo persona', 'Teléfono', 'Correo', ''].map(h => (
                        <th key={h} className="px-4 py-2 text-left text-[10px] uppercase tracking-wider font-semibold text-muted-foreground border-b border-border">
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {clientes.map(c => (
                      <FilaDesktop key={c.id} cliente={c} onEdit={() => setEditando(c)} onDelete={() => setEliminando(c)} />
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            <div className="flex items-center justify-between px-4 py-2.5 border-t border-border bg-surface-2/30 flex-wrap gap-2">
              <span className="text-xs text-muted-foreground">
                Mostrando {clientes.length} de {total} clientes
              </span>
              {paginas > 1 && (
                <div className="flex items-center gap-2">
                  <Button size="sm" variant="outline" disabled={paginaActual === 1} onClick={() => irPagina(offset - LIMIT)}>
                    <ChevronLeft className="size-3.5" /> Anterior
                  </Button>
                  <span className="text-xs text-muted-foreground tabular">{paginaActual} / {paginas}</span>
                  <Button size="sm" variant="outline" disabled={paginaActual === paginas} onClick={() => irPagina(offset + LIMIT)}>
                    Siguiente <ChevronRight className="size-3.5" />
                  </Button>
                </div>
              )}
            </div>
          </>
        )}
      </Card>

      {creando && (
        <ModalCliente cliente={null} onClose={() => setCreando(false)} onGuardado={onClienteCreado} authFetch={authFetch} />
      )}
      {editando && (
        <ModalCliente cliente={editando} onClose={() => setEditando(null)} onGuardado={onClienteEditado} authFetch={authFetch} />
      )}
      {eliminando && (
        <ModalEliminar cliente={eliminando} onClose={() => setEliminando(null)} onEliminado={onClienteEliminado} authFetch={authFetch} />
      )}
    </div>
  )
}
