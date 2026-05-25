/*
 * TabHistorial — wrapper con dos vistas (Día / Mes).
 * Fase D: unifica el histórico de ventas en una sola ruta /historial.
 *   - ?view=dia (default): VistaDia — ventas del día con edición/eliminación
 *   - ?view=mes           : VistaMes — calendario heatmap mensual + desglose
 * El estado vive en el query string para que tabs distintas se compartan
 * por link y refresco.
 */
import { useSearchParams } from 'react-router-dom'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs.jsx'
import VistaDia from './historial/VistaDia.jsx'
import VistaMes from './historial/VistaMes.jsx'

export default function TabHistorial({ refreshKey }) {
  const [params, setParams] = useSearchParams()
  const view = params.get('view') === 'mes' ? 'mes' : 'dia'

  function setView(next) {
    const np = new URLSearchParams(params)
    if (next === 'dia') np.delete('view')   // 'dia' es el default → URL más limpia
    else                np.set('view', next)
    setParams(np, { replace: true })
  }

  return (
    <div className="space-y-4">
      <header className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Historial de ventas</h1>
          <p className="text-xs text-muted-foreground mt-0.5 capitalize">
            {new Date().toLocaleDateString('es-CO', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric', timeZone: 'America/Bogota' })}
          </p>
        </div>
      </header>

      <Tabs value={view} onValueChange={setView}>
        <TabsList>
          <TabsTrigger value="dia">Día</TabsTrigger>
          <TabsTrigger value="mes">Mes</TabsTrigger>
        </TabsList>

        <TabsContent value="dia" className="mt-4">
          <VistaDia refreshKey={refreshKey} />
        </TabsContent>
        <TabsContent value="mes" className="mt-4">
          <VistaMes />
        </TabsContent>
      </Tabs>
    </div>
  )
}
