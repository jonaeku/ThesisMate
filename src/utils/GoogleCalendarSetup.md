# 📅 Setup Guide – Google Calendar Integration

This project integrates with **Google Calendar** to fetch your next deadlines.  
To make it work, you need two files in your project folder:

- `credentials.json` – contains your OAuth client secrets from Google Cloud.
    
- `token.json` – generated automatically after your first login and stores your access/refresh tokens.
    

---

## 1. Enable Google Calendar API

1. Go to [Google Cloud Console](https://console.cloud.google.com/).
    
2. Create a new project (or select an existing one).
    
3. Navigate to **APIs & Services → Enabled APIs & services**.
    
4. Click **Enable APIs and Services**.
    
5. Search for **Google Calendar API** and enable it.
    
For more see [here](https://developers.google.com/workspace/calendar/api/quickstart/python)

---

## 2. Create OAuth credentials

1. In Google Cloud Console, go to **APIs & Services → Credentials**.
    
2. Click **Create Credentials → OAuth client ID**.
    
3. Set the **application type** to **Desktop app**.
    
4. Download the generated file.
    
5. Rename it to `credentials.json` and place it in the root of your project (or alongside your Python file).
    

⚠️ Never commit `credentials.json` to GitHub — it contains sensitive keys.

---

## 3. Configure OAuth consent screen

1. In Google Cloud Console, go to **APIs & Services → OAuth consent screen**.
    
2. Choose **External**.
    
3. Fill in required fields (App name, User support email, etc.).
    
5. Under **Test users**, add the Gmail account you’ll use.
    
6. Save changes.
    

---

## 4. Generate `token.json`

1. Run Python and call `load_credentials` for the first time:
    ```
    from your_module import load_credentials 
    load_credentials("credentials.json", "token.json")
    ```
2. A browser window will open asking you to log in with Google and grant permission.
    
3. Once you approve, the app will automatically create a **`token.json`** file in your project directory.
    

From then on, the program will reuse `token.json` to refresh tokens automatically.

---

## 5. Setting your calendar ID

By default, the code uses a specific calendar ID inside `get_upcoming_events`. You can change this to your own calendar:

1. Open [Google Calendar](https://calendar.google.com/).
    
2. In the left sidebar, hover over the calendar you want → click **⋮ → Settings and sharing**.
    
3. Scroll down to **Integrate calendar**.
    
4. Copy the **Calendar ID**:
    
    - For your main calendar: usually your Gmail address (e.g., `you@gmail.com`).
        
    - For custom calendars: looks like `abc123@group.calendar.google.com`.
        
5. In your code, pass it explicitly:
    ```
    events = get_upcoming_events(creds, calendar_id="you@gmail.com")
   ```
    
    or replace the default value in the function definition.
    

---

## 6. Verify your setup

With both files in place and your calendar ID set, run:
```
from your_module import next_deadline_message  
msg = next_deadline_message(within_days=30) 
print(msg["message"])
```

Example output:
```
PS: Next deadline: **Submit Literature Review** on **01.03.2025** (in 5 days)
```

---

## 7. Notes

- If you ever need to **switch accounts** or **reset authentication**, delete `token.json` and run `load_credentials` again.
    
- `credentials.json` comes from Google Cloud, `token.json` is created automatically on first login.
    
- To use multiple calendars, call `get_upcoming_events` with different `calendar_id` values.




