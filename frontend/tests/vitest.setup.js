import '@testing-library/jest-dom'

// Node 26의 미설정 전역 localStorage가 happy-dom storage를 가리지 않게 한다.
if (typeof globalThis.localStorage === 'undefined') {
  const values = new Map()
  const storage = {
    clear: () => values.clear(),
    getItem: (key) => values.has(String(key)) ? values.get(String(key)) : null,
    key: (index) => [...values.keys()][index] ?? null,
    removeItem: (key) => values.delete(String(key)),
    setItem: (key, value) => values.set(String(key), String(value)),
    get length() { return values.size },
  }
  Object.defineProperty(globalThis, 'localStorage', {
    configurable: true,
    value: storage,
  })
}
