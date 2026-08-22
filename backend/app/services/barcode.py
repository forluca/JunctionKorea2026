"""문서에서 티켓 코드(QR/바코드)를 찾아 디코딩한다.

전략 (Parse의 figure 검출에 의존하지 않음):
1. 주 경로 — 원본 문서의 페이지 전체를 이미지로 렌더링(PDF는 PyMuPDF)해서 통째로 스캔
2. 보조 경로 — Upstage Parse가 준 figure 크롭(base64)도 스캔 (1에서 놓친 것 대비)

zxing-cpp 사용 — QR, Data Matrix, Aztec, PDF417, 1D 바코드 전부 지원.
지갑 표시용 크롭 이미지는 검출된 코드의 좌표 주변을 잘라 만든다.
"""

import base64

import cv2
import numpy as np
import pymupdf
import zxingcpp

_CROP_MARGIN = 30  # 코드 주변 여백(px)


def _crop_around(img: np.ndarray, position) -> bytes | None:
    """검출 좌표 주변을 여백을 두고 잘라 PNG bytes로 반환."""
    try:
        pts = [position.top_left, position.top_right,
               position.bottom_left, position.bottom_right]
        xs = [p.x for p in pts]
        ys = [p.y for p in pts]
        h, w = img.shape[:2]
        x0 = max(0, min(xs) - _CROP_MARGIN)
        x1 = min(w, max(xs) + _CROP_MARGIN)
        y0 = max(0, min(ys) - _CROP_MARGIN)
        y1 = min(h, max(ys) + _CROP_MARGIN)
        ok, png = cv2.imencode(".png", img[y0:y1, x0:x1])
        return png.tobytes() if ok else None
    except Exception:
        return None


def _scan_image(img: np.ndarray, found: list[dict], seen: set[str]) -> None:
    for res in zxingcpp.read_barcodes(img):
        if not res.text or res.text in seen:
            continue
        seen.add(res.text)
        crop = _crop_around(img, res.position)
        if crop is None:
            ok, png = cv2.imencode(".png", img)
            crop = png.tobytes() if ok else b""
        found.append({"value": res.text, "format": res.format.name, "png": crop})


def decode_barcodes(file_bytes: bytes, mime_type: str,
                    elements: list[dict] | None = None) -> list[dict]:
    """문서에서 발견된 코드 목록 반환: [{"value", "format", "png"(크롭 PNG bytes)}]"""
    found: list[dict] = []
    seen: set[str] = set()

    # 1) 원본 페이지 전체 스캔 (주 경로)
    try:
        if mime_type == "application/pdf":
            doc = pymupdf.open(stream=file_bytes, filetype="pdf")
            for page in doc:
                pix = page.get_pixmap(dpi=200)
                img = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)
                img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR if pix.n == 4 else cv2.COLOR_RGB2BGR)
                _scan_image(img, found, seen)
        elif mime_type.startswith("image/"):
            img = cv2.imdecode(np.frombuffer(file_bytes, np.uint8), cv2.IMREAD_COLOR)
            if img is not None:
                _scan_image(img, found, seen)
    except Exception:
        pass  # 렌더링 실패해도 보조 경로는 시도

    # 2) Parse figure 크롭 스캔 (보조 — 오피스 문서 등 렌더링 불가 형식 대비)
    for e in elements or []:
        if e.get("category") != "figure" or not e.get("base64_encoding"):
            continue
        try:
            raw = base64.b64decode(e["base64_encoding"])
            img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
            if img is not None:
                _scan_image(img, found, seen)
        except Exception:
            continue

    return found
