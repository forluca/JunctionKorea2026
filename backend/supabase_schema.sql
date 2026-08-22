-- Docket 스키마 — Supabase 대시보드 > SQL Editor에 붙여넣고 실행하세요.

create table if not exists trips (
  id uuid primary key default gen_random_uuid(),
  title text not null default '새 여행',
  start_date date,
  end_date date,
  status text not null default 'active',
  created_at timestamptz not null default now()
);

create table if not exists items (
  id uuid primary key default gen_random_uuid(),
  trip_id uuid not null references trips(id) on delete cascade,
  document_id uuid,
  type text,
  title text not null default '제목 없음',
  starts_at timestamptz,
  ends_at timestamptz,
  location text,
  price numeric,
  currency text,
  booking_ref text,
  qr_code text,
  qr_images jsonb,
  cancellation_deadline timestamptz,
  notes jsonb,          -- 사용자가 알아둬야 할 사항 문장 배열 (판단+주의사항 통합)
  has_conflict boolean not null default false,
  conflict_msg text,
  created_at timestamptz not null default now()
);

create table if not exists documents (
  id uuid primary key default gen_random_uuid(),
  item_id uuid references items(id) on delete set null,  -- 여행은 item_id → items.trip_id로 조회
  file_name text,
  mime_type text,
  storage_path text,
  doc_type text,
  parsed_html text,
  parsed_text text,
  extracted jsonb,
  created_at timestamptz not null default now()
);

create index if not exists idx_items_trip on items(trip_id, starts_at);
create index if not exists idx_documents_item on documents(item_id);

-- 스토리지 버킷(documents)은 서버가 시작 시 자동 생성을 시도하지만,
-- 권한 문제가 나면 대시보드 > Storage에서 'documents' 버킷을 직접 만들어 주세요.
