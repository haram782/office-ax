import { Routes, Route } from 'react-router-dom'
import Dashboard   from './pages/Dashboard'
import Workspace   from './pages/Workspace'
import Pipeline    from './pages/Pipeline'
import PreviewPage from './pages/PreviewPage'

/**
 * 라우트 정의.
 * ThemeProvider의 dark 래퍼 내부에서 렌더된다.
 */
export default function App() {
  return (
    <div className="min-h-screen bg-zinc-100 dark:bg-zinc-950 text-zinc-800 dark:text-zinc-300">
      <Routes>
        <Route path="/"             element={<Dashboard />}  />
        <Route path="/workspace"    element={<Workspace />}  />
        <Route path="/pipeline/:id" element={<Pipeline />}   />
        <Route path="/preview"      element={<PreviewPage />} />
      </Routes>
    </div>
  )
}
