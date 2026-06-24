import { Ic } from '../../components/Ic'

/**
 * 대시보드 좌측 사이드바.
 * dashTab 상태에 따라 활성 항목을 강조한다.
 */
export function DashboardSidebar({ dashTab, onTabChange }) {
  const items = [
    { id: 'pipelines', label: '나의 파이프라인 관리', icon: 'workflow', desc: '자동화 흐름 5개' },
    { id: 'email',     label: '이메일 수발신 뷰',      icon: 'mail',     desc: 'park.sg@office-ax.com' },
    { id: 'style',     label: '스타일 & 템플릿 (RAG)', icon: 'sparkles', desc: '어투·서식 에셋 4개' },
  ]

  return (
    <aside className="w-64 shrink-0 border-r border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-3 flex flex-col gap-1">
      <div className="text-xs font-semibold text-zinc-400 px-2 pt-1 pb-2 tracking-wide uppercase">
        대시보드 메뉴
      </div>

      {items.map(item => {
        const active = dashTab === item.id
        return (
          <button
            key={item.id}
            onClick={() => onTabChange(item.id)}
            className={
              'w-full text-left rounded-lg px-3 py-2.5 flex items-start gap-2.5 transition-colors ' +
              (active
                ? 'bg-blue-50 dark:bg-blue-500/10 ring-1 ring-blue-200 dark:ring-blue-500/30'
                : 'hover:bg-zinc-100 dark:hover:bg-zinc-800')
            }
          >
            <span className={(active ? 'text-blue-600 dark:text-blue-300' : 'text-zinc-400') + ' mt-0.5'}>
              <Ic name={item.icon} className="w-5 h-5" />
            </span>
            <div className="min-w-0">
              <div className={'text-sm font-medium ' + (active ? 'text-blue-700 dark:text-blue-200' : 'text-zinc-700 dark:text-zinc-200')}>
                {item.label}
              </div>
              <div className="text-xs text-zinc-400 mt-0.5 truncate">{item.desc}</div>
            </div>
          </button>
        )
      })}

      <div className="flex-1" />

      {/* Pro 플랜 배지 */}
      <div className="rounded-lg bg-zinc-50 dark:bg-zinc-800/60 p-3 text-xs text-zinc-500 dark:text-zinc-400">
        <div className="font-medium text-zinc-700 dark:text-zinc-200 mb-1">Pro 플랜</div>
        문서 무제한 · RAG 학습 5GB
      </div>
    </aside>
  )
}
