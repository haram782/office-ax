/**
 * deriveChangeSuggestions — patch_changes 브랜치 단위 테스트
 * Red → Green → Refactor TDD
 */

import { describe, it, expect } from 'vitest'
import { deriveChangeSuggestions } from '../src/utils/changeSuggestions'

describe('deriveChangeSuggestions — patch_changes', () => {
  it('patch_changes 배열이 있으면 각 항목이 changeDbId를 가진 suggestion으로 변환된다', () => {
    const snippetData = {
      patch_changes: [
        {
          id: 99,
          operation_id: 'op-abc',
          title: '표 헤더 굵게',
          original: '기존 텍스트',
          replacement: '새 텍스트',
          reason: '가독성 향상',
          confidence: 0.9,
          anchor: { type: 'cell', cell: 'A1', sheet: 'Sheet1' },
          status: 'pending',
        },
      ],
    }

    const suggestions = deriveChangeSuggestions(snippetData)

    expect(suggestions).toHaveLength(1)
    expect(suggestions[0].changeDbId).toBe(99)
    expect(suggestions[0].id).toBe('op-abc')
    expect(suggestions[0].title).toBe('표 헤더 굵게')
    expect(suggestions[0].source).toBe('patch_changes')
  })

  it('patch_changes와 edit_suggestions가 함께 있을 때 모두 포함된다', () => {
    const snippetData = {
      edit_suggestions: [
        { id: 'es-1', title: '기존 제안', anchor: { type: 'text_match', target_text: '안녕' } },
      ],
      patch_changes: [
        {
          id: 77,
          operation_id: 'op-xyz',
          title: 'patch 제안',
          anchor: { type: 'cell', cell: 'B2', sheet: 'Sheet1' },
        },
      ],
    }

    const suggestions = deriveChangeSuggestions(snippetData)

    // edit_suggestions + patch_changes = 2건 (anchor 겹치지 않음)
    expect(suggestions.length).toBeGreaterThanOrEqual(2)
    const patchSuggestion = suggestions.find(s => s.source === 'patch_changes')
    expect(patchSuggestion).toBeDefined()
    expect(patchSuggestion.changeDbId).toBe(77)
  })

  it('patch_changes 항목에 operation_id 없으면 인덱스 기반 id가 부여된다', () => {
    const snippetData = {
      patch_changes: [
        { id: 55, title: '항목 없음' },
      ],
    }

    const suggestions = deriveChangeSuggestions(snippetData)

    expect(suggestions[0].id).toBe('patch-0')
    expect(suggestions[0].changeDbId).toBe(55)
  })
})
