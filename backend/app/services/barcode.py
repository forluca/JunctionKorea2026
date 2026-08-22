"""Parse가 준 figure 크롭(base64)에서 티켓 코드를 디코딩한다.

zxing-cpp 사용 — QR, Data Matrix, Aztec, PDF417, 1D 바코드 전부 지원.
(실제 티켓은 QR보다 Data Matrix/Aztec인 경우가 많음)
"""

import base64

import cv2
import numpy as np
import zxingcpp


def decode_barcodes(elements: list[dict]) -> list[dict]:
    """Parse 응답 elements의 figure 크롭을 스캔해 발견된 코드 목록을 반환.

    반환: [{"value": 코드 값, "format": 코드 포맷명, "png": 원본 크롭 PNG bytes}]
    같은 값이 여러 크롭에서 나오면 첫 번째만 유지.
    """
    found: list[dict] = []
    seen: set[str] = set()
    for e in elements:
        if e.get("category") != "figure" or not e.get("base64_encoding"):
            continue
        try:
            raw = base64.b64decode(e["base64_encoding"])
            img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                continue
            for res in zxingcpp.read_barcodes(img):
                if not res.text or res.text in seen:
                    continue
                seen.add(res.text)
                ok, png = cv2.imencode(".png", img)
                found.append({
                    "value": res.text,
                    "format": res.format.name,
                    "png": png.tobytes() if ok else raw,
                })
        except Exception:
            continue  # 크롭 하나 실패가 파이프라인을 막지 않게
    return found
