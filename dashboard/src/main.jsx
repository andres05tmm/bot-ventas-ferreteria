import React from 'react'
import ReactDOM from 'react-dom/client'
// Inter via @fontsource — sin <link> externo (Railway, evitar FOUT)
import '@fontsource/inter/400.css'
import '@fontsource/inter/500.css'
import '@fontsource/inter/600.css'
import '@fontsource/inter/700.css'
import App from './App.jsx'
import './index.css'

// Bloquear orientación portrait — solo funciona en contextos seguros con soporte de la API
if (screen?.orientation?.lock) {
  screen.orientation.lock('portrait').catch(() => {})
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
