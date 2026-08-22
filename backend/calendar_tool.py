import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# 사용자가 접근할 수 있는 권한 범위 : 캘린더의 event를 보고 수정할 수 있음
SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


def get_calendar_service():
    creds = None

    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file(
            "token.json",
            SCOPES
        )

    if not creds or not creds.valid:

        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())

        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json",
                SCOPES
            )

            creds = flow.run_local_server(port=0)

        with open("token.json", "w") as token:
            token.write(creds.to_json())

    service = build(
        "calendar",
        "v3",
        credentials=creds
    )

    return service

def create_event(
    title,
    start_time,
    end_time,
    description=None,
    location=None,
):
    service = get_calendar_service()

    event = {
        "summary": title,

        "start": {
            "dateTime": start_time,
            "timeZone": "Asia/Seoul",
        },

        "end": {
            "dateTime": end_time,
            "timeZone": "Asia/Seoul",
        },
    }

    if description:
        event["description"] = description

    if location:
        event["location"] = location

    created_event = (
        service.events()
        .insert(
            calendarId="primary",
            body=event,
        )
        .execute()
    )

    return created_event


##################################
########test code ################
'''
create_event(
    title="Junction 회의",
    start_time="2026-08-22T14:00:00+09:00",
    end_time="2026-08-22T15:00:00+09:00",
    description="Junction 아이디어 회의",
)
---> Google calendar의 기본 캘린더에 일정이 생성됨 
 '''

if __name__ == "__main__":
    create_event(
        title="Calendar API Test2",
        start_time="2026-08-23T15:00:00+09:00",
        end_time="2026-08-23T16:00:00+09:00",
    )


