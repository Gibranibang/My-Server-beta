import React from 'react'
import ReactDOM from 'react-dom/client'
import CompanionApp from './CompanionApp'
import { setCompanionApi } from './companion/api'
import { createRealApi } from './companion/api.real'
import './index.css'

// Register real API backend
setCompanionApi(createRealApi())

if (typeof window !== "undefined") {
  document.title = "MyServer Companion"
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <CompanionApp />
  </React.StrictMode>,
)
