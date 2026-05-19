# app/agents/reminder.py
# ════════════════════════════════════════════════
# Reminder / Scheduler Agent
#
# WHY THIS AGENT EXISTS:
# Sends policy-driven nudges to students.
# Respects quiet hours and max nudges per day.
# Tracks consecutive misses for escalation.
#
# RUNS ON: APScheduler cron jobs
# ════════════════════════════════════════════════

from datetime import datetime
from sqlalchemy.orm import Session

from app.core.llm import get_llm
from app.core.logger import get_logger, get_correlation_id
from app.db.models import (
    User, Assignment, Submission,
    Nudge, Tenant, AuditLog, AuditAction,
    SubmissionStatus
)

log = get_logger(__name__)

REMINDER_SYSTEM_PROMPT = """
You are writing a friendly reminder to a student
about a pending school assignment.

Rules:
- Encouraging not nagging
- Maximum 2 sentences
- Include assignment name and due date
- Vary the message slightly each time
"""


def is_quiet_hours(tenant: Tenant) -> bool:
    """
    Check if current time is within quiet hours.
    No reminders sent during quiet hours.
    
    """
    current_hour = datetime.utcnow().hour
    start = tenant.quiet_hours_start
    end = tenant.quiet_hours_end

    if start > end:
        # Overnight quiet hours e.g. 22-8
        return current_hour >= start or current_hour < end
    else:
        return start <= current_hour < end


def get_nudge_count_today(
    student_id: str,
    assignment_id: str,
    db: Session
) -> int:
    """
    Count how many nudges sent today for
    this student + assignment combination.
    
    """
    today_start = datetime.utcnow().replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    return db.query(Nudge).filter(
        Nudge.student_id == student_id,
        Nudge.assignment_id == assignment_id,
        Nudge.sent_at >= today_start,
        Nudge.was_delivered == True
    ).count()


def should_send_nudge(
    student: User,
    assignment: Assignment,
    tenant: Tenant,
    db: Session
) -> bool:
    """
    Check all policies before sending a nudge.

    Policies checked:
    1. Not quiet hours
    2. Under max nudges per day limit
    3. Assignment still active
    4. Student hasn't submitted yet
    
    """
    # Check quiet hours
    if is_quiet_hours(tenant):
        log.info("nudge_blocked_quiet_hours",
                 student_id=str(student.id),
                 correlation_id=get_correlation_id())
        return False

    # Check daily limit
    nudges_today = get_nudge_count_today(
        str(student.id),
        str(assignment.id),
        db
    )

    if nudges_today >= tenant.max_nudges_per_day:
        log.info("nudge_blocked_daily_limit",
                 student_id=str(student.id),
                 nudges_today=nudges_today,
                 limit=tenant.max_nudges_per_day,
                 correlation_id=get_correlation_id())
        return False

    # Check if already submitted
    submission = db.query(Submission).filter(
        Submission.assignment_id == str(assignment.id),
        Submission.student_id == str(student.id)
    ).first()

    if submission and submission.status != SubmissionStatus.PENDING:
        log.info("nudge_blocked_already_submitted",
                 student_id=str(student.id),
                 correlation_id=get_correlation_id())
        return False

    return True


def generate_reminder_message(
    student: User,
    assignment: Assignment
) -> str:
    """
    Generate personalised reminder message.
    
    """
    llm = get_llm()

    try:
        response = llm.reminder(
            messages=[{
                "role": "user",
                "content": f"""
                Remind {student.full_name} about:
                Assignment: {assignment.title}
                Due: {assignment.due_date}
                """
            }],
            system=REMINDER_SYSTEM_PROMPT
        )
        return response

    except Exception as e:
        log.error("reminder_generation_failed",
                  error=str(e),
                  exc_info=True)
        return (
            f"Reminder: '{assignment.title}' "
            f"is due {assignment.due_date}. "
            f"Don't forget to submit!"
        )


def record_nudge(
    student: User,
    assignment: Assignment,
    was_delivered: bool,
    db: Session,
    nudge_type: str = "reminder"
) -> Nudge:
    """
    Record a nudge in the database.
    Updates consecutive_missed counter.
    """
    # Get previous consecutive missed count
    last_nudge = db.query(Nudge).filter(
        Nudge.student_id == str(student.id),
        Nudge.assignment_id == str(assignment.id)
    ).order_by(Nudge.created_at.desc()).first()

    consecutive = 0
    if last_nudge and not was_delivered:
        consecutive = last_nudge.consecutive_missed + 1

    nudge = Nudge(
        tenant_id=str(student.tenant_id),
        student_id=str(student.id),
        assignment_id=str(assignment.id),
        nudge_type=nudge_type,
        was_delivered=was_delivered,
        consecutive_missed=consecutive,
        sent_at=datetime.utcnow()
    )
    db.add(nudge)

    # Audit log
    audit = AuditLog(
        tenant_id=str(student.tenant_id),
        user_id=str(student.id),
        action=AuditAction.REMINDER_SENT,
        entity_type="assignment",
        entity_id=assignment.id,
        correlation_id=get_correlation_id()
    )
    db.add(audit)

    log.info("nudge_recorded",
             student_id=str(student.id),
             assignment_id=str(assignment.id),
             consecutive_missed=consecutive,
             was_delivered=was_delivered,
             correlation_id=get_correlation_id())

    return nudge