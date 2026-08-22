"""문서 유형 카테고리와 유형별 Information Extraction 스키마.

주의: IE API 제약으로 스키마 1레벨 프로퍼티는 string/integer/number/array만 허용
(object/boolean 불가). boolean 성격의 필드는 "yes"/"no"/"unknown" string으로 정의한다.
날짜/시각은 ISO 8601(YYYY-MM-DD, HH:MM) 문자열로 추출하도록 description에 명시.
"""

CATEGORIES = [
    {"name": "hotel", "description": "Hotel, hostel, or accommodation booking confirmation / voucher"},
    {"name": "flight", "description": "Flight ticket, e-ticket, or airline booking confirmation"},
    {"name": "train", "description": "Train, bus, or ferry ticket / reservation"},
    {"name": "attraction_ticket", "description": "Museum, attraction, theme park, or event entry ticket / voucher"},
    {"name": "rental_car", "description": "Rental car booking confirmation or voucher"},
    {"name": "tour", "description": "Guided tour, activity, or experience booking voucher"},
    {"name": "receipt", "description": "Purchase receipt or payment invoice"},
    {"name": "other", "description": "Any other document that does not fit the categories above"},
]

CATEGORY_NAMES = {c["name"] for c in CATEGORIES}

_COMMON = {
    "booking_reference": {"type": "string", "description": "Booking/reservation/confirmation number or PNR"},
    "total_price": {"type": "number", "description": "Total price as a number without currency symbol"},
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
    "flight": {
        "type": "object",
        "properties": {
            "airline": {"type": "string"},
            "flight_number": {"type": "string"},
            "departure_airport": {"type": "string", "description": "Airport name or IATA code"},
            "arrival_airport": {"type": "string", "description": "Airport name or IATA code"},
            "departure_datetime": {"type": "string", "description": "ISO 8601 YYYY-MM-DDTHH:MM"},
            "arrival_datetime": {"type": "string", "description": "ISO 8601 YYYY-MM-DDTHH:MM"},
            "passenger_names": {"type": "array", "items": {"type": "string"}},
            "seat": {"type": "string"},
            **_COMMON,
        },
    },
    "train": {
        "type": "object",
        "properties": {
            "operator": {"type": "string", "description": "Train/bus/ferry operator"},
            "service_number": {"type": "string", "description": "Train or bus number"},
            "departure_station": {"type": "string"},
            "arrival_station": {"type": "string"},
            "departure_datetime": {"type": "string", "description": "ISO 8601 YYYY-MM-DDTHH:MM"},
            "arrival_datetime": {"type": "string", "description": "ISO 8601 YYYY-MM-DDTHH:MM"},
            "passenger_names": {"type": "array", "items": {"type": "string"}},
            "seat": {"type": "string"},
            **_COMMON,
        },
    },
    "attraction_ticket": {
        "type": "object",
        "properties": {
            "venue_name": {"type": "string"},
            "address": {"type": "string"},
            "visit_date": {"type": "string", "description": "YYYY-MM-DD"},
            "entry_time": {"type": "string", "description": "Timed entry slot HH:MM if present"},
            "valid_until": {"type": "string", "description": "Ticket validity end date if present"},
            "ticket_type": {"type": "string", "description": "Adult/child/combo etc."},
            "num_persons": {"type": "integer"},
            "onsite_exchange_required": {"type": "string", "description": "yes / no / unknown — must the voucher be exchanged for a physical ticket on site?"},
            **_COMMON,
        },
    },
    "rental_car": {
        "type": "object",
        "properties": {
            "company": {"type": "string"},
            "pickup_location": {"type": "string"},
            "pickup_datetime": {"type": "string", "description": "ISO 8601 YYYY-MM-DDTHH:MM"},
            "dropoff_location": {"type": "string"},
            "dropoff_datetime": {"type": "string", "description": "ISO 8601 YYYY-MM-DDTHH:MM"},
            "driver_name": {"type": "string"},
            "car_class": {"type": "string"},
            **_COMMON,
        },
    },
    "tour": {
        "type": "object",
        "properties": {
            "tour_name": {"type": "string"},
            "provider": {"type": "string"},
            "meeting_point": {"type": "string"},
            "start_datetime": {"type": "string", "description": "ISO 8601 YYYY-MM-DDTHH:MM"},
            "duration": {"type": "string", "description": "e.g. 3 hours"},
            "num_persons": {"type": "integer"},
            "onsite_exchange_required": {"type": "string", "description": "yes / no / unknown"},
            **_COMMON,
        },
    },
    "receipt": {
        "type": "object",
        "properties": {
            "merchant_name": {"type": "string"},
            "address": {"type": "string"},
            "purchase_datetime": {"type": "string", "description": "ISO 8601 YYYY-MM-DDTHH:MM"},
            "line_items": {"type": "array", "items": {"type": "string"}, "description": "Purchased item names"},
            "payment_method": {"type": "string"},
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
}
