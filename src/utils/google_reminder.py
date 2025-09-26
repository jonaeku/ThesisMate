import datetime
from dateutil import parser as date_parser
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import os

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]  # minimal read-only scope


def get_abs_path(rel_path):
    return os.path.join(os.path.dirname(__file__), rel_path)

def load_credentials(credentials_path="credentials.json", token_path="token.json"):
    credentials_path = get_abs_path(credentials_path)
    token_path = get_abs_path(token_path)
    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # interactive auth: pop a browser window for first-time login
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
            creds = flow.run_local_server(port=0)  # will open browser and store consent/refresh token
        # save for next time
        with open(token_path, "w") as f:
            f.write(creds.to_json())
    return creds

def get_upcoming_events(creds, calendar_id="a73fcdacbde46c50f9788741e039f09c54218e915dc384d63e1e34f257d31bee@group.calendar.google.com", max_results=10, within_days=None):
    service = build("calendar", "v3", credentials=creds)
    now = datetime.datetime.utcnow().isoformat() + "Z"
    params = {
        "calendarId": calendar_id,
        "timeMin": now,
        "maxResults": max_results,
        "singleEvents": True,
        "orderBy": "startTime",
    }
    if within_days is not None:
        time_max = (datetime.datetime.utcnow() + datetime.timedelta(days=within_days)).isoformat() + "Z"
        params["timeMax"] = time_max

    events_result = service.events().list(**params).execute()
    events = events_result.get("items", [])
    return events

def next_deadline_message(credentials_path="credentials.json", token_path="token.json", within_days=30):
    creds = load_credentials(credentials_path, token_path)
    events = get_upcoming_events(creds, within_days=within_days, max_results=5)
    if not events:
        return None
    # pick the soonest event (events are ordered by startTime)
    e = events[0]
    start_raw = e["start"].get("dateTime", e["start"].get("date"))  # handles all-day events
    start_dt = date_parser.parse(start_raw)
    now = datetime.datetime.now(tz=start_dt.tzinfo or datetime.timezone.utc)
    days_left = (start_dt - now).days
    title = e.get("summary", "(no title)")
    formatted_date = start_dt.strftime("%d.%m.%Y")

    # Generate message depending on urgency
    if days_left <= 1:
        human = f"⚠️ URGENT: **{title}** is due on **{formatted_date}** (in {days_left} day{'s' if days_left != 1 else ''})!"
    elif days_left <= 7:
        human = f"⏳ Heads up: **{title}** is coming up soon — **{formatted_date}** (in {days_left} days)."
    else:
        human = f"📅 FYI: Your next deadline is **{title}** on **{formatted_date}** (in {days_left} days)."

    return {
        "title": title,
        "start": start_raw,
        "days_left": days_left,
        "message": human,
    }


if __name__ == "__main__":
    reminder = next_deadline_message()
    if reminder:
        print(reminder["message"])
    else:
        print("No upcoming deadlines found.")