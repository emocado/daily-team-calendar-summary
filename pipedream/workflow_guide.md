# Pipedream Setup Guide: Daily Team Calendar Summary

This guide walks you through creating your automated, zero-cost, 100% cloud-hosted daily team calendar summary on Pipedream. Once deployed, it runs automatically every day at 9:00 AM SGT without requiring your laptop to be on.

---

## Prerequisites
- [Pipedream](https://pipedream.com/) account (Free plan).
- Green API credentials (already configured in the script):
  - `idInstance`: `710522727682`
  - `apiTokenInstance`: `1bbfcf04c5d542a2afcae69adaa47d7338282986e1b342c6a9`
- Google Account with access to the **SW Leave & Events** Google Calendar:
  - Calendar ID: `1416ccaf3075caf17169d81fa4f6e65a10634383b9301c50ee1ca4781659ccfb@group.calendar.google.com`

---

## Step 1: Create a New Workflow in Pipedream

1. Log in to [Pipedream](https://pipedream.com/).
2. Click **New +** > **Workflow**.
3. Name your workflow: `Daily Team Calendar Summary`.

---

## Step 2: Configure the Trigger (Daily Schedule)

1. Select **Schedule** as the trigger.
2. Select **Custom expression (cron)**:
   - **Cron Expression:** `0 1 * * *`
   - *(Note: `0 1 * * *` in UTC is 09:00 AM Asia/Singapore time).*
3. Alternatively, you can choose **Every Day** and set the time to `09:00` with timezone `Asia/Singapore`.
4. Click **Save and continue**.

---

## Step 3: Add the Google Calendar Step

1. Click the **+** button to add the next step.
2. Search for **Google Calendar** and select it.
3. Choose the action: **Find Events** (or **List Events**).
4. Connect your Google Account via the 1-click Google OAuth button.
5. In the configuration:
   - **Calendar:** Select `SW Leave & Events` (or choose "Enter a custom value" and paste: `1416ccaf3075caf17169d81fa4f6e65a10634383b9301c50ee1ca4781659ccfb@group.calendar.google.com`).
   - **Time Min:** `{{ steps.trigger.context.ts }}` (or leave blank to search from current time).
   - **Single Events:** `true` (expands recurring events).
   - **Order By:** `startTime`.
6. Rename this step to **`get_events`** (important, as the Python script looks for `steps.get_events`).
7. Click **Test** to fetch events and verify the connection.

---

## Step 4: Add the Python Formatting & Green API Send Step

1. Click the **+** button to add another step.
2. Select **Python** > **Run Python code**.
3. Replace all default code in the editor with the complete contents of [`pipedream/format_and_send.py`](format_and_send.py).
4. Review the target group at the top of the script:
   - To send to the **Team Group ("CFMS / SW Team")**:
     ```python
     TARGET_GROUP_JID = "120363023046007972@g.us"
     ```
   - To test with the **Personal Test Group ("Me, Myself and I")**:
     ```python
     TARGET_GROUP_JID = "120363427869267873@g.us"
     ```
5. Click **Test** to execute a test run.
   - You should see the formatted summary in the test logs and immediately receive the summary message in your WhatsApp group!

---

## Step 5: (Optional) Connect a Data Store for Idempotency

To prevent accidental duplicate sends if the workflow is re-triggered manually on the same day:
1. In the Python step configuration, expand **Optional fields** / **Inputs**.
2. Add a **Data Store**.
3. Select or create a new Data Store named `calendar_summary_store`.
4. The script will automatically store a hash of sent summaries and skip sending if it has already been sent on that day.

---

## Step 6: Deploy

Click **Deploy** in the top-right corner of the Pipedream editor.

Your automation is now fully live in the cloud. Every morning at 09:00 AM SGT, Pipedream will fetch the calendar, format the message, and deliver it via Green API to WhatsApp without needing your laptop to be on.
