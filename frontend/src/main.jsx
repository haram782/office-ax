import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import PreviewPage from './PreviewPage'
import './index.css'

const isPreview = window.location.hash === '#preview'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    {isPreview ? <PreviewPage /> : <App />}
  </React.StrictMode>
)
