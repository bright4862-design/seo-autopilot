import React from 'react'
import ReactDOM from 'react-dom/client'
import '@/lib/scanStorageRecovery'
import App from '@/App.jsx'
import { AuthProvider } from '@/lib/AuthContext'
import '@/index.css'

// Public release provenance. The exact Git SHA is compiled into the production
// bundle by the guarded Base44 site publisher and verified after deployment.
// It contains no secret material; it only ties the customer UI bytes to source.
const FIXLIST_SOURCE_SHA = String(import.meta.env.VITE_FIXLIST_SOURCE_SHA || '')
if (typeof window !== 'undefined') {
  Object.defineProperty(window, '__FIXLIST_SOURCE_SHA__', {
    value: FIXLIST_SOURCE_SHA,
    configurable: false,
    enumerable: false,
    writable: false,
  })
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <AuthProvider>
    <App />
  </AuthProvider>
)
