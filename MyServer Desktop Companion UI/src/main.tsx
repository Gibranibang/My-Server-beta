import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import CompanionApp from './CompanionApp'
import { setCompanionApi, createMockApi } from './companion/api'
import { createRealApi } from './companion/api.real'
import './index.css'

const isTauri = typeof window !== 'undefined' && Boolean((window as any).__TAURI_INTERNALS__ || (window as any).__TAURI__)
const isPywebview = typeof window !== 'undefined' && Boolean((window as any).pywebview)
const isNativeApp = isTauri || isPywebview

const urlParams = typeof window !== 'undefined' ? new URLSearchParams(window.location.search) : null
const forceCanvas = urlParams?.get('canvas') === '1' || urlParams?.get('board') === '1'
const forceMock = urlParams?.get('mock') === '1'

// Di lingkungan native desktop (Tauri / pywebview) atau build produksi: selalu gunakan Real API
if (isNativeApp || (!forceMock && import.meta.env.PROD)) {
  setCompanionApi(createRealApi())
} else {
  setCompanionApi(createMockApi())
}

if (typeof window !== 'undefined') {
  document.title = 'MyServer Companion'
}

// Hanya render multi-frame Figma canvas board jika secara eksplisit dipanggil dengan ?canvas=1 di browser dev
const renderCanvas = !isNativeApp && forceCanvas

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    {renderCanvas ? <App /> : <CompanionApp />}
  </React.StrictMode>,
)
