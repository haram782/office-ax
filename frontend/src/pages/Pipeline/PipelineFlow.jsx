import { Ic } from '../../components/Ic'

// 노드 색상 테마 정의
const THEMES = {
  amber:   { border: 'border-amber-300 dark:border-amber-500/40',   badge: 'bg-amber-100 text-amber-600 dark:bg-amber-500/20 dark:text-amber-300',   text: 'text-amber-600 dark:text-amber-300',   dot: 'bg-amber-500'   },
  violet:  { border: 'border-violet-300 dark:border-violet-500/40', badge: 'bg-violet-100 text-violet-600 dark:bg-violet-500/20 dark:text-violet-300', text: 'text-violet-600 dark:text-violet-300', dot: 'bg-violet-500'  },
  blue:    { border: 'border-blue-300 dark:border-blue-500/40',     badge: 'bg-blue-100 text-blue-600 dark:bg-blue-500/20 dark:text-blue-300',         text: 'text-blue-600 dark:text-blue-300',     dot: 'bg-blue-500'    },
  emerald: { border: 'border-emerald-300 dark:border-emerald-500/40', badge: 'bg-emerald-100 text-emerald-600 dark:bg-emerald-500/20 dark:text-emerald-300', text: 'text-emerald-600 dark:text-emerald-300', dot: 'bg-emerald-500' },
}

/** 파이프라인 노드 카드 */
function Node({ theme, icon, tag, title, desc, chips }) {
  const t = THEMES[theme]
  return (
    <div className={`w-60 shrink-0 rounded-xl border bg-white dark:bg-zinc-900 shadow-sm ${t.border}`}>
      {/* 노드 헤더 */}
      <div className={`flex items-center gap-2 px-3.5 py-2.5 border-b ${t.border}`}>
        <div className={`w-7 h-7 rounded-lg grid place-items-center shrink-0 ${t.badge}`}>
          <Ic name={icon} />
        </div>
        <div className="min-w-0">
          <div className={`text-[10px] font-semibold uppercase tracking-wide ${t.text}`}>{tag}</div>
          <div className="text-sm font-semibold text-zinc-800 dark:text-zinc-100 truncate">{title}</div>
        </div>
      </div>

      {/* 노드 본문 */}
      <div className="px-3.5 py-3">
        <p className="text-xs text-zinc-500 dark:text-zinc-400 leading-relaxed">{desc}</p>
        {chips && (
          <div className="flex flex-wrap gap-1 mt-2.5">
            {chips.map((c, i) => (
              <span key={i} className="text-[10px] px-2 py-0.5 rounded-md bg-zinc-100 dark:bg-zinc-800 text-zinc-500 dark:text-zinc-400">
                {c}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* 연결 상태 표시 */}
      <div className={`px-3.5 pb-3 flex items-center gap-1.5 text-[10px] ${t.text}`}>
        <span className={`w-1.5 h-1.5 rounded-full ${t.dot}`} />
        연결됨
      </div>
    </div>
  )
}

/** 노드 간 화살표 */
function Arrow({ label }) {
  return (
    <div className="flex flex-col items-center gap-1 px-2 shrink-0">
      {label && <span className="text-[10px] text-zinc-400 dark:text-zinc-500 whitespace-nowrap">{label}</span>}
      <div className="flex items-center">
        <div className="h-px w-10 bg-zinc-300 dark:bg-zinc-600" />
        <Ic name="arrowRight" className="w-4 h-4 text-zinc-400 -ml-2" />
      </div>
    </div>
  )
}

/**
 * 파이프라인 플로우 노드 시각화.
 * 4개 노드(트리거 → 스타일 → AI → 결과)가 좌→우 방향으로 연결된다.
 */
export function PipelineFlow() {
  return (
    <div className="flex items-center">
      <Node
        theme="amber"
        icon="mail"
        tag="트리거 노드"
        title="이메일 수신"
        desc="contract@office-ax.com 으로 문서가 도착하면 실행됩니다."
        chips={['스케줄 09:00', '첨부 .pdf/.hwp']}
      />
      <Arrow label="수신 문서" />
      <Node
        theme="violet"
        icon="sparkles"
        tag="스타일 / RAG 노드"
        title="스타일 참조"
        desc="업로드된 어투·서식 에셋을 참조해 문체를 정렬합니다."
        chips={['어투: 하람_보고서', '양식: 회사_기획서']}
      />
      <Arrow label="컨텍스트 주입" />
      <Node
        theme="blue"
        icon="bot"
        tag="AI 액션 노드"
        title="문서 분석 · 보정"
        desc="표 서식·날짜 표기 오류를 검출하고 자동 보정합니다."
        chips={['오류 검출', '날짜 통일', '표 정렬']}
      />
      <Arrow label="보정 결과" />
      <Node
        theme="emerald"
        icon="download"
        tag="결과 노드"
        title="최종본 생성 & 회신"
        desc="보정된 최종본을 생성해 발신자에게 자동 회신합니다."
        chips={['PDF 내보내기', '자동 회신']}
      />
    </div>
  )
}
