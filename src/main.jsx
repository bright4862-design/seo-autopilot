import React from 'react'
import ReactDOM from 'react-dom/client'
import '@/lib/scanStorageRecovery'
import App from '@/App.jsx'
import { AuthProvider } from '@/lib/AuthContext'
import '@/index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <AuthProvider>
    <App />
  </AuthProvider>
)
