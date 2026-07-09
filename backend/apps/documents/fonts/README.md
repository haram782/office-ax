# NotoSansKR-Regular.otf

PDF `redact_overlay` 패치 시 한글 replacement 텍스트를 렌더링하기 위해 임베드하는 폰트.

## 출처

- 원본: [Noto Sans CJK KR Regular](https://github.com/notofonts/noto-cjk) (SIL Open Font License 1.1, `OFL.txt` 참조)
- 이 저장소의 파일은 `fonttools pyftsubset`으로 원본(16MB, 전체 통합 한자 포함)에서
  한글·라틴·기본 문장부호만 추려낸 서브셋(1.4MB)이다.

## 왜 필요한가

`_apply_pdf_redact_overlay`(`backend/apps/documents/patcher.py`)가 PyMuPDF 내장
`fontname="korea-s"`를 쓰면, 그 폰트는 실제 글리프가 PDF에 **임베드되지 않고**
뷰어가 시스템에 "Batang" 폰트를 갖고 있다고 가정하는 참조 폰트다. 브라우저의
pdf.js는 이 참조를 해석하지 못해 새로 삽입한 한글 텍스트가 완전히 투명하게
렌더링된다(추출은 되지만 화면에는 안 보임). 이 폰트 파일을 직접 임베드하면
어떤 뷰어에서도 동일하게 보인다.

## 재생성 방법

```bash
curl -sSL -o /tmp/full.otf \
  "https://raw.githubusercontent.com/notofonts/noto-cjk/main/Sans/OTF/Korean/NotoSansCJKkr-Regular.otf"
pip install fonttools brotli
pyftsubset /tmp/full.otf \
  --output-file=NotoSansKR-Regular.otf \
  --unicodes="U+0020-007E,U+00A0,U+1100-11FF,U+3000-303F,U+3130-318F,U+AC00-D7A3,U+FF00-FFEF" \
  --layout-features='*' \
  --no-hinting
```
