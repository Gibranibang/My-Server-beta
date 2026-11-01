import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import CompanionApp from './CompanionApp'
import { setCompanionApi, createMockApi } from './companion/api'
import { createRealApi } from './companion/api.real'
import './index.css'

const isNativeApp = typeof window !== 'undefined' && Boolean((window as any).pywebview)
const urlParams = typeof window !== 'undefined' ? new URLSearchParams(window.location.search) : null
const forceReal = urlParams?.get('real') === '1'
const forceCompanion = urlParams?.get('app') === '1'

// Di browser (preview / Figma): gunakan Mock API agar SEMUA card, drive, app, dan rute terbuka 100% tanpa login
if (isNativeApp || forceReal) {
  setCompanionApi(createRealApi())
} else {
  setCompanionApi(createMockApi())
}

if (typeof window !== 'undefined') {
  document.title = 'MyServer Companion - Figma Design Canvas'
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    {isNativeApp && !forceCompanion ? <CompanionApp /> : <App />}
  </React.StrictMode>,
)
