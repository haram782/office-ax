# NotoSansKR-Regular.ttf

PDF `redact_overlay` 패치 시 한글 replacement 텍스트를 렌더링하기 위해 임베드하는 폰트.

## 출처

- 원본: [Noto Sans KR](https://github.com/google/fonts/tree/main/ofl/notosanskr) 가변 폰트
  (SIL Open Font License 1.1, `OFL.txt` 참조)
- `fontTools.varLib.instancer`로 wght=400(Regular) 정적 인스턴스를 뽑은 뒤,
  `pyftsubset`으로 한글·라틴·기본 문장부호만 남긴 서브셋(2.5MB)이다.

## 왜 필요한가

`_apply_pdf_redact_overlay`(`backend/apps/documents/patcher.py`)가 PyMuPDF 내장
`fontname="korea-s"`를 쓰면, 그 폰트는 실제 글리프가 PDF에 **임베드되지 않고**
뷰어가 시스템에 "Batang" 폰트를 갖고 있다고 가정하는 참조 폰트다. 브라우저의
pdf.js는 이 참조를 해석하지 못해 새로 삽입한 한글 텍스트가 완전히 투명하게
렌더링된다(추출은 되지만 화면에는 안 보임). 이 폰트 파일을 직접 임베드하면
어떤 뷰어에서도 동일하게 보인다.

## 왜 CFF(.otf) 대신 TrueType(.ttf)인가

처음에는 "Noto Sans **CJK** KR"(범-CJK 통합 폰트, CFF/CID-keyed, 16MB)을
`pyftsubset`으로 서브셋했으나, 이 폰트의 FDArray/FDSelect 구조(지역별 글리프
변형 선택용) 때문에 서브셋 결과에서 한글 글리프 외곽선이 깨져 완전히
투명하게 렌더링되는 문제가 있었다(추출은 되는데 화면에는 안 보임 — 원래
버그와 증상이 같아서 회귀 테스트로도 못 잡을 뻔했다. `get_fonts()`로
임베드 여부만 보고 넘어가면 안 되고 실제 렌더링까지 확인해야 하는 이유).

"Noto Sans KR"(한국어 전용, TrueType/glyf, 이 파일의 출처)은 그런 다지역
CID 구조가 없어 서브셋이 안전하다. 대신 가변 폰트라서 굵기(wght)를 먼저
고정 인스턴스로 뽑아야 한다.

## 재생성 방법

```bash
curl -sSL -o /tmp/var.ttf \
  "https://raw.githubusercontent.com/google/fonts/main/ofl/notosanskr/NotoSansKR%5Bwght%5D.ttf"
pip install fonttools brotli

python -c "
from fontTools.varLib.instancer import instantiateVariableFont
from fontTools.ttLib import TTFont
font = TTFont('/tmp/var.ttf')
instantiateVariableFont(font, {'wght': 400}).save('/tmp/regular.ttf')
"

pyftsubset /tmp/regular.ttf \
  --output-file=NotoSansKR-Regular.ttf \
  --unicodes="U+0020-007E,U+00A0,U+3000-303F,U+3130-318F,U+AC00-D7A3,U+FF00-FFEF" \
  --layout-features='*'
```

재생성 후 반드시 실제 렌더링(픽스맵)까지 확인할 것 — `get_text()` 추출
성공만으로는 글리프가 실제로 그려지는지 알 수 없다:

```python
import fitz
doc = fitz.open(); page = doc.new_page()
page.insert_font(fontname="Test", fontfile="NotoSansKR-Regular.ttf")
page.insert_text((72, 100), "한글 테스트 ABC123", fontsize=12, fontname="Test")
page.get_pixmap(matrix=fitz.Matrix(3, 3)).save("/tmp/check.png")  # 눈으로 직접 확인
```
