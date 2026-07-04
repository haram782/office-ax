/**
 * 크레딧 소진(429) 프론트 처리 테스트.
 *
 * closed-beta-launch-plan-v1-ko.md 결정 16:
 *   - 어떤 API든 429 응답이 오면 전역 이벤트로 알리고 안내 모달을 띄운다
 *   - 각 훅의 개별 에러 처리는 그대로 유지한다 (인터셉터는 reject를 삼키지 않는다)
 *
 * Red → Green → Refactor
 */

import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

import { api } from '../src/api/client'

/** 등록된 axios response 인터셉터의 rejected 핸들러를 찾는다 */
function findRejectedHandler() {
  return api.interceptors.response.handlers.find((h) => h && h.rejected)?.rejected
}

function make429Error(message = '이번 달 사용량을 모두 썼어요.') {
  return {
    response: { status: 429, data: { error: message, credits_used: 200, credits_limit: 200 } },
  }
}

describe('429 응답 인터셉터', () => {
  it('response 인터셉터가 등록되어 있다', () => {
    expect(findRejectedHandler()).toBeTruthy()
  })

  it('429 응답이면 ax:credit-exhausted 이벤트를 발행하고 reject를 유지한다', async () => {
    const listener = vi.fn()
    window.addEventListener('ax:credit-exhausted', listener)

    const rejected = findRejectedHandler()
    await expect(rejected(make429Error('한도 초과 문구'))).rejects.toBeTruthy()

    expect(listener).toHaveBeenCalledTimes(1)
    expect(listener.mock.calls[0][0].detail).toContain('한도 초과')
    window.removeEventListener('ax:credit-exhausted', listener)
  })

  it('[회귀] 429가 아닌 에러는 이벤트 없이 그대로 reject된다', async () => {
    const listener = vi.fn()
    window.addEventListener('ax:credit-exhausted', listener)

    const rejected = findRejectedHandler()
    await expect(
      rejected({ response: { status: 500, data: {} } })
    ).rejects.toBeTruthy()

    expect(listener).not.toHaveBeenCalled()
    window.removeEventListener('ax:credit-exhausted', listener)
  })
})
