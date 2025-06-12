import os
import re
import json
import time
import logging
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from jinja2 import Environment, FileSystemLoader
from models import Base, Meeting, Message, ActionItem, CoChair, SpeakerStats, UserKarma, init_db

def pretty_print_dict(d):
    """Helper function to pretty print dictionary for logging"""
    return json.dumps(d, indent=2, sort_keys=True)

# Load environment variables
load_dotenv()

# Configure logging - Set to most verbose level
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('meetbot')
# Make sure all loggers are set to DEBUG
logging.getLogger('slack_bolt').setLevel(logging.DEBUG)
logging.getLogger('slack_sdk').setLevel(logging.DEBUG)

logger.info("Starting with DEBUG logging enabled")

# Initialize Slack app with all events permission
try:
    app = App(token=os.environ["SLACK_BOT_TOKEN"])
    logger.info("Slack app initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize Slack app: {e}")
    raise

# Initialize database
try:
    engine = create_engine('sqlite:///meetbot.db')
    Session = sessionmaker(bind=engine)
    init_db()
    logger.info("Database initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize database: {e}")
    raise

# Initialize Jinja2 environment
try:
    env = Environment(loader=FileSystemLoader('templates'))
    logger.info("Jinja2 environment initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize Jinja2 environment: {e}")
    raise

def get_user_name(client, user_id):
    try:
        logger.debug(f"Fetching user info for user_id: {user_id}")
        result = client.users_info(user=user_id)
        name = result["user"]["real_name"]
        logger.debug(f"Found user name: {name}")
        return name
    except Exception as e:
        logger.warning(f"Failed to get user name for {user_id}: {e}")
        return user_id

def get_channel_info(client, channel_id):
    """Get channel name and details for logging purposes."""
    try:
        result = client.conversations_info(channel=channel_id)
        channel_name = result["channel"]["name"]
        is_private = result["channel"]["is_private"]
        member_count = result["channel"]["num_members"]
        logger.debug(f"Channel info - ID: {channel_id}, Name: #{channel_name}, Private: {is_private}, Members: {member_count}")
        return channel_name, is_private, member_count
    except Exception as e:
        logger.warning(f"Failed to get channel info for {channel_id}: {e}")
        return None, None, None

def log_message_context(client, channel_id, user_id, message_text=None):
    """Log detailed context about a message or command."""
    try:
        # Get channel information
        channel_name, is_private, member_count = get_channel_info(client, channel_id)
        
        # Get user information
        user_name = get_user_name(client, user_id)
        
        context_log = [
            "Message Context:",
            f"  Channel: #{channel_name} ({channel_id})",
            f"  Channel Type: {'Private' if is_private else 'Public'}",
            f"  Channel Members: {member_count}",
            f"  User: {user_name} ({user_id})"
        ]
        
        if message_text and logger.isEnabledFor(logging.DEBUG):
            context_log.append(f"  Message: {message_text}")
            
        logger.debug("\n".join(context_log))
    except Exception as e:
        logger.warning(f"Failed to log message context: {e}")

# Helper functions for command handling
def handle_meeting_start(client, channel_id, user_id, session):
    logger.debug(f"Handling meeting start request - channel: {channel_id}, user: {user_id}")
    
    # Check if there's already an active meeting
    active_meeting = session.query(Meeting).filter_by(
        channel_id=channel_id,
        is_active=True
    ).first()
    
    if active_meeting:
        logger.debug(f"Active meeting already exists in channel {channel_id}")
        client.chat_postEphemeral(
            channel=channel_id,
            user=user_id,
            text="There's already an active meeting in this channel!"
        )
        return
    
    try:
        # Create new meeting
        meeting = Meeting(
            channel_id=channel_id,
            chair_id=user_id,
            start_time=datetime.utcnow()
        )
        session.add(meeting)
        session.commit()
        logger.info(f"New meeting created in channel {channel_id} with chair {user_id}")
        
        client.chat_postMessage(
            channel=channel_id,
            text=f"Meeting started! :timer_clock:\nChair: <@{user_id}>\nUse `/meeting end` or `!meeting end` to end the meeting."
        )
    except Exception as e:
        logger.error(f"Failed to start meeting: {e}")
        session.rollback()
        client.chat_postEphemeral(
            channel=channel_id,
            user=user_id,
            text="Failed to start meeting due to an internal error. Please try again."
        )

def handle_meeting_end(client, channel_id, user_id, session):
    meeting = session.query(Meeting).filter_by(
        channel_id=channel_id,
        is_active=True
    ).first()
    
    if not meeting:
        client.chat_postEphemeral(
            channel=channel_id,
            user=user_id,
            text="No active meeting found in this channel!"
        )
        return
    
    if meeting.chair_id != user_id:
        client.chat_postEphemeral(
            channel=channel_id,
            user=user_id,
            text="Only the meeting chair can end the meeting!"
        )
        return
    
    meeting.end_time = datetime.utcnow()
    meeting.is_active = False
    session.commit()
    
    client.chat_postMessage(
        channel=channel_id,
        text="Meeting ended! :checkered_flag:\nUse `/export` or `!export` to get the meeting minutes."
    )

def handle_chair_change(client, channel_id, user_id, target_user, session):
    meeting = session.query(Meeting).filter_by(
        channel_id=channel_id,
        is_active=True
    ).first()
    
    if not meeting:
        client.chat_postEphemeral(
            channel=channel_id,
            user=user_id,
            text="No active meeting found in this channel!"
        )
        return
    
    if meeting.chair_id != user_id:
        client.chat_postEphemeral(
            channel=channel_id,
            user=user_id,
            text="Only the current chair can change the chair!"
        )
        return
    
    if not target_user.startswith("<@") or not target_user.endswith(">"):
        client.chat_postEphemeral(
            channel=channel_id,
            user=user_id,
            text="Please mention a user to make them chair!"
        )
        return
    
    new_chair_id = target_user[2:-1]
    meeting.chair_id = new_chair_id
    session.commit()
    
    client.chat_postMessage(
        channel=channel_id,
        text=f"Meeting chair changed to <@{new_chair_id}>!"
    )

def handle_cochair_add(client, channel_id, user_id, target_user, session):
    meeting = session.query(Meeting).filter_by(
        channel_id=channel_id,
        is_active=True
    ).first()
    
    if not meeting:
        client.chat_postEphemeral(
            channel=channel_id,
            user=user_id,
            text="No active meeting found in this channel!"
        )
        return
    
    if meeting.chair_id != user_id:
        client.chat_postEphemeral(
            channel=channel_id,
            user=user_id,
            text="Only the chair can add co-chairs!"
        )
        return
    
    if not target_user.startswith("<@") or not target_user.endswith(">"):
        client.chat_postEphemeral(
            channel=channel_id,
            user=user_id,
            text="Please mention a user to make them co-chair!"
        )
        return
    
    new_cochair_id = target_user[2:-1]
    cochair = CoChair(meeting_id=meeting.id, user_id=new_cochair_id)
    session.add(cochair)
    session.commit()
    
    client.chat_postMessage(
        channel=channel_id,
        text=f"Added <@{new_cochair_id}> as co-chair!"
    )

def handle_action_item(client, channel_id, user_id, text, session):
    meeting = session.query(Meeting).filter_by(
        channel_id=channel_id,
        is_active=True
    ).first()
    
    if not meeting:
        client.chat_postEphemeral(
            channel=channel_id,
            user=user_id,
            text="No active meeting found in this channel!"
        )
        return
    
    # Split the text into parts and validate format
    parts = text.strip().split(None, 1)  # Split into max 2 parts
    if len(parts) != 2:
        client.chat_postEphemeral(
            channel=channel_id,
            user=user_id,
            text="Please use format: !action user action"
        )
        return
    
    # Extract user and task
    assigned_to = parts[0]
    task = parts[1].strip()
    
    # Remove @ if present
    if assigned_to.startswith("@"):
        assigned_to = assigned_to[1:]
    
    # Remove Slack mention format if present
    if assigned_to.startswith("<@") and assigned_to.endswith(">"):
        try:
            # Try to get the user's real name
            user_info = client.users_info(user=assigned_to[2:-1])
            assigned_to = user_info["user"]["real_name"]
        except:
            # If we can't get the real name, just use the ID
            assigned_to = assigned_to[2:-1]
    
    if not task:
        client.chat_postEphemeral(
            channel=channel_id,
            user=user_id,
            text="Please provide an action description after the user"
        )
        return
    
    # Create the action item
    action_item = ActionItem(
        meeting_id=meeting.id,
        assigned_to=assigned_to,  # Store the name directly
        task=task
    )
    session.add(action_item)
    session.commit()
    
    # Send confirmation message
    client.chat_postMessage(
        channel=channel_id,
        text=f"✅ Action item assigned to {assigned_to}: {task}"
    )

def generate_meeting_export(meeting, messages, actions, client):
    """Generate HTML export for a meeting with Bootstrap styling"""
    html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Meeting Export</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { padding: 20px; background-color: #f8f9fa; }
        .meeting-header { background-color: #fff; border-radius: 10px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .meeting-title { color: #2c3e50; margin-bottom: 20px; }
        .meeting-info { color: #6c757d; }
        .section { background-color: #fff; border-radius: 10px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .section-title { color: #2c3e50; margin-bottom: 15px; border-bottom: 2px solid #e9ecef; padding-bottom: 10px; }
        .message-list { list-style: none; padding: 0; }
        .message-item { padding: 10px; border-bottom: 1px solid #e9ecef; }
        .message-item:last-child { border-bottom: none; }
        .message-user { font-weight: bold; color: #2c3e50; }
        .message-content { color: #495057; }
        .action-list { list-style: none; padding: 0; }
        .action-item { padding: 10px; border-bottom: 1px solid #e9ecef; }
        .action-item:last-child { border-bottom: none; }
        .action-user { font-weight: bold; color: #2c3e50; }
        .action-task { color: #495057; }
        .action-completed { color: #28a745; font-style: italic; }
        .timestamp { color: #6c757d; font-size: 0.9em; }
    </style>
</head>
<body>
    <div class="container">
        <div class="meeting-header">
            <h1 class="meeting-title">Meeting Export</h1>
            <div class="meeting-info">"""
    
    # Meeting info
    try:
        channel_info = client.conversations_info(channel=meeting.channel_id)
        channel_name = channel_info["channel"]["name"]
        html += f'<p><strong>Channel:</strong> <span class="badge bg-primary">#{channel_name}</span></p>'
    except:
        html += f'<p><strong>Channel ID:</strong> <span class="badge bg-secondary">{meeting.channel_id}</span></p>'
    
    # Format timestamps nicely
    start_time = meeting.start_time.strftime("%B %d, %Y at %I:%M %p")
    html += f'<p><strong>Start Time:</strong> {start_time}</p>'
    if meeting.end_time:
        end_time = meeting.end_time.strftime("%B %d, %Y at %I:%M %p")
        html += f'<p><strong>End Time:</strong> {end_time}</p>'
        duration = meeting.end_time - meeting.start_time
        hours, remainder = divmod(duration.total_seconds(), 3600)
        minutes, seconds = divmod(remainder, 60)
        html += f'<p><strong>Duration:</strong> {int(hours)}h {int(minutes)}m {int(seconds)}s</p>'
    
    html += """</div>
        </div>
        
        <div class="section">
            <h2 class="section-title">Messages</h2>
            <ul class="message-list">"""
    
    # Messages
    for msg in messages:
        try:
            user_info = client.users_info(user=msg.user_id)
            user_name = user_info["user"]["real_name"]
            # Handle timestamp conversion properly
            if isinstance(msg.timestamp, str):
                timestamp = datetime.fromtimestamp(float(msg.timestamp)).strftime("%I:%M %p")
            else:
                timestamp = msg.timestamp.strftime("%I:%M %p")
            html += f"""
                <li class="message-item">
                    <div class="d-flex justify-content-between align-items-start">
                        <div>
                            <span class="message-user">{user_name}</span>
                            <span class="message-content">{msg.content}</span>
                        </div>
                        <span class="timestamp">{timestamp}</span>
                    </div>
                </li>"""
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            # Handle timestamp conversion properly
            if isinstance(msg.timestamp, str):
                timestamp = datetime.fromtimestamp(float(msg.timestamp)).strftime("%I:%M %p")
            else:
                timestamp = msg.timestamp.strftime("%I:%M %p")
            html += f"""
                <li class="message-item">
                    <div class="d-flex justify-content-between align-items-start">
                        <div>
                            <span class="message-user">User {msg.user_id}</span>
                            <span class="message-content">{msg.content}</span>
                        </div>
                        <span class="timestamp">{timestamp}</span>
                    </div>
                </li>"""
    
    html += """</ul>
        </div>"""
    
    # Action items
    if actions:
        html += """
        <div class="section">
            <h2 class="section-title">Action Items</h2>
            <ul class="action-list">"""
        
        for action in actions:
            try:
                user_info = client.users_info(user=action.assigned_to)
                user_name = user_info["user"]["real_name"]
                status = " (Completed)" if action.completed else ""
                status_class = "action-completed" if action.completed else ""
                html += f"""
                <li class="action-item">
                    <div class="d-flex justify-content-between align-items-start">
                        <div>
                            <span class="action-user">{user_name}</span>
                            <span class="action-task {status_class}">{action.task}{status}</span>
                        </div>
                    </div>
                </li>"""
            except Exception as e:
                logger.error(f"Error processing action item: {e}")
                status = " (Completed)" if action.completed else ""
                status_class = "action-completed" if action.completed else ""
                html += f"""
                <li class="action-item">
                    <div class="d-flex justify-content-between align-items-start">
                        <div>
                            <span class="action-user">User {action.assigned_to}</span>
                            <span class="action-task {status_class}">{action.task}{status}</span>
                        </div>
                    </div>
                </li>"""
        
        html += """</ul>
        </div>"""
    
    html += """
    </div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>"""
    
    return html

# Slash command handlers
@app.command("/meeting")
def handle_meeting_command(ack, command, respond, client, logger):
    """Handle meeting-related commands"""
    ack()
    logger.info(f"Processing meeting command: {command['text']}")
    
    try:
        args = command["text"].split()
        if not args:
            respond("Please provide a subcommand (start, end, status)")
            return
            
        subcommand = args[0].lower()
        channel_id = command["channel_id"]
        user_id = command["user_id"]
        
        session = Session()
        
        if subcommand == "start":
            # Check if there's already an active meeting
            active_meeting = session.query(Meeting).filter_by(
                channel_id=channel_id,
                is_active=True
            ).first()
            
            if active_meeting:
                respond("❌ There's already an active meeting in this channel!")
                return
                
            # Create new meeting
            meeting = Meeting(
                channel_id=channel_id,
                chair_id=user_id,
                start_time=datetime.now()
            )
            session.add(meeting)
            session.commit()
            
            # Get channel and user info for the announcement
            try:
                channel_info = client.conversations_info(channel=channel_id)
                channel_name = channel_info["channel"]["name"]
                user_info = client.users_info(user=user_id)
                chair_name = user_info["user"]["real_name"]
                
                # Send announcement message
                announcement = (
                    "🎯 *New Meeting Started!*\n\n"
                    f"• *Channel:* #{channel_name}\n"
                    f"• *Chair:* {chair_name}\n"
                    f"• *Start Time:* {meeting.start_time.strftime('%I:%M %p')}\n"
                    "\n"
                    "📝 *Available Commands:*\n"
                    "• `!meeting status` - Check meeting status\n"
                    "• `!action @user task` - Assign action items\n"
                    "• `!meeting end` - End the meeting\n"
                    "\n"
                    "✨ Meeting has started! All messages will now be recorded."
                )
                
                client.chat_postMessage(
                    channel=channel_id,
                    text=announcement,
                    blocks=[
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": announcement
                            }
                        }
                    ]
                )
                
                respond("✅ Meeting started successfully!")
                logger.info(f"Started new meeting in channel {channel_id}")
                
            except Exception as e:
                logger.error(f"Error getting channel/user info for announcement: {e}")
                respond("✅ Meeting started successfully! (Could not send detailed announcement)")
            
        elif subcommand == "end":
            handle_meeting_end(client, channel_id, user_id, session)
        elif subcommand == "status":
            # Get current meeting status
            meeting = session.query(Meeting).filter_by(
                channel_id=channel_id,
                is_active=True
            ).first()
            
            if not meeting:
                client.chat_postMessage(
                    channel=channel_id,
                    text="No active meeting in this channel."
                )
                return
                
            # Get meeting stats
            duration = datetime.utcnow() - meeting.start_time
            duration_mins = int(duration.total_seconds() / 60)
            
            messages = session.query(Message).filter_by(meeting_id=meeting.id).count()
            participants = session.query(SpeakerStats).filter_by(meeting_id=meeting.id).count()
            action_items = session.query(ActionItem).filter_by(meeting_id=meeting.id).count()
            
            # Get chair name
            try:
                chair_info = client.users_info(user=meeting.chair_id)
                chair_name = chair_info["user"]["real_name"]
            except:
                chair_name = f"<@{meeting.chair_id}>"
            
            status = (
                "📊 *Meeting Status*\n\n"
                f"• *Duration:* {duration_mins} minutes\n"
                f"• *Chair:* {chair_name}\n"
                f"• *Messages:* {messages}\n"
                f"• *Participants:* {participants}\n"
                f"• *Action Items:* {action_items}\n"
            )
            
            client.chat_postMessage(
                channel=channel_id,
                text=status
            )
        else:
            logger.warning(f"Unknown meeting subcommand: {subcommand}")
            respond("Invalid command. Use 'start', 'end', or 'status'.")
    except Exception as e:
        logger.error(f"Error handling /meeting command: {e}")
        respond("An error occurred while processing your command.")

@app.command("!chair")
def handle_chair_command(ack, command, client, logger):
    """Handle chair assignment command"""
    ack()
    logger.info(f"Processing chair command: {command['text']}")
    
    try:
        args = command["text"].split()
        if not args:
            client.chat_postEphemeral(
                channel=command["channel_id"],
                user=command["user_id"],
                text="Please mention a user to assign as chair: !chair @user"
            )
            return
            
        # Extract user ID from mention
        user_id = args[0].strip("<>@")
        channel_id = command["channel_id"]
        
        session = Session()
        
        # Find active meeting
        meeting = session.query(Meeting).filter_by(
            channel_id=channel_id,
            is_active=True
        ).first()
        
        if not meeting:
            client.chat_postEphemeral(
                channel=channel_id,
                user=command["user_id"],
                text="❌ No active meeting in this channel!"
            )
            return
            
        # Update chair
        meeting.chair_id = user_id
        session.commit()
        
        # Get user info for announcement
        try:
            user_info = client.users_info(user=user_id)
            chair_name = user_info["user"]["real_name"]
            
            client.chat_postMessage(
                channel=channel_id,
                text=f"👑 {chair_name} has been assigned as the meeting chair!"
            )
            
        except Exception as e:
            logger.error(f"Error getting user info: {e}")
            client.chat_postMessage(
                channel=channel_id,
                text=f"✅ New chair assigned (User ID: {user_id})"
            )
            
    except Exception as e:
        logger.error(f"Error handling chair command: {e}")
        client.chat_postEphemeral(
            channel=command["channel_id"],
            user=command["user_id"],
            text="❌ Error assigning chair. Please try again."
        )

@app.command("!cochair")
def handle_cochair_command(ack, command, client, logger):
    """Handle co-chair assignment command"""
    ack()
    logger.info(f"Processing cochair command: {command['text']}")
    
    try:
        args = command["text"].split()
        if not args:
            client.chat_postEphemeral(
                channel=command["channel_id"],
                user=command["user_id"],
                text="Please mention a user to assign as co-chair: !cochair @user"
            )
            return
            
        # Extract user ID from mention
        user_id = args[0].strip("<>@")
        channel_id = command["channel_id"]
        
        session = Session()
        
        # Find active meeting
        meeting = session.query(Meeting).filter_by(
            channel_id=channel_id,
            is_active=True
        ).first()
        
        if not meeting:
            client.chat_postEphemeral(
                channel=channel_id,
                user=command["user_id"],
                text="❌ No active meeting in this channel!"
            )
            return
            
        # Update co-chair
        meeting.cochair_id = user_id
        session.commit()
        
        # Get user info for announcement
        try:
            user_info = client.users_info(user=user_id)
            cochair_name = user_info["user"]["real_name"]
            
            client.chat_postMessage(
                channel=channel_id,
                text=f"👑 {cochair_name} has been assigned as the meeting co-chair!"
            )
            
        except Exception as e:
            logger.error(f"Error getting user info: {e}")
            client.chat_postMessage(
                channel=channel_id,
                text=f"✅ New co-chair assigned (User ID: {user_id})"
            )
            
    except Exception as e:
        logger.error(f"Error handling cochair command: {e}")
        client.chat_postEphemeral(
            channel=command["channel_id"],
            user=command["user_id"],
            text="❌ Error assigning co-chair. Please try again."
        )

@app.command("!karma")
def handle_karma_command(ack, command, client, logger):
    """Handle karma-related commands"""
    ack()
    logger.info(f"Processing karma command: {command['text']}")
    
    try:
        text = command["text"].strip()
        if not text:
            client.chat_postEphemeral(
                channel=command["channel_id"],
                user=command["user_id"],
                text="Please specify a karma action: !karma @user++ or !karma @user-- or !karma list"
            )
            return
            
        channel_id = command["channel_id"]
        session = Session()
        
        if text.lower() == "list":
            # Show karma leaderboard
            karma_list = session.query(UserKarma).order_by(UserKarma.points.desc()).all()
            
            if not karma_list:
                client.chat_postMessage(
                    channel=channel_id,
                    text="No karma points recorded yet! 🌱"
                )
                return
                
            leaderboard = "🏆 *Karma Leaderboard*\n\n"
            for i, karma in enumerate(karma_list[:10], 1):
                try:
                    user_info = client.users_info(user=karma.user_id)
                    user_name = user_info["user"]["real_name"]
                    leaderboard += f"{i}. {user_name}: {karma.points} points\n"
                except:
                    leaderboard += f"{i}. <@{karma.user_id}>: {karma.points} points\n"
            
            client.chat_postMessage(
                channel=channel_id,
                text=leaderboard
            )
            return
            
        # Parse user and action from text
        match = re.match(r"<@([A-Z0-9]+)>\s*(\+\+|--)", text)
        if not match:
            client.chat_postEphemeral(
                channel=channel_id,
                user=command["user_id"],
                text="Invalid karma command format. Use: !karma @user++ or !karma @user--"
            )
            return
            
        target_user = match.group(1)
        action = match.group(2)
            
        # Don't allow self-karma
        if target_user == command["user_id"]:
            client.chat_postEphemeral(
                channel=channel_id,
                user=command["user_id"],
                text="Nice try! You can't modify your own karma 😉"
            )
            return
            
        # Get or create karma record
        karma = session.query(UserKarma).filter_by(user_id=target_user).first()
        if not karma:
            karma = UserKarma(user_id=target_user, points=0)
            session.add(karma)
            
        # Update karma
        if action == "++":
            karma.points += 1
            change = "increased"
        else:
            karma.points -= 1
            change = "decreased"
            
        session.commit()
        
        # Get user info for announcement
        try:
            user_info = client.users_info(user=target_user)
            target_name = user_info["user"]["real_name"]
            
            client.chat_postMessage(
                channel=channel_id,
                text=f"🎭 {target_name}'s karma has {change} to {karma.points} points!"
            )
            
        except Exception as e:
            logger.error(f"Error getting user info: {e}")
            client.chat_postMessage(
                channel=channel_id,
                text=f"✅ Karma {change} for <@{target_user}> to {karma.points} points!"
            )
            
    except Exception as e:
        logger.error(f"Error handling karma command: {e}")
        client.chat_postEphemeral(
            channel=command["channel_id"],
            user=command["user_id"],
            text="❌ Error processing karma command. Please try again."
        )

@app.message(re.compile(r"^!stats"))
def handle_stats_message(message, client, logger):
    """Handle !stats command"""
    handle_stats_command(lambda: None, {"channel_id": message["channel"], "user_id": message["user"]}, client, logger)

@app.command("!stats")
def handle_stats_command(ack, command, client, logger):
    """Handle meeting statistics command"""
    ack()
    logger.info(f"Processing stats command")
    
    try:
        channel_id = command["channel_id"]
        session = Session()
        
        # Find active meeting
        meeting = session.query(Meeting).filter_by(
            channel_id=channel_id,
            is_active=True
        ).first()
        
        if not meeting:
            client.chat_postEphemeral(
                channel=channel_id,
                user=command["user_id"],
                text="❌ No active meeting in this channel!"
            )
            return
            
        # Get speaker stats
        stats = session.query(SpeakerStats).filter_by(meeting_id=meeting.id).all()
        
        if not stats:
            client.chat_postMessage(
                channel=channel_id,
                text="No participation statistics available for this meeting yet."
            )
            return
            
        # Build stats message
        stats_msg = "📊 *Meeting Participation Statistics*\n\n"
        
        for stat in stats:
            try:
                user_info = client.users_info(user=stat.user_id)
                user_name = user_info["user"]["real_name"]
                
                stats_msg += f"*{user_name}*\n"
                stats_msg += f"• Messages: {stat.message_count}\n"
                stats_msg += f"• Words: {stat.total_words}\n"
                stats_msg += f"• Speaking time: {int(stat.speaking_time_seconds)}s\n\n"
                
            except Exception as e:
                logger.error(f"Error getting user info: {e}")
                stats_msg += f"*<@{stat.user_id}>*\n"
                stats_msg += f"• Messages: {stat.message_count}\n"
                stats_msg += f"• Words: {stat.total_words}\n"
                stats_msg += f"• Speaking time: {int(stat.speaking_time_seconds)}s\n\n"
        
        client.chat_postMessage(
            channel=channel_id,
            text=stats_msg
        )
        
    except Exception as e:
        logger.error(f"Error handling stats command: {e}")
        client.chat_postEphemeral(
            channel=command["channel_id"],
            user=command["user_id"],
            text="❌ Error getting meeting statistics. Please try again."
        )

@app.message(re.compile(r"^!export"))
def handle_export_message(message, client):
    """Handle !export command"""
    logger.info(f"Processing export command")
    
    try:
        channel_id = message["channel"]
        user_id = message["user"]
        session = Session()
        
        # Find most recent meeting in channel
        meeting = session.query(Meeting).filter_by(
            channel_id=channel_id
        ).order_by(Meeting.end_time.desc()).first()
        
        if not meeting:
            client.chat_postEphemeral(
                channel=channel_id,
                user=user_id,
                text="❌ No meeting found in this channel!"
            )
            return
            
        # Get meeting messages
        messages = session.query(Message).filter_by(meeting_id=meeting.id).order_by(Message.timestamp).all()
        
        # Get action items
        actions = session.query(ActionItem).filter_by(meeting_id=meeting.id).all()
        
        if not messages:
            client.chat_postEphemeral(
                channel=channel_id,
                user=user_id,
                text="❌ No messages found for this meeting!"
            )
            return
            
        # Generate HTML export
        export_time = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"meeting_export_{channel_id}_{export_time}.html"
        
        try:
            # Generate the HTML content
            html_content = generate_meeting_export(meeting, messages, actions, client)
            
            # Write to file
            with open(filename, "w") as f:
                f.write(html_content)
            
            # Upload to Slack
            client.files_upload_v2(
                channel=channel_id,
                file=filename,
                initial_comment="📑 Here's your meeting export!",
                title="Meeting Export"
            )
            
            # Clean up the file
            os.remove(filename)
            
        except Exception as e:
            if "missing_scope" in str(e) and "files:write" in str(e):
                # Special handling for missing files:write scope
                client.chat_postEphemeral(
                    channel=channel_id,
                    user=user_id,
                    text="❌ Export failed: The bot needs the 'files:write' permission. Please contact your workspace admin to add this permission to the MeetBot app."
                )
            else:
                # Other errors
                logger.error(f"Error handling export command: {e}")
                client.chat_postEphemeral(
                    channel=channel_id,
                    user=user_id,
                    text="❌ Error exporting meeting. Please try again."
                )
            
    except Exception as e:
        logger.error(f"Error handling export command: {e}")
        client.chat_postEphemeral(
            channel=channel_id,
            user=user_id,
            text="❌ Error exporting meeting. Please try again."
        )

# Message-based command handlers
@app.message(re.compile(r"^!meeting\s+(\w+)(?:\s+(.*))?"))
def handle_meeting_message(message, context, client):
    logger.debug(f"Received !meeting message: {message}")
    session = Session()
    
    try:
        subcommand = context.matches[0].strip().lower()
        channel_id = message["channel"]
        user_id = message["user"]
        
        logger.debug(f"Processing !meeting {subcommand} from user {user_id} in channel {channel_id}")
        
        if subcommand == "start":
            handle_meeting_start(client, channel_id, user_id, session)
        elif subcommand == "end":
            handle_meeting_end(client, channel_id, user_id, session)
        elif subcommand == "status":
            # Get current meeting status
            meeting = session.query(Meeting).filter_by(
                channel_id=channel_id,
                is_active=True
            ).first()
            
            if not meeting:
                client.chat_postMessage(
                    channel=channel_id,
                    text="❌ No active meeting in this channel. Use `!meeting start` to start a new meeting."
                )
                return
                
            # Get meeting stats
            duration = datetime.utcnow() - meeting.start_time
            duration_mins = int(duration.total_seconds() / 60)
            
            messages = session.query(Message).filter_by(meeting_id=meeting.id).count()
            participants = session.query(SpeakerStats).filter_by(meeting_id=meeting.id).count()
            action_items = session.query(ActionItem).filter_by(meeting_id=meeting.id).count()
            
            # Get chair name
            try:
                chair_info = client.users_info(user=meeting.chair_id)
                chair_name = chair_info["user"]["real_name"]
            except:
                chair_name = f"<@{meeting.chair_id}>"
                
            # Get co-chairs
            co_chairs = session.query(CoChair).filter_by(meeting_id=meeting.id).all()
            co_chair_names = []
            for co_chair in co_chairs:
                try:
                    co_chair_info = client.users_info(user=co_chair.user_id)
                    co_chair_names.append(co_chair_info["user"]["real_name"])
                except:
                    co_chair_names.append(f"<@{co_chair.user_id}>")
            
            status = (
                "📊 *Meeting Status*\n\n"
                f"• *Duration:* {duration_mins} minutes\n"
                f"• *Chair:* {chair_name}\n"
            )
            
            if co_chair_names:
                status += f"• *Co-chairs:* {', '.join(co_chair_names)}\n"
                
            status += (
                f"• *Messages:* {messages}\n"
                f"• *Participants:* {participants}\n"
                f"• *Action Items:* {action_items}\n\n"
                "Use `!meeting end` to end the meeting."
            )
            
            client.chat_postMessage(
                channel=channel_id,
                text=status
            )
        else:
            client.chat_postEphemeral(
                channel=channel_id,
                user=user_id,
                text="Invalid command. Use 'start', 'end', or 'status'."
            )
    except Exception as e:
        logger.error(f"Error handling message event: {e}")
        client.chat_postEphemeral(
            channel=channel_id,
            user=user_id,
            text="An error occurred while processing your command."
        )

@app.message(re.compile(r"^!chair\s+(<@[A-Z0-9]+>)"))
def handle_chair_message(message, context, client):
    session = Session()
    handle_chair_change(client, message["channel"], message["user"], context.matches[0], session)

@app.message(re.compile(r"^!cochair\s+(<@[A-Z0-9]+>)"))
def handle_cochair_message(message, context, client):
    session = Session()
    handle_cochair_add(client, message["channel"], message["user"], context.matches[0], session)

@app.message(re.compile(r"^!action\s+list$"))
def handle_action_list_message(message, client):
    """Handle !action list command"""
    session = Session()
    channel_id = message["channel"]
    
    # Find active meeting
    meeting = session.query(Meeting).filter_by(
        channel_id=channel_id,
        is_active=True
    ).first()
    
    if not meeting:
        client.chat_postEphemeral(
            channel=channel_id,
            user=message["user"],
            text="No active meeting found in this channel!"
        )
        return
    
    # Get action items for the meeting
    action_items = session.query(ActionItem).filter_by(
        meeting_id=meeting.id,
        completed=False
    ).order_by(ActionItem.created_at).all()
    
    if not action_items:
        client.chat_postMessage(
            channel=channel_id,
            text="No pending action items for this meeting! 🎉"
        )
        return
    
    # Build action items list
    items_list = "📋 *Current Action Items*\n\n"
    for i, item in enumerate(action_items, 1):
        items_list += f"{i}. *{item.assigned_to}*: {item.task}\n"
    
    client.chat_postMessage(
        channel=channel_id,
        text=items_list
    )

@app.message(re.compile(r"^!action\s+(?!list\b)(.+)"))
def handle_action_message(message, context, client):
    """Handle !action command for assigning action items"""
    session = Session()
    handle_action_item(client, message["channel"], message["user"], context.matches[0], session)

@app.message(re.compile(r"^!karma\s+<@([A-Z0-9]+)>(\+\+|--)"))
def handle_karma_message(message, context, client):
    """Handle !karma @user++ format"""
    user_id = context.matches[0]
    action = context.matches[1]
    handle_karma_command(lambda: None, {"channel_id": message["channel"], "user_id": message["user"], "text": f"<@{user_id}> {action}"}, client, logger)

@app.message(re.compile(r"^<@([A-Z0-9]+)>(\+\+|--)"))
def handle_direct_karma_message(message, context, client):
    """Handle @user++ format"""
    user_id = context.matches[0]
    action = context.matches[1]
    handle_karma_command(lambda: None, {"channel_id": message["channel"], "user_id": message["user"], "text": f"<@{user_id}> {action}"}, client, logger)

@app.message(re.compile(r"^!karma\s+list"))
def handle_karma_list_message(message, client):
    """Handle !karma list command"""
    session = Session()
    channel_id = message["channel"]
    
    # Show karma leaderboard
    karma_list = session.query(UserKarma).order_by(UserKarma.points.desc()).all()
    
    if not karma_list:
        client.chat_postMessage(
            channel=channel_id,
            text="No karma points recorded yet! 🌱"
        )
        return
        
    leaderboard = "🏆 *Karma Leaderboard*\n\n"
    for i, karma in enumerate(karma_list[:10], 1):
        try:
            user_info = client.users_info(user=karma.user_id)
            user_name = user_info["user"]["real_name"]
            leaderboard += f"{i}. {user_name}: {karma.points} points\n"
        except:
            leaderboard += f"{i}. <@{karma.user_id}>: {karma.points} points\n"
    
    client.chat_postMessage(
        channel=channel_id,
        text=leaderboard
    )

@app.event("message")
def handle_message(event, client, logger):
    """Handle incoming messages with enhanced logging."""
    logger.info(f"📨 Received message event: {pretty_print_dict(event)}")
    
    try:
        # Skip message subtypes (like bot messages)
        if "subtype" in event:
            logger.info(f"Skipping message with subtype: {event.get('subtype')}")
            return

        # Skip if no text in message
        if "text" not in event:
            logger.info("Skipping message with no text")
            return

        channel_id = event["channel"]
        user_id = event["user"]
        content = event["text"]
        
        # Get channel info for logging
        try:
            channel_info = client.conversations_info(channel=channel_id)
            channel_name = channel_info["channel"]["name"]
            logger.info(f"📝 Message received in #{channel_name} ({channel_id})")
            logger.info(f"Message content: {content}")
            logger.info(f"From user: {user_id}")
            
            # Process !help command
            if content.strip() == "!help":
                logger.info("Processing !help command")
                handle_help_message(client, channel_id, user_id, logger)
                return
            
            # Special logging for #general
            if channel_name == "general":
                logger.info("‼️ Message received in #general channel!")
                
        except Exception as e:
            logger.error(f"Could not get channel info for {channel_id}: {e}")
        
        session = Session()
        
        # Check for active meeting
        meeting = session.query(Meeting).filter_by(
            channel_id=channel_id,
            is_active=True
        ).first()
        
        if meeting:
            logger.info(f"✅ Active meeting found in channel - Recording message")
            # Record message
            message = Message(
                meeting_id=meeting.id,
                user_id=user_id,
                content=content
            )
            session.add(message)
            
            # Update speaker stats
            stats = session.query(SpeakerStats).filter_by(
                meeting_id=meeting.id,
                user_id=user_id
            ).first()
            
            if not stats:
                logger.info(f"Creating new speaker stats for user {user_id}")
                stats = SpeakerStats(
                    meeting_id=meeting.id,
                    user_id=user_id,
                    message_count=0,
                    total_words=0,
                    speaking_time_seconds=0.0
                )
                session.add(stats)
                session.flush()  # Ensure stats object is created in DB
            
            stats.message_count += 1
            stats.total_words += len(content.split())
            stats.speaking_time_seconds += len(content) * 0.1  # Rough estimate
            
            session.commit()
            logger.info("Message and stats recorded successfully")
        else:
            logger.info(f"ℹ️ No active meeting in channel - Message not recorded")
        
    except Exception as e:
        logger.error(f"Error handling message event: {e}", exc_info=True)
        if 'session' in locals():
            session.rollback()

@app.event("member_joined_channel")
def handle_member_joined(event, client):
    """Log when the bot joins a channel."""
    try:
        channel_id = event["channel"]
        user_id = event["user"]
        
        # If the bot joined
        if user_id == client.bot_user_id:
            channel_name, is_private, member_count = get_channel_info(client, channel_id)
            logger.info(f"Bot joined channel #{channel_name} ({channel_id})")
            logger.debug(f"Channel details - Private: {is_private}, Members: {member_count}")
    except Exception as e:
        logger.error(f"Error handling member_joined_channel event: {e}")

@app.event("app_mention")
def handle_mention(event, client):
    """Log when the bot is mentioned."""
    try:
        channel_id = event["channel"]
        user_id = event["user"]
        text = event["text"]
        
        logger.info(f"Bot was mentioned in channel {channel_id}")
        log_message_context(client, channel_id, user_id, text)
    except Exception as e:
        logger.error(f"Error handling app_mention event: {e}")

@app.message(re.compile(r"^!meeting\s+end"))
def handle_meeting_end_message(message, client):
    """Handle !meeting end command"""
    session = Session()
    handle_meeting_end(client, message["channel"], message["user"], session)
    client.chat_postMessage(
        channel=message["channel"],
        text="Meeting ended! :checkered_flag:\nUse `!export` to get the meeting minutes."
    )

@app.message(re.compile(r"^!help"))
def handle_help_message(client, channel_id, user_id, logger):
    """Handle the help command by displaying available commands."""
    help_text = (
        "🤖 *MeetBot Available Commands*\n\n"
        "*Meeting Management:*\n"
        "• `!meeting start` - Start a new meeting in the channel\n"
        "• `!meeting end` - End the current meeting\n"
        "• `!meeting status` - Show the current meeting status\n\n"
        
        "*Action Items:*\n"
        "• `!action user task` - Assign an action item to a user (with or without @)\n"
        "• `!action list` - List all action items for the current meeting\n"
        "• `!action done ID` - Mark an action item as completed\n\n"
        
        "*Roles and Permissions:*\n"
        "• `!chair @user` - Assign someone as the meeting chair\n"
        "• `!cochair @user` - Assign someone as meeting co-chair\n\n"
        
        "*Karma System:*\n"
        "• `!karma @user++` or `@user++` - Give karma to a user\n"
        "• `!karma @user--` or `@user--` - Remove karma from a user\n"
        "• `!karma list` - Show karma leaderboard\n\n"
        
        "*Other Commands:*\n"
        "• `!export` - Export the current meeting to HTML\n"
        "• `!stats` - Show meeting participation statistics\n"
        "• `!help` - Show this help message\n\n"
        
        "💡 *Tips:*\n"
        "• The bot automatically records all messages during an active meeting\n"
        "• Only the chair or co-chair can end meetings\n"
        "• Action items are saved and can be reviewed later\n"
        "• Meeting exports include all messages and action items"
    )
    
    try:
        client.chat_postMessage(
            channel=channel_id,
            text=help_text,
            blocks=[
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": help_text
                    }
                }
            ]
        )
        logger.info("Help message posted successfully")
    except Exception as e:
        logger.error(f"Error posting help message: {e}")
        client.chat_postEphemeral(
            channel=channel_id,
            user=user_id,
            text="❌ Error: Could not post help message. Please try again."
        )

if __name__ == "__main__":
    # Initialize the Socket Mode handler
    try:
        handler = SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])
        logger.info("Starting the bot in Socket Mode...")
        handler.start()
    except Exception as e:
        logger.error(f"Failed to start Socket Mode handler: {e}")
        raise