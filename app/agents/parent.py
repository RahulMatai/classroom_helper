# app/agents/parent.py
# ════════════════════════════════════════════════
# Parent Agent
#
# WHY THIS AGENT EXISTS:
# Handles all parent-facing communication.
# Deliberately narrow scope:
# - Weekly digest only
# - Escalation alerts only
# Never chatty — parents get minimal messages.
#
# RUNS ON: weekly cron + escalation threshold
# ════════════════════════════════════════════════

from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session

from app.core.llm import get_llm
from app.core.logger import get_logger, get_correlation_id
from app.core.events import publish_event, EventType
from app.db.models import (
    User, Submission, Assignment,
    AuditLog, AuditAction
)

log = get_logger(__name__)

DIGEST_SYSTEM_PROMPT = """
You are writing a weekly update for a parent about
their child's school assignments.

Rules:
- Plain simple language — no jargon
- Maximum 5 sentences
- Factual and positive in tone
- Mention what was completed and what is pending
- Never alarm unnecessarily
"""

ESCALATION_SYSTEM_PROMPT = """
You are writing an urgent message to a parent about
their child missing multiple assignment deadlines.

Rules:
- Clear and direct
- Not panic-inducing but serious
- Maximum 3 sentences
- Include the assignment name and how many
  reminders were missed
"""


def generate_weekly_digest(
    parent: User,
    student: User,
    submissions: list,
    assignments: list
) -> str:
    """
    Generate weekly digest message for parent.

    Called every Sunday by Reminder Agent cron job.

  
    """
    llm = get_llm()

    submitted = len([
        s for s in submissions
        if s.status.value != "pending"
    ])
    pending = len(assignments) - submitted

    context = f"""
    Student name: {student.full_name}
    Total assignments: {len(assignments)}
    Submitted: {submitted}
    Pending: {pending}
    Week ending: {datetime.utcnow().strftime('%B %d, %Y')}
    """

    try:
        response = llm.parent(
            messages=[{
                "role": "user",
                "content": f"Write weekly digest: {context}"
            }],
            system=DIGEST_SYSTEM_PROMPT
        )

        log.info("digest_generated",
                 parent_id=str(parent.id),
                 student_id=str(student.id),
                 submitted=submitted,
                 pending=pending,
                 correlation_id=get_correlation_id())

        return response

    except Exception as e:
        log.error("digest_generation_failed",
                  error=str(e),
                  exc_info=True)
        return (
            f"{student.full_name} completed {submitted} "
            f"of {len(assignments)} assignments this week."
        )


def generate_escalation_message(
    parent: User,
    student: User,
    assignment: Assignment,
    missed_count: int
) -> str:
    """
    Generate escalation alert for parent.

    Only called when student hits
    tenant's escalation_threshold.

    Args:
        parent: Parent to notify
        student: The student
        assignment: Assignment that was missed
        missed_count: How many reminders missed

    Returns:
        Escalation message string
    """
    llm = get_llm()

    context = f"""
    Student: {student.full_name}
    Assignment: {assignment.title}
    Due date: {assignment.due_date}
    Reminders missed: {missed_count}
    """

    try:
        response = llm.parent(
            messages=[{
                "role": "user",
                "content": f"Write escalation message: {context}"
            }],
            system=ESCALATION_SYSTEM_PROMPT
        )

        log.info("escalation_generated",
                 parent_id=str(parent.id),
                 student_id=str(student.id),
                 assignment_id=str(assignment.id),
                 missed_count=missed_count,
                 correlation_id=get_correlation_id())

        return response

    except Exception as e:
        log.error("escalation_generation_failed",
                  error=str(e),
                  exc_info=True)
        return (
            f"Urgent: {student.full_name} has missed "
            f"{missed_count} reminders for "
            f"'{assignment.title}'."
        )