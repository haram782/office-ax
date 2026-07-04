import { useEffect, useState } from 'react'

/**
 * 크레딧 소진 안내 모달.
 *
 * api/client.js의 429 인터셉터가 발행하는 ax:credit-exhausted 이벤트를 받아
 * 앱 어디에서든 동일한 안내를 띄운다. App 루트에 한 번만 마운트한다.
 */
export default function CreditLimitModal() {
  const [message, setMessage] = useState(null)

  useEffect(() => {
    const onExhausted = (e) => setMessage(e.detail)
    window.addEventListener('ax:credit-exhausted', onExhausted)
    return () => window.removeEventListener('ax:credit-exhausted', onExhausted)
  }, [])

  if (!message) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
      <div className="max-w-[380px] w-full rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-6 fade-in">
        <div className="font-bold text-zinc-800 dark:text-zinc-100 text-base mb-2">
          이번 달 사용량 소진
        </div>
        <p className="text-sm text-zinc-500 dark:text-zinc-400 leading-relaxed mb-5">{message}</p>
        <button
          onClick={() => setMessage(null)}
          className="w-full h-10 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
        >
          확인
        </button>
      </div>
    </div>
  )
}
