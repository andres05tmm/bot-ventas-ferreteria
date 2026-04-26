import React from 'react'
import ReactDOM from 'react-dom/client'
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
