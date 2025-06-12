# Slack MeetBot

A Python-based Slackbot that helps drive and manage meetings in Slack channels. It tracks participation, records minutes, manages action items, and provides detailed meeting statistics.

## Features

- 📝 Meeting Management
  - Start/end meetings
  - Track meeting participants
  - Record all messages
  - Export meeting minutes as HTML

- 👥 Role Management
  - Designated meeting chair
  - Support for co-chairs
  - Role-based permissions

- ✅ Action Items
  - Create and assign tasks
  - Track action items per meeting
  - Include in meeting minutes

- 📊 Statistics
  - Track participation metrics
  - Message counts
  - Word counts
  - Speaking time estimates

- ⭐ Karma System
  - Give karma points to helpful teammates
  - Track karma points per user
  - View karma standings
  - Support for both slash commands and ++ syntax

## Setup

1. **Create a Slack App**
   - Go to https://api.slack.com/apps
   - Click "Create New App"
   - Choose "From scratch"
   - Select your workspace

2. **Configure Bot Token Scopes**
   Add the following scopes under "OAuth & Permissions":
   - `channels:history`
   - `channels:read`
   - `groups:read`
   - `chat:write`
   - `users:read`
   - `reactions:read`
   - `reactions:write`
   - `files:write`

3. **Enable Socket Mode**
   - Go to "Socket Mode" in your app settings
   - Enable Socket Mode
   - Generate and save your app-level token

3a. **Set up Event Subscriptions**
   - Go to "Event Subscriptions"
   - Enable events
   - Subscribe to the following bot events:
    `message.channels`
    `message.groups`
    `app_mention`

4. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

5. **Configure Environment**
   Create a `.env` file with:
   ```
   SLACK_BOT_TOKEN=xoxb-your-bot-token
   SLACK_APP_TOKEN=xapp-your-app-token
   DEBUG=false  # Set to true for detailed logging
   ```

6. **Run the Bot**
   ```bash
   python app.py
   ```

## Debugging

The bot includes a comprehensive logging system that can be enabled by setting `DEBUG=true` in your `.env` file. When debug mode is enabled, you'll see detailed information about:

- Application startup and initialization
- Command reception and processing
- Database operations
- Error details
- Message handling
- User interactions

Debug logs include timestamps and log levels, making it easier to track down issues. Example debug output:

```
2024-01-20 10:30:45 - meetbot - INFO - Debug mode is enabled - you'll see detailed logging
2024-01-20 10:30:45 - meetbot - INFO - Slack app initialized successfully
2024-01-20 10:30:45 - meetbot - INFO - Database initialized successfully
2024-01-20 10:30:45 - meetbot - INFO - Jinja2 environment initialized successfully
2024-01-20 10:30:45 - meetbot - INFO - Starting Slack MeetBot...
2024-01-20 10:30:45 - meetbot - INFO - Bot is ready! Listening for events...
2024-01-20 10:31:00 - meetbot - DEBUG - Received /meeting command: {...}
```

To enable debug mode:
1. Add `DEBUG=true` to your `.env` file
2. Restart the bot
3. Watch the console for detailed logging information

To disable debug mode:
1. Set `DEBUG=false` in your `.env` file (or remove the line)
2. Restart the bot

## Commands

The bot supports both slash commands and message-based commands with the `!` prefix. You can use either format:

### Meeting Management
- Start a meeting:
  - `/meeting start` or `!meeting start`
- End a meeting:
  - `/meeting end` or `!meeting end`

### Role Management
- Change the chair:
  - `/chair @user` or `!chair @user`
- Add a co-chair:
  - `/cochair @user` or `!cochair @user`

### Action Items and Stats
- Create an action item:
  - `/action @user task` or `!action @user task`
- View participation stats:
  - `/stats` or `!stats`
- Export meeting minutes:
  - `/export` or `!export`

### Karma System
- View karma standings:
  - `/karma` or `!karma`
- Give karma points:
  - `/karma @user` or `!karma @user`
  - `@user++` (alternative syntax)

## Meeting Minutes Export

The bot automatically exports meeting minutes as HTML files to the `exports` directory. The export includes:
- Meeting metadata (time, date, channel)
- Participants and roles
- Complete message transcript
- Action items
- Participation statistics

## Database

The bot uses SQLite for data storage. The database (`meetbot.db`) will be created automatically on first run and includes tables for:
- Meetings
- Messages
- Action Items
- Co-chairs
- Speaker Statistics
- User Karma

## Karma System

The karma system allows team members to recognize and appreciate each other's contributions. There are three ways to give karma points:

1. Using the slash command:
   ```
   /karma @user
   ```

2. Using the message command:
   ```
   !karma @user
   ```

3. Using the ++ syntax:
   ```
   @user++
   ```

To view karma standings, use either:
```
/karma
```
or
```
!karma
```

Rules:
- Users cannot give karma points to themselves
- Each karma action gives one point
- Karma points are tracked globally across all channels
- Karma standings show all users sorted by points

## Contributing

Feel free to submit issues and enhancement requests! 