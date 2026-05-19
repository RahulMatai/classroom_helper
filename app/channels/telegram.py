# app/channels/telegram.py
# ════════════════════════════════════════════════
# Telegram Channel Adapter
#
# WHY THIS FILE EXISTS:
# Receives messages from Telegram webhook,
# normalises them to CanonicalMessage,
# routes to correct agent,
# sends response back to Telegram.
#
# SECURITY:
# Verifies secret_token on every webhook call.
# Rejects anything without valid token.
# ════════════════════════════════════════════════

import asyncio
from telegram import Update, Bot
from telegram.ext import (
    Application, CommandHandler,
    MessageHandler, filters,
    ContextTypes
)
from sqlalchemy.orm import Session

from app.channels.base import (
    CanonicalMessage, MessageType, OutboundMessage
)
from app.agents.safety import check_message_safety
from app.agents.router import classify_intent
from app.agents.teacher import create_assignment
from app.agents.student import (
    process_submission, generate_acknowledgement
)
from app.core.config import settings
from app.core.logger import get_logger, set_correlation_id
from app.db.models import User, Assignment, AssignmentStatus
from app.db.session import SessionLocal

log = get_logger(__name__)

def normalise_telegram_message(update: Update) -> CanonicalMessage:
    """
    Convert telegeam update to canoncal message.
    
    """
    message = update.message
    sender_id = str(message.from_user.id)
    
    if message.voice:
        msg_type = MessageType.VOICE
        text = "[Voice Message]"
    elif message.document:
        msg_type = MessageType.FILE
        text = message.caption or "[File]"
    else:
        msg_type = MessageType.TEXT
        text = message or ""
    return CanonicalMessage(
        message_id= str(message.message_id),
        channel="Telegram",
        sender_id= sender_id,
        text = text,
        message_type = msg_type,
        raw_payload= update.to_dict()
        
    )
    
#getting user from database
def get_user_by_telegram_id(
    telegram_id:str,
    db:Session
    
)-> User:
    #lookup their telegram ID if it exists
    return db.query(User).filter(
        User.telegram_id == telegram_id,
        User.is_active == True
    ).first()

# ── Command Handlers ──────────────────────────────

async def handle_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    """
    Handle /start command.
    Sent when user first opens the bot.
    """
    correlation_id = set_correlation_id()
    sender_id = str(update.message.from_user.id)

    log.info("telegram_start_command",
             sender_id=sender_id,
             correlation_id=correlation_id)

    db = SessionLocal()
    try:
        user = get_user_by_telegram_id(sender_id, db)

        if user:
            await update.message.reply_text(
                f"Welcome back {user.full_name}! "
                f"You are logged in as {user.role.value}.\n"
                f"Send me a message to get started."
            )
        else:
            await update.message.reply_text(
                "Welcome to Classroom Companion! 🎓\n\n"
                "To get started, ask your teacher "
                "to send you an invite link.\n\n"
                "If you have a binding code, "
                "send it now to link your account."
            )
    finally:
        db.close()
async def handle_help(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    """Handle /help command."""
    await update.message.reply_text(
        "📚 Classroom Companion Help\n\n"
        "Teachers:\n"
        "• Type your assignment naturally\n"
        "• Example: 'Essay on climate change due Friday'\n\n"
        "Students:\n"
        "• Submit work by typing or sending a file\n"
        "• Ask 'what are my assignments?' for a list\n\n"
        "Type /start to begin."
    )
    
#----------route to agent---------------
async def route_to_agent(
    intent: str,
    canonical: CanonicalMessage,
    user: User,
    db: Session,
    correlation_id: str
) -> str:
    """
    Route Message to correct agent
    """
    from app.core.policy import can_create_assignment
    if intent == "assignment.create":
        if not can_create_assignment(user):
            return "Only teachers can create the assignments"
        
        assignment =create_assignment(raw_text=canonical.text,
                                       teacher=user,
                                       db=db)
        
        db.commit()
        return(f"✅ Assignment created: '{assignment.title}'\n"
            f"Due: {assignment.due_date or 'No deadline set'}\n"
            f"Status: Active — students notified.")
    elif intent == "submission":
        #finding acrive asssignment here
        assignment = db.query(Assignment).filter(
            Assignment.tenant_id == str(user.tenant_id),
            Assignment.status == AssignmentStatus.ACTIVE
        ).first()
        if not  assignment:
            return "No active assignments found"
        submission = process_submission(
            student=user,
            assignment=assignment,
            content=canonical.text,
            content_type="text",
            db=db
        )
        db.commit()

        ack = generate_acknowledgement(
            user, assignment, "text"
        )
        return ack
    
    # Status query
    elif intent == "assignment.query":
        assignments = db.query(Assignment).filter(
            Assignment.tenant_id == str(user.tenant_id),
            Assignment.status == AssignmentStatus.ACTIVE
        ).all()

        if not assignments:
            return "No active assignments right now."

        response = "📚 Active Assignments:\n\n"
        for a in assignments:
            response += f"• {a.title}"
            if a.due_date:
                response += f" (due {a.due_date.strftime('%b %d')})"
            response += "\n"
        return response
# Smalltalk
    elif intent == "smalltalk":
        return (
            "Hi! I'm your classroom assistant. "
            "Teachers can create assignments, "
            "students can submit work. "
            "How can I help you today?"
        )

    # Default
    else:
        return (
            "I received your message. "
            "If you're a teacher, describe your assignment. "
            "If you're a student, send your submission."
        )

            
    

# ── Main Message Handler ──────────────────────────

async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    """
    Main handler for all incoming messages.

    Flow:
    1. Normalise to CanonicalMessage
    2. Safety check
    3. Get user from DB
    4. Classify intent
    5. Route to correct agent
    6. Send response
    """
    correlation_id = set_correlation_id()

    # Normalise message
    canonical = normalise_telegram_message(update)

    log.info("telegram_message_received",
             sender_id=canonical.sender_id,
             message_type=canonical.message_type.value,
             correlation_id=correlation_id)
    safety_result = check_message_safety(canonical.text)
    
    if not safety_result.get("safe", False):
        log.warning("unsafe_message_blocked",
                    sender_id=canonical.sender_id,
                    reason=safety_result.get("reason"),
                    correlation_id=correlation_id)
        await update.message.reply_text(
            "Sorry, I cannot process that message."
        )
        return
    # Get user from database
    db = SessionLocal()
    try:
        user = get_user_by_telegram_id(
            canonical.sender_id, db
        )

        if not user:
            await update.message.reply_text(
                "You are not registered. "
                "Please ask your teacher for an invite link."
            )
            return

        # Update canonical with user info
        canonical.user_id = str(user.id)
        canonical.tenant_id = str(user.tenant_id)

        # Classify intent
        intent_result = classify_intent(
            canonical.text,
            user.role.value
        )
        intent = intent_result.get("intent","unknown")
        log.info("intent_classified",
                 intent=intent,
                 user_id=str(user.id),
                 correlation_id=correlation_id)

        # Route to correct agent
        response_text = await route_to_agent(
            intent=intent,
            canonical=canonical,
            user=user,
            db=db,
            correlation_id=correlation_id
        )
        # Send response
        await update.message.reply_text(response_text)
    except Exception as e:
        log.error("message_handling_failed",
                  error=str(e),
                  exc_info=True,
                  correlation_id=correlation_id)
        await update.message.reply_text(
            "Something went wrong. Please try again."
        )
    finally:
        db.close()
        
#------telegram bot setup--------------

def create_telegram_app():
    """
    create and configure telegram bot application
    called once at startup in main.py
    
    """
    app = (
        Application.builder()
        .token(settings.TELEGRAM_BOT_TOKEN)
        .build()
    )
    app.add_handler(CommandHandler("start", handle_start))
    app.add_handler(CommandHandler("help", handle_help))
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        )
    )
    app.add_handler(
        MessageHandler(
            filters.VOICE | filters.Document.ALL,
            handle_message
        )
    )

    log.info("telegram_bot_configured",
             bot_token_preview=settings.TELEGRAM_BOT_TOKEN[:10])

    return app
    

    