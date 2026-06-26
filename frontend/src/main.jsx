import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { GoogleOAuthProvider } from '@react-oauth/google'
import App from './App'
import { ThemeProvider } from './theme'
import { AppModalProvider } from './components/AppModal'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    {/* GoogleOAuthProvider는 BrowserRouter 바깥에 위치해야 한다.
        clientId 미설정 시 'dev-placeholder'로 폴백 — SDK 초기화 crash 방지.
        실제 Google 로그인은 .env에 VITE_GOOGLE_CLIENT_ID 설정 시 동작한다. */}
    <GoogleOAuthProvider clientId={import.meta.env.VITE_GOOGLE_CLIENT_ID || 'dev-placeholder'}>
      <BrowserRouter>
        <ThemeProvider>
          <AppModalProvider>
            <App />
          </AppModalProvider>
        </ThemeProvider>
      </BrowserRouter>
    </GoogleOAuthProvider>
  </React.StrictMode>,
)
