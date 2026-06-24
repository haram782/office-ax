import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Topbar }           from '../../components/Topbar'
import { Ic }               from '../../components/Ic'
import { DashboardSidebar } from './DashboardSidebar'
import { DashStats }        from './DashStats'
import { PipelinesView }    from './PipelinesView'
import { EmailView }        from './EmailView'
import { StyleView }        from './StyleView'

/**
 * 대시보드 페이지.
 * Topbar + 좌측 사이드바 + 메인 영역(탭별 콘텐츠) 구조.
 */
export default function Dashboard() {
  const navigate  = useNavigate()
  const [dashTab, setDashTab] = useState('pipelines')

  function renderContent() {
    if (dashTab === 'pipelines') return <PipelinesView />
    if (dashTab === 'email')     return <EmailView />
    return <StyleView />
  }

  return (
    <div className="h-screen flex flex-col">
      <Topbar onNewConversation={() => navigate('/workspace')} />

      <div className="flex-1 flex overflow-hidden">
        <DashboardSidebar dashTab={dashTab} onTabChange={setDashTab} />

        <main className="flex-1 overflow-auto p-6">
          {/* 페이지 헤더 */}
          <div className="flex items-end justify-between mb-5">
            <div>
              <h1 className="text-lg font-bold text-zinc-800 dark:text-zinc-100">대시보드</h1>
              <p className="text-sm text-zinc-400 mt-0.5">park.sg@office-ax.com</p>
            </div>
            <button
              onClick={() => navigate('/workspace')}
              className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium px-3.5 py-2"
            >
              <Ic name="fileText" />
              워크스페이스 열기
            </button>
          </div>

          {/* 통계 카드 3개 */}
          <DashStats />

          {/* 탭 콘텐츠 */}
          {renderContent()}
        </main>
      </div>
    </div>
  )
}
