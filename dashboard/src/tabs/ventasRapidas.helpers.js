// ══════════════════════════════════════════════════════════════════════════════
// HELPERS Y CONSTANTES — TabVentasRapidas
// Extraídos del tab principal en Wave 3.b (sub-tarea 1).
// Sin dependencias de React: solo datos + funciones puras + acceso a storage.
// IMPORTANTE: mantener mismas claves localStorage/sessionStorage por compat.
// ══════════════════════════════════════════════════════════════════════════════

// ── Favoritos persistidos (localStorage) ──────────────────────────────────────
export const FAV_KEY = 'vr_favs_v2'
export const loadFavs = () => {
  try { return JSON.parse(localStorage.getItem(FAV_KEY) || '[]') } catch { return [] }
}
export const saveFavs = (keys) => {
  try { localStorage.setItem(FAV_KEY, JSON.stringify(keys)) } catch {}
}

// ── Carrito persistido en sesión (sessionStorage) ─────────────────────────────
export const CART_KEY = 'vr_carrito_v1'
export const loadCart = () => {
  try { return JSON.parse(sessionStorage.getItem(CART_KEY) || '[]') } catch { return [] }
}
export const saveCart = (items) => {
  try { sessionStorage.setItem(CART_KEY, JSON.stringify(items)) } catch {}
}

// ── Icono por categoría ───────────────────────────────────────────────────────
export const CAT_ICON = {
  '1 artículos de ferreteria':                    '🔧',
  '2 pinturas y disolventes':                     '🎨',
  '3 tornilleria':                                '🔩',
  '4 impermeabilizantes y materiales de construcción': '🧱',
  '5 materiales electricos':                      '⚡',
}
export function iconCat(cat = '') {
  return CAT_ICON[cat.toLowerCase()] || '📦'
}

// ── Nombre limpio de categoría (sin número prefijo) ───────────────────────────
export function catLabel(cat = '') {
  return cat.replace(/^\d+\s*/, '')
}

// ── Helper de normalización ──────────────────────────────────────────────────
export const nl = s => (s || '').toLowerCase()

// ══════════════════════════════════════════════════════════════════════════════
// SUBCATEGORÍAS — misma lógica que /productos en el bot
// ══════════════════════════════════════════════════════════════════════════════
export const SUBCATS = {
  '1 artículos de ferreteria': [
    { key: 'ferr_brochas',     icono: '🖌️', label: 'Brochas / Rodillos', fn: p => nl(p.nombre).includes('brocha') || nl(p.nombre).includes('rodillo') },
    { key: 'ferr_lijas',       icono: '📏', label: 'Lijas',               fn: p => nl(p.nombre).includes('lija')    || nl(p.nombre).includes('esmeril') },
    { key: 'ferr_cintas',      icono: '🔗', label: 'Cintas',              fn: p => nl(p.nombre).includes('cinta')   || nl(p.nombre).includes('pele')  || nl(p.nombre).includes('enmascarar') },
    { key: 'ferr_cerraduras',  icono: '🔒', label: 'Cerraduras',          fn: p => ['cerradura','candado','cerrojo','falleba'].some(k => nl(p.nombre).includes(k)) },
    { key: 'ferr_brocas',      icono: '🪚', label: 'Brocas / Discos',     fn: p => nl(p.nombre).includes('broca')   || nl(p.nombre).includes('disco') },
    { key: 'ferr_herr',        icono: '🔧', label: 'Herramientas',        fn: p => ['martillo','metro','destornillador','exacto','espatula','espátula','tijera','formon','grapadora','machete','taladro','llave','pulidora'].some(k => nl(p.nombre).includes(k)) },
    { key: 'ferr_varios',      icono: '📦', label: 'Varios',              fn: p => !['brocha','rodillo','lija','esmeril','cinta','pele','enmascarar','cerradura','candado','cerrojo','falleba','broca','disco','martillo','metro','destornillador','exacto','espatula','tijera','formon','grapadora','machete','taladro','llave','pulidora'].some(k => nl(p.nombre).includes(k)) },
  ],
  '2 pinturas y disolventes': [
    { key: 'pint_vinilo',    icono: '🖌️', label: 'Vinilo / Cuñetes',     fn: p => nl(p.nombre).includes('vinilo') || /cu[ñn]ete/i.test(p.nombre) },
    { key: 'pint_esmalte',   icono: '🎨', label: 'Esmalte / Anticorr.',  fn: p => nl(p.nombre).includes('esmalte') || nl(p.nombre).includes('anticorrosivo') },
    { key: 'pint_laca',      icono: '🪄', label: 'Laca',                 fn: p => nl(p.nombre).includes('laca') },
    { key: 'pint_thinner',   icono: '🧪', label: 'Thinner / Varsol',     fn: p => nl(p.nombre).includes('thinner') || nl(p.nombre).includes('varsol') || nl(p.nombre).includes('tiner') },
    { key: 'pint_poli',      icono: '💧', label: 'Poliuretano',          fn: p => nl(p.nombre).includes('poliuretano') || nl(p.nombre).includes('poliamida') },
    { key: 'pint_aerosol',   icono: '🎭', label: 'Aerosol',              fn: p => nl(p.nombre).includes('aerosol') || nl(p.nombre).includes('aersosol') },
    { key: 'pint_sellador',  icono: '🧴', label: 'Sellador / Masilla',   fn: p => nl(p.nombre).includes('sellador') || nl(p.nombre).includes('masilla') },
    { key: 'pint_otros',     icono: '🎨', label: 'Otros',                fn: p => !['vinilo','esmalte','anticorrosivo','laca','thinner','varsol','tiner','poliuretano','poliamida','aerosol','aersosol','sellador','masilla'].some(k => nl(p.nombre).includes(k)) },
  ],
  '3 tornilleria': [
    { key: 'torn_dry6',      icono: '⚙️', label: 'Drywall ×6',           fn: p => nl(p.nombre).includes('drywall') && /6x/.test(nl(p.nombre).replace(/ /g,'')) },
    { key: 'torn_dry8',      icono: '⚙️', label: 'Drywall ×8',           fn: p => nl(p.nombre).includes('drywall') && /8x/.test(nl(p.nombre).replace(/ /g,'')) },
    { key: 'torn_dry10',     icono: '⚙️', label: 'Drywall ×10',          fn: p => nl(p.nombre).includes('drywall') && /10x/.test(nl(p.nombre).replace(/ /g,'')) },
    { key: 'torn_hex',       icono: '🔩', label: 'Hex Galvanizado',       fn: p => nl(p.nombre).includes('hex') && (nl(p.nombre).includes('tornillo') || nl(p.nombre).includes('tuerca') || (nl(p.nombre).includes('arandela') && nl(p.nombre).includes('galv'))) },
    { key: 'torn_estufa',    icono: '🔩', label: 'Estufa',                fn: p => nl(p.nombre).includes('estufa') },
    { key: 'torn_puntillas', icono: '📌', label: 'Puntillas',             fn: p => nl(p.nombre).includes('puntilla') },
    { key: 'torn_tirafondo', icono: '🔩', label: 'Tira Fondo',            fn: p => nl(p.nombre).includes('tira fondo') },
    { key: 'torn_arandelas', icono: '⚙️', label: 'Arandelas / Chazos',   fn: p => (nl(p.nombre).includes('arandela') || nl(p.nombre).includes('chazo')) && !nl(p.nombre).includes('galv') },
  ],
  '4 impermeabilizantes y materiales de construcción': [],
  '5 materiales electricos': [],
}

// Ordenar tornillería: Drywall primero (6×→8×→10×), luego el resto por precio
export function ordenarTornilleria(prods) {
  const isDry = p => nl(p.nombre).includes('drywall') && nl(p.nombre).includes('tornillo')
  const drySize = p => {
    const m = nl(p.nombre).replace(/ /g,'').match(/(\d+)x/)
    return m ? parseInt(m[1]) : 99
  }
  const dryLen = p => {
    const m = nl(p.nombre).replace(/ /g,'').match(/x(\d+(?:\.\d+)?)/)
    return m ? parseFloat(m[1]) : 999
  }
  const dry   = prods.filter(isDry).sort((a,b) => drySize(a)-drySize(b) || dryLen(a)-dryLen(b))
  const resto = prods.filter(p => !isDry(p)).sort((a,b) => a.precio - b.precio)
  return [...dry, ...resto]
}

// ── Tipo de producto ──────────────────────────────────────────────────────────
export function tipoProd(prod) {
  if (prod.nombre?.toLowerCase().includes('esmeril')) return 'cm'
  if (['MLT','MILILITROS','ML'].includes((prod.unidad_medida || '').toUpperCase())) return 'mlt'
  if (['GRM','GRAMOS','GR'].includes((prod.unidad_medida || '').toUpperCase())) return 'grm'
  if (['KG','KGM'].includes((prod.unidad_medida || '').toUpperCase())) return 'kg'
  if (prod.precios_fraccion && Object.keys(prod.precios_fraccion).length > 0) return 'fraccion'
  return 'simple'
}

// ══════════════════════════════════════════════════════════════════════════════
// CONFIG DE GRUPOS DE COLOR (vinilo, esmalte, laca, aerosol)
// ══════════════════════════════════════════════════════════════════════════════
export const GRUPOS_CONFIG = {
  pint_vinilo: [
    { key:'T1',      icono:'🖌️', titulo:'Galón Vinilo T1',     match: p => /vinilo davinci t1/i.test(p.nombre),     getColor: p => p.nombre.replace(/Vinilo Davinci T1 /i,'').trim() },
    { key:'T2',      icono:'🖌️', titulo:'Galón Vinilo T2',     match: p => /vinilo davinci t2/i.test(p.nombre),     getColor: p => p.nombre.replace(/Vinilo Davinci T2 /i,'').trim() },
    { key:'T3',      icono:'🖌️', titulo:'Galón Vinilo T3',     sinColorPrep: true, match: p => /vinilo davinci t3/i.test(p.nombre),     getColor: p => p.nombre.replace(/Vinilo Davinci T3 /i,'').trim() },
    { key:'ico',     icono:'🖌️', titulo:'Vinilo ICO',          sinColorPrep: true, match: p => /vinilo ico/i.test(p.nombre) && !/cuñete|cunete/i.test(p.nombre), getColor: p => p.nombre.replace(/Vinilo ICO /i,'').trim() },
    { key:'cunete',  icono:'🪣', titulo:'Cuñete (5 gal)',      sinPrecio: true, match: p => /cu[ñn]ete/i.test(p.nombre) && !/1\/2|medio|masilla|placco/i.test(p.nombre), getColor: p => p.nombre },
    { key:'medio',   icono:'🪣', titulo:'½ Cuñete (2.5 gal)', sinPrecio: true, match: p => /(1\/2\s*cu[ñn]ete|medio\s*cu[ñn]ete)/i.test(p.nombre), getColor: p => p.nombre },
  ],
  pint_esmalte: [
    { key:'std',   icono:'🎨', titulo:'Esmalte estándar',  match: p => /^esmalte /i.test(p.nombre)  && !/3.en|aluminio|dorado/i.test(p.nombre), getColor: p => p.nombre.replace(/^esmalte /i,'').trim() },
    { key:'anti',  icono:'🔴', titulo:'Anticorrosivo',      match: p => /^anticorrosivo /i.test(p.nombre), getColor: p => p.nombre.replace(/^anticorrosivo /i,'').trim() },
    { key:'3en1',  icono:'🎨', titulo:'Esmalte 3 en 1',    match: p => /3.en.?1/i.test(p.nombre) && !/aluminio/i.test(p.nombre), getColor: p => p.nombre.replace(/esmalte 3 en.?1\s*/i,'').replace(/\s*(davinci|tonner|pintuco)\s*/i,' ').trim() },
  ],
  pint_laca: [
    { key:'cat',     icono:'🪄', titulo:'Laca Catalizada', match: p => /catalizada/i.test(p.nombre) && !/masilla/i.test(p.nombre), getColor: p => p.nombre.replace(/laca /i,'').replace(/ catalizada/i,'').trim() },
    { key:'corr',    icono:'🪄', titulo:'Laca Corriente',  match: p => /laca corriente/i.test(p.nombre), getColor: p => p.nombre.replace(/laca corriente\s*/i,'').trim() },
    { key:'masilla', icono:'🧴', titulo:'Masilla Laca',    match: p => /masilla laca/i.test(p.nombre), getColor: p => p.nombre.replace(/masilla laca\s*/i,'').trim() },
  ],
  pint_aerosol: [
    { key:'std',  icono:'🎭', titulo:'Aerosol estándar', match: p => /aerosol/i.test(p.nombre) && !/alta\s*temp|fluorec|silicona/i.test(p.nombre), getColor: p => p.nombre.replace(/^aerosol\s*/i,'').trim() },
  ],
}

export const SUBCATS_COLORES = Object.keys(GRUPOS_CONFIG)

// ─── buildGrupos: agrupa productos por config ─────────────────────────────────
export function buildGrupos(prods, subcatKey) {
  const config = GRUPOS_CONFIG[subcatKey]
  if (!config) return { grupos: [], sueltos: prods }
  const asignados = new Set()
  const grupos = config.map(gc => {
    const items = prods.filter(p => {
      if (asignados.has(p.key)) return false
      const ok = gc.match(p)
      if (ok) asignados.add(p.key)
      return ok
    })
    return { ...gc, items }
  }).filter(g => g.items.length > 0)
  const sueltos = prods.filter(p => !asignados.has(p.key))
  return { grupos, sueltos }
}
