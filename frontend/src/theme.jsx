import { createContext, useContext, useState } from 'react'

const ThemeContext = createContext(null)

/**
 * 다크 모드 토글 컨텍스트 프로바이더.
 * 최상위 <div class="dark"> 래퍼를 직접 제어한다.
 */
export function ThemeProvider({ children }) {
  const [theme, setTheme] = useState('light')
  const toggleTheme = () => setTheme(t => (t === 'dark' ? 'light' : 'dark'))

  return (
    <ThemeContext.Provider value={{ theme, toggleTheme }}>
      {/* Tailwind darkMode:'class' — 이 div에 "dark" 클래스가 붙으면 하위 전체 다크 적용 */}
      <div className={theme === 'dark' ? 'dark' : ''} style={{ minHeight: '100%' }}>
        {children}
      </div>
    </ThemeContext.Provider>
  )
}

export function useTheme() {
  return useContext(ThemeContext)
}
