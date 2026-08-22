from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# 사용자가 접근할 수 있는 권한 범위 : 캘린더의 event를 보고 수정할 수 있음
SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
TIME_ZONE = "Asia/Seoul"
KST = ZoneInfo(TIME_ZONE)
ONE_DAY_MINUTES = 24 * 60
MAX_REMINDER_MINUTES = 4 * 7 * 24 * 60

BASE_DIR = Path(__file__).resolve().parent
CREDENTIALS_FILE = BASE_DIR / "credentials.json"
TOKEN_FILE = BASE_DIR / "token.json"


def get_calendar_service():
    """OAuth 인증 정보를 사용해 Google Calendar API 서비스를 반환한다."""
    creds = None

    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:

        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())

        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")

    return build("calendar", "v3", credentials=creds)


def _as_datetime(value: str | datetime, field_name: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (AttributeError, ValueError) as exc:
            raise ValueError(f"{field_name} must be an ISO 8601 datetime") from exc

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=KST)
    return parsed

def create_event(
    title: str,
    start_time: str | datetime,
    end_time: str | datetime,
    description: str | None = None,
    location: str | None = None,
    email_reminder_minutes: int | None = ONE_DAY_MINUTES,
    calendar_id: str = "primary",
    service=None,
):
    """캘린더 이벤트를 만들고 필요하면 이메일 리마인더를 설정한다."""
    start = _as_datetime(start_time, "start_time")
    end = _as_datetime(end_time, "end_time")
    if end <= start:
        raise ValueError("end_time must be later than start_time")

    event = {
        "summary": title,
        "start": {
            "dateTime": start.isoformat(),
            "timeZone": TIME_ZONE,
        },
        "end": {
            "dateTime": end.isoformat(),
            "timeZone": TIME_ZONE,
        },
    }

    if description:
        event["description"] = description

    if location:
        event["location"] = location

    if email_reminder_minutes is not None:
        if not 0 <= email_reminder_minutes <= MAX_REMINDER_MINUTES:
            raise ValueError(
                f"email_reminder_minutes must be between 0 and {MAX_REMINDER_MINUTES}"
            )
        event["reminders"] = {
            "useDefault": False,
            "overrides": [
                {
                    "method": "email",
                    "minutes": email_reminder_minutes,
                }
            ],
        }

    calendar_service = service or get_calendar_service()
    return (
        calendar_service.events()
        .insert(calendarId=calendar_id, body=event)
        .execute()
    )


def create_schedule_reminder(
    item: dict,
    service=None,
    email_reminder_minutes: int = ONE_DAY_MINUTES,
):
    """DB의 items 행으로 일반 일정을 만들고 시작 하루 전에 이메일로 알린다."""
    if not item.get("starts_at"):
        raise ValueError("item.starts_at is required")

    start = _as_datetime(item["starts_at"], "item.starts_at")
    end = (
        _as_datetime(item["ends_at"], "item.ends_at")
        if item.get("ends_at")
        else start + timedelta(hours=1)
    )
    message = item.get("schedule_message") or item.get("notes")

    return create_event(
        title=item.get("title") or "일정",
        start_time=start,
        end_time=end,
        description=message,
        location=item.get("location"),
        email_reminder_minutes=email_reminder_minutes,
        service=service,
    )


def create_cancellation_deadline_reminder(
    item: dict,
    service=None,
    email_reminder_minutes: int = ONE_DAY_MINUTES,
):
    """취소 기한 이벤트를 만들고 기한 하루 전에 이메일로 알린다."""
    if not item.get("cancellation_deadline"):
        return None

    deadline = _as_datetime(
        item["cancellation_deadline"],
        "item.cancellation_deadline",
    )
    message = item.get("cancellation_message") or item.get("notes")
    description_parts = [
        f"취소 가능 기한: {deadline.astimezone(KST).strftime('%Y-%m-%d %H:%M')}",
    ]
    if message:
        description_parts.append(str(message))

    return create_event(
        title=f"[취소 마감] {item.get('title') or '예약'}",
        start_time=deadline,
        end_time=deadline + timedelta(minutes=30),
        description="\n\n".join(description_parts),
        email_reminder_minutes=email_reminder_minutes,
        service=service,
    )


def create_calendar_reminders_for_item(
    item: dict,
    email_reminder_minutes: int = ONE_DAY_MINUTES,
) -> dict:
    """하나의 DB item에 대해 일반 일정과 취소 기한 일정을 함께 생성한다."""
    service = get_calendar_service()
    created_events = {}

    if item.get("starts_at"):
        created_events["schedule"] = create_schedule_reminder(
            item,
            service=service,
            email_reminder_minutes=email_reminder_minutes,
        )

    cancellation_event = create_cancellation_deadline_reminder(
        item,
        service=service,
        email_reminder_minutes=email_reminder_minutes,
    )
    if cancellation_event:
        created_events["cancellation"] = cancellation_event

    return created_events
