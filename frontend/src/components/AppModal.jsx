import { createContext, useContext, useState } from 'react'
import { createPortal } from 'react-dom'

const AppModalContext = createContext(null)

/** 모달 Context에서 showAlert, showConfirm을 꺼내 쓴다 */
export function useAppModal() {
  return useContext(AppModalContext)
}

/** 공통 백드롭 + 카드 래퍼 */
function ModalCard({ children }) {
  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-zinc-950/50 backdrop-blur-sm">
      <div className="bg-white dark:bg-zinc-900 rounded-2xl border border-zinc-200 dark:border-zinc-800 shadow-2xl p-6 w-80 fade-in">
        {children}
      </div>
    </div>,
    document.body,
  )
}

/**
 * 전역 모달 Provider.
 * main.jsx에서 앱 루트를 감싼다.
 *
 * showAlert(message)                                 → Promise<void>
 * showConfirm({ message, confirmLabel, danger })     → Promise<boolean>
 */
export function AppModalProvider({ children }) {
  const [modal, setModal] = useState(null)

  const showAlert = (message) =>
    new Promise((resolve) => setModal({ type: 'alert', message, resolve }))

  const showConfirm = ({ message, confirmLabel = '확인', danger = false }) =>
    new Promise((resolve) => setModal({ type: 'confirm', message, confirmLabel, danger, resolve }))

  const close = (value) => {
    modal?.resolve(value)
    setModal(null)
  }

  return (
    <AppModalContext.Provider value={{ showAlert, showConfirm }}>
      {children}

      {/* Alert 모달 */}
      {modal?.type === 'alert' && (
        <ModalCard>
          <p className="text-sm text-zinc-700 dark:text-zinc-200 leading-relaxed mb-5">
            {modal.message}
          </p>
          <div className="flex justify-end">
            <button
              onClick={() => close(undefined)}
              className="px-4 h-9 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium"
            >
              확인
            </button>
          </div>
        </ModalCard>
      )}

      {/* Confirm 모달 */}
      {modal?.type === 'confirm' && (
        <ModalCard>
          <p className="text-sm text-zinc-700 dark:text-zinc-200 leading-relaxed mb-5">
            {modal.message}
          </p>
          <div className="flex justify-end gap-2">
            <button
              onClick={() => close(false)}
              className="px-4 h-9 rounded-lg border border-zinc-200 dark:border-zinc-700 text-zinc-600 dark:text-zinc-300 text-sm hover:bg-zinc-50 dark:hover:bg-zinc-800"
            >
              취소
            </button>
            <button
              onClick={() => close(true)}
              className={`px-4 h-9 rounded-lg text-white text-sm font-medium ${
                modal.danger
                  ? 'bg-rose-600 hover:bg-rose-700'
                  : 'bg-blue-600 hover:bg-blue-700'
              }`}
            >
              {modal.confirmLabel}
            </button>
          </div>
        </ModalCard>
      )}
    </AppModalContext.Provider>
  )
}
