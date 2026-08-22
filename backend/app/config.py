import os

from dotenv import find_dotenv, load_dotenv

# 리포 루트의 .env를 위로 탐색해서 로드
load_dotenv(find_dotenv())

UPSTAGE_API_KEY = (os.getenv("UPSTAGE_API") or os.getenv("UPSTAGE_API_KEY") or "").strip()
SUPABASE_KEY = (os.getenv("SUPABASE_API") or os.getenv("SUPABASE_KEY") or "").strip()
SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").strip()

UPSTAGE_BASE_URL = "https://api.upstage.ai/v1"
LLM_MODEL = os.getenv("UPSTAGE_LLM_MODEL", "solar-pro2")
STORAGE_BUCKET = os.getenv("SUPABASE_BUCKET", "documents")
