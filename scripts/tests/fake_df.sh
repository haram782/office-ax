#!/usr/bin/env bash
# 테스트 전용 가짜 df — restore의 디스크 용량 부족 분기만 재현한다.
echo "Filesystem 1024-blocks Used Available Capacity Mounted"
echo "fake 1 1 ${FAKE_DF_AVAILABLE_KB:-1} 100% /"
