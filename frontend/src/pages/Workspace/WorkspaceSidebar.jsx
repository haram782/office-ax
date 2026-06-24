import { Ic } from '../../components/Ic'

/**
 * 워크스페이스 좌측 사이드바.
 * - 대화 목록 (더미 + 현재 세션)
 * - 이 세션의 파일 (useFileItems 연결)
 * - 활성 자동화 규칙 체크박스
 */
export function WorkspaceSidebar({
  conversations,
  activeConv,
  onSelectConversation,
  onNewConversation,
  fileItems,
  viewingFileId,
  onFileView,
  rules,
  onToggleRule,
  activeRuleCount,
  isLoadingSessions,
}) {
  const RULE_LABELS = {
    table: '표 셀 서식 자동 정렬',
    date:  '날짜 표기 형식 통일 (YYYY-MM-DD)',
    mask:  '개인정보 자동 마스킹',
    tone:  '어투 일괄 변환 (RAG)',
  }

  function SectionLabel({ text, action }) {
    return (
      <div className="flex items-center justify-between px-2 pb-2">
        <div className="text-xs font-semibold text-zinc-400 uppercase tracking-wide">{text}</div>
        {action}
      </div>
    )
  }

  function ConvItem({ conv }) {
    const active = conv.id === activeConv
    return (
      <button
        onClick={() => onSelectConversation(conv.id)}
        className={
          'w-full text-left rounded-lg px-2.5 py-2 flex items-start gap-2 border ' +
          (active
            ? 'border-blue-200 dark:border-blue-500/40 bg-blue-50/60 dark:bg-blue-500/10'
            : 'border-transparent hover:bg-zinc-100 dark:hover:bg-zinc-800')
        }
      >
        <span className={'mt-0.5 shrink-0 ' + (active ? 'text-blue-500 dark:text-blue-300' : 'text-zinc-400')}>
          <Ic name="messageSquare" className="w-3.5 h-3.5" />
        </span>
        <div className="min-w-0 flex-1">
          <div className={'text-[13px] truncate ' + (active ? 'text-blue-700 dark:text-blue-200 font-medium' : 'text-zinc-700 dark:text-zinc-200')}>
            {conv.title}
          </div>
          <div className="text-[11px] text-zinc-400">{conv.ts}</div>
        </div>
      </button>
    )
  }

  function FileItem({ item }) {
    const active = item.id === viewingFileId
    return (
      <button
        onClick={() => onFileView(item.id)}
        className={
          'w-full text-left rounded-lg px-3 py-2 flex items-center gap-2.5 border ' +
          (active
            ? 'border-blue-200 dark:border-blue-500/40 bg-blue-50/60 dark:bg-blue-500/10'
            : 'border-transparent hover:bg-zinc-100 dark:hover:bg-zinc-800')
        }
      >
        <Ic name="fileText" className="w-4 h-4 text-zinc-400 shrink-0" />
        <div className="min-w-0 flex-1">
          <div className={'text-[13px] truncate ' + (active ? 'text-blue-700 dark:text-blue-200 font-medium' : 'text-zinc-700 dark:text-zinc-200')}>
            {item.filename}
          </div>
          <div className="text-[11px] text-zinc-400">
            {item.status === 'done' ? '완료' : item.status === 'processing' ? '분석 중' : item.status}
          </div>
        </div>
      </button>
    )
  }

  function RuleCheck({ ruleKey }) {
    const on = rules[ruleKey]
    return (
      <button
        onClick={() => onToggleRule(ruleKey)}
        className="w-full flex items-center gap-2.5 px-2 py-1.5 rounded-lg hover:bg-zinc-100 dark:hover:bg-zinc-800 text-left"
      >
        <span className={
          'w-4 h-4 rounded grid place-items-center border shrink-0 ' +
          (on ? 'bg-blue-600 border-blue-600 text-white' : 'border-zinc-300 dark:border-zinc-600')
        }>
          {on && <Ic name="check" className="w-3 h-3" />}
        </span>
        <span className={'text-xs ' + (on ? 'text-zinc-700 dark:text-zinc-200' : 'text-zinc-400')}>
          {RULE_LABELS[ruleKey]}
        </span>
      </button>
    )
  }

  const newBtn = (
    <button
      onClick={onNewConversation}
      className="inline-flex items-center gap-1 text-[11px] font-medium text-blue-600 dark:text-blue-300 hover:underline"
    >
      <Ic name="plus" className="w-3 h-3" />새 대화
    </button>
  )

  return (
    <aside className="w-64 shrink-0 border-r border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 flex flex-col">
      <div className="flex-1 overflow-auto p-3 flex flex-col gap-4">
        {/* 대화 목록 */}
        <div>
          <SectionLabel text="대화" action={newBtn} />
          <div className="flex flex-col gap-1">
            {isLoadingSessions ? (
              // 백엔드 세션 로드 중 스피너
              <div className="flex items-center justify-center py-8 text-zinc-400">
                <span className="w-4 h-4 border-2 border-zinc-300 dark:border-zinc-600 border-t-blue-500 rounded-full animate-spin mr-2" />
                <span className="text-xs">불러오는 중...</span>
              </div>
            ) : (
              conversations.map(c => <ConvItem key={c.id} conv={c} />)
            )}
          </div>
        </div>

        {/* 이 세션의 파일 */}
        <div>
          <SectionLabel text="이 세션의 파일" />
          <div className="flex flex-col gap-1">
            {fileItems.length > 0
              ? fileItems.map(f => <FileItem key={f.id} item={f} />)
              : (
                <div className="px-2 py-3 text-[11px] text-zinc-400">
                  파일을 첨부하면 여기에 표시됩니다
                </div>
              )
            }
          </div>
        </div>

        {/* 활성 자동화 규칙 */}
        <div>
          <SectionLabel text="활성 자동화 규칙" />
          <div className="flex flex-col gap-0.5">
            {Object.keys(rules).map(k => <RuleCheck key={k} ruleKey={k} />)}
          </div>
        </div>
      </div>

      {/* 하단 규칙 카운터 */}
      <div className="shrink-0 p-3 border-t border-zinc-200 dark:border-zinc-800">
        <div className="rounded-lg bg-zinc-50 dark:bg-zinc-800/60 px-3 py-2.5 text-xs text-zinc-500 dark:text-zinc-400 flex items-center gap-2">
          <Ic name="zap" className="w-4 h-4 text-blue-500" />
          <span>규칙 <b className="text-zinc-700 dark:text-zinc-200">{activeRuleCount}</b>개 적용 중</span>
        </div>
      </div>
    </aside>
  )
}
