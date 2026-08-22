from functools import lru_cache

from supabase import Client, create_client

from app import config


@lru_cache
def get_db() -> Client:
    if not config.SUPABASE_URL:
        raise RuntimeError(
            "SUPABASE_URL이 .env에 없습니다. "
            "Supabase 대시보드 > Settings > API의 Project URL을 "
            "SUPABASE_URL=https://<project-ref>.supabase.co 형태로 추가하세요."
        )
    return create_client(config.SUPABASE_URL, config.SUPABASE_KEY)


def ensure_bucket() -> None:
    """문서 원본 저장용 스토리지 버킷을 없으면 생성한다."""
    try:
        get_db().storage.create_bucket(config.STORAGE_BUCKET)
    except Exception:
        pass  # 이미 존재
