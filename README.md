# Slack MeetBot

A Python-based Slackbot that helps drive and manage meetings in Slack channels. It tracks participation, records minutes, manages action items, and provides detailed meeting statistics.

Note: You miss [meetbot](https://wiki.debian.org/MeetBot) from IRC? Well here is the next generation for Slack.

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

## Commands

The bot supports both slash commands and message-based commands with the `!` prefix. You can use either format:

### Meeting Management
- Start a meeting: `!meeting start`
- End a meeting: `!meeting end`

### Role Management
- Change the chair: `!chair @user`
- Add a co-chair: `!cochair @user`

### Action Items and Stats
- Create an action item: `!action @user task`
- View participation stats: `!stats`
- Export meeting minutes: `!export`

### Karma System
- View karma standings: `!karma`
- Give karma points: `!karma @user` or `@user++` (alternative syntax)

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

1. Using the message command:
   ```
   !karma @user
   ```

2. Using the ++ syntax:
   ```
   @user++
   ```

Rules:
- Users cannot give karma points to themselves
- Each karma action gives one point
- Karma points are tracked globally across all channels
- Karma standings show all users sorted by points

## Contributing

Feel free to submit issues and enhancement requests!

## License & Authors

If you would like to see the detailed LICENSE click [here](./LICENSE).

- Author: JJ Asghar <awesome@ibm.com>

```text
Copyright:: 2025- IBM, Inc

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
```

PS: Yes I "vibecoded" this with Cursor. It did suprisingly well.
