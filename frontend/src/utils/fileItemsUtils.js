/**
 * useFileItems 의 핵심 매칭 로직 — React/JSX 의존 없는 순수 함수.
 * Node.js assert 테스트와 DocumentPanel.jsx 양쪽에서 임포트한다.
 */

/**
 * userMsg 에 대응하는 assistant 메시지를 반환한다.
 *
 * 1순위: upload_log.id 가 일치하는 assistant 메시지 (백엔드 명시 연결).
 * 2순위: upload_log 가 없는 구형 메시지 — 위치 기반 폴백.
 *        upload_log 있는 다른 파일의 결과를 탈취하지 않도록 !m.upload_log 조건 필수.
 *
 * @param {Array}  messages   - 전체 메시지 배열 (role, upload_log?.id 포함)
 * @param {Object} userMsg    - upload_log.id 를 가진 user 메시지
 * @returns {Object|null}     - 매칭된 assistant 메시지 또는 null
 */
export function resolveAssistantMsg(messages, userMsg) {
  const userUploadId = userMsg.upload_log.id
  const idx = messages.indexOf(userMsg)

  // 1순위: id 기반 정확한 매칭
  const linkedMsg = messages.find(
    m => m.role === 'assistant' && m.upload_log?.id === userUploadId,
  )

  // 2순위: upload_log 없는 구형 메시지 — 위치 기반 폴백.
  //   - 다음 user 메시지(텍스트 전용 포함) 이전까지만 검색 — 이후는 다른 대화 턴
  //   - upload_log 있는 다른 파일 결과를 탈취하지 않도록 !m.upload_log 조건 필수
  let positionalMsg = null
  if (!linkedMsg) {
    const sliceAfterUser = messages.slice(idx + 1)
    const nextUserIdx = sliceAfterUser.findIndex(m => m.role === 'user')
    // nextUserIdx === -1: 이후에 user 메시지 없음 → 끝까지 검색
    const searchRange = nextUserIdx === -1
      ? sliceAfterUser
      : sliceAfterUser.slice(0, nextUserIdx)
    positionalMsg = searchRange.find(m => m.role === 'assistant' && !m.upload_log) ?? null
  }

  return linkedMsg ?? positionalMsg ?? null
}

/**
 * messages 배열에서 파일 아이템 목록을 추출한다 (최신 순).
 * DocumentPanel.jsx 의 useFileItems 와 동일한 매핑 로직.
 *
 * @param {Array} messages
 * @returns {Array}
 */
export function deriveFileItems(messages) {
  return messages
    .filter(m => m.role === 'user' && m.upload_log?.id)
    .reverse()
    .map(userMsg => {
      const assistantMsg = resolveAssistantMsg(messages, userMsg)
      return {
        id: userMsg.upload_log.id,
        filename: userMsg.upload_log.original_filename,
        fileUrl: userMsg.upload_log.file_url || '',
        status: assistantMsg
          ? 'done'
          : (userMsg._pending ? 'processing' : (userMsg.upload_log.status ?? 'processing')),
        artifactUrl: assistantMsg?.artifact_url || '',
        snippetData: assistantMsg?.snippet_data || null,
      }
    })
}
