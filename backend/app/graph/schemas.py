"""문서 유형 카테고리와 유형별 Information Extraction 스키마.

주의: IE API 제약으로 스키마 1레벨 프로퍼티는 string/integer/number/array만 허용
(object/boolean 불가). boolean 성격의 필드는 "yes"/"no"/"unknown" string으로 정의한다.
날짜/시각은 ISO 8601(YYYY-MM-DD, HH:MM) 문자열로 추출하도록 description에 명시.
"""

# 현재 지원 유형: hotel / transportation / tour (+ other는 분류 안전망)
# 유형 추가 시: 여기에 카테고리 1줄 + 아래 EXTRACTION_SCHEMAS에 스키마 1개
CATEGORIES = [
    {"name": "hotel", "description": "Hotel, hostel, or accommodation booking confirmation / voucher"},
    {"name": "transportation", "description": "Any transport ticket or booking: flight e-ticket, train, bus, or ferry"},
    {"name": "tour", "description": "Guided tour, activity, attraction entry, or experience booking voucher"},
    {"name": "other", "description": "Any other document that does not fit the categories above"},
]

CATEGORY_NAMES = {c["name"] for c in CATEGORIES}

_COMMON = {
    "booking_reference": {"type": "string", "description": "Booking/reservation/confirmation number or PNR"},
    "total_price": {"type": "number", "description": "Total price as a number without currency symbol. Use 0 ONLY if the document explicitly states it is free. Use -1 if no price is stated anywhere in the document."},
    "currency": {"type": "string", "description": "Currency code, e.g. KRW, USD, EUR, JPY"},
    "cancellation_deadline": {"type": "string", "description": "Free-cancellation or refund deadline in ISO 8601 if present"},
    "confirmation_status": {"type": "string", "description": "confirmed / pending / cancelled / unknown"},
    "notes": {"type": "string", "description": "Important fine print: entry rules, no re-entry, ID required, etc."},
}

EXTRACTION_SCHEMAS: dict[str, dict] = {
    "hotel": {
        "type": "object",
        "properties": {
            "hotel_name": {"type": "string"},
            "address": {"type": "string", "description": "Full address of the property"},
            "check_in_date": {"type": "string", "description": "YYYY-MM-DD"},
            "check_in_time": {"type": "string", "description": "HH:MM if stated"},
            "check_out_date": {"type": "string", "description": "YYYY-MM-DD"},
            "check_out_time": {"type": "string", "description": "HH:MM if stated"},
            "guests": {"type": "integer", "description": "Number of guests"},
            "room_type": {"type": "string"},
            **_COMMON,
        },
    },
    # 항공·기차·버스·페리 통합
    "transportation": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "description": "flight / train / bus / ferry"},
            "carrier": {"type": "string", "description": "Airline or transport operator name"},
            "service_number": {"type": "string", "description": "Flight number or train/bus number, e.g. KE937"},
            "departure_location": {"type": "string", "description": "Departure airport/station name or code"},
            "arrival_location": {"type": "string", "description": "Arrival airport/station name or code"},
            "departure_datetime": {"type": "string", "description": "ISO 8601 YYYY-MM-DDTHH:MM"},
            "arrival_datetime": {"type": "string", "description": "ISO 8601 YYYY-MM-DDTHH:MM"},
            "is_round_trip": {"type": "string", "description": "yes / no — does this ticket include a return leg?"},
            "return_departure_datetime": {"type": "string", "description": "Return leg departure, ISO 8601, if round trip"},
            "return_arrival_datetime": {"type": "string", "description": "Return leg arrival, ISO 8601, if round trip"},
            "passenger_names": {"type": "array", "items": {"type": "string"}},
            "seat": {"type": "string"},
            **_COMMON,
        },
    },
    # 투어·액티비티·관광지 입장권 통합
    "tour": {
        "type": "object",
        "properties": {
            "tour_name": {"type": "string", "description": "Tour/activity/attraction name"},
            "provider": {"type": "string"},
            "meeting_point": {"type": "string", "description": "Meeting point or venue address"},
            "start_datetime": {"type": "string", "description": "ISO 8601 YYYY-MM-DDTHH:MM (timed entry slot if any)"},
            "duration": {"type": "string", "description": "e.g. 3 hours"},
            "valid_until": {"type": "string", "description": "Ticket validity end date if present"},
            "ticket_type": {"type": "string", "description": "Adult/child/combo etc."},
            "num_persons": {"type": "integer"},
            "onsite_exchange_required": {"type": "string", "description": "yes / no / unknown — must the voucher be exchanged for a physical ticket on site?"},
            **_COMMON,
        },
    },
    "other": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Best short title for this document"},
            "date": {"type": "string", "description": "Main date in the document, ISO 8601"},
            "location": {"type": "string"},
            "summary": {"type": "string", "description": "One-sentence summary of the document"},
            **_COMMON,
        },
    },
    # 전체 여행 계획 문서 (targetType=trip 전용 — classify를 거치지 않음)
    # 일정 항목들을 배열로 추출 (1레벨 제약: 배열 내부 객체는 허용됨)
    "itinerary": {
        "type": "object",
        "properties": {
            "trip_title": {"type": "string", "description": "Title of the trip, e.g. 'Rome & Barcelona Trip'"},
            "destination": {"type": "string", "description": "Main destination(s)"},
            "start_date": {"type": "string", "description": "Trip start date YYYY-MM-DD"},
            "end_date": {"type": "string", "description": "Trip end date YYYY-MM-DD"},
            "schedule_items": {
                "type": "array",
                "description": "Every scheduled entry in the plan, in order",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Name of the activity/place/booking"},
                        "date": {"type": "string", "description": "YYYY-MM-DD, or relative like 'Day 2' if no absolute date"},
                        "start_time": {"type": "string", "description": "HH:MM if stated"},
                        "end_time": {"type": "string", "description": "HH:MM if stated"},
                        "location": {"type": "string"},
                        "category": {"type": "string", "description": "hotel / flight / train / attraction / food / transport / other"},
                        "notes": {"type": "string"},
                    },
                },
            },
        },
    },
}
