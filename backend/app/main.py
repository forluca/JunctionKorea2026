from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router

app = FastAPI(title="Docket Backend", version="0.1.0")


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """예기치 못한 에러를 원인이 보이는 JSON으로 반환 (디버깅용)."""
    return JSONResponse(
        {"error": type(exc).__name__, "detail": str(exc)[:800]},
        status_code=500,
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 해커톤 데모용
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")


@app.get("/health")
def health():
    return {"ok": True}
