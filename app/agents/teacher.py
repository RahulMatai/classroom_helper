# app/agents/teacher.py
# ════════════════════════════════════════════════
# Teacher Agent
#
# WHY THIS AGENT EXISTS:
# Handles everything a teacher does:
# - Parse natural language into assignments
# - Generate cohort summaries
# - Process feedback to students
#
# RUNS ON: messages classified as
#   assignment.create, feedback, assignment.query
# ════════════════════════════════════════════════

import json
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session

from app.core.llm import get_llm
from app.core.logger import get_logger, get_correlation_id
from app.core.events import publish_event, EventType
from app.db.models import (
    Assignment, AssignmentStatus,
    AuditLog, AuditAction, User
)

log = get_logger(__name__)

TEACHER_SYSTEM_PROMPT = """
You are an AI assistant for teachers on a school platform.
Help teachers create assignments from natural language.

When parsing an assignment extract:
- title: short descriptive title
- description: full details
- due_date: in ISO format (YYYY-MM-DD) or null
- target_type: "class", "group", or "student"
- word_limit: if mentioned, else null

Respond with JSON only.
"""

SUMMARISER_PROMPT = """
You are summarising student progress for a teacher.
Be concise, factual, and helpful.
Format: "X of Y submitted. [Key observations]"
Keep it under 3 sentences.
"""


def parse_assignment_from_text(
    raw_text: str,
    teacher: User
) -> dict:
    """
    Parse natural language into structured assignment.
    """
    llm = get_llm()

    try:
        response = llm.teacher(
            messages=[{
                "role": "user",
                "content": f"Parse this assignment: {raw_text}"
            }],
            system=TEACHER_SYSTEM_PROMPT
        )

        parsed = json.loads(response)

        log.info("assignment_parsed",
                 teacher_id=str(teacher.id),
                 title=parsed.get("title"),
                 correlation_id=get_correlation_id())

        return parsed

    except Exception as e:
        log.error("assignment_parse_failed",
                  error=str(e),
                  exc_info=True)
        return {
            "title": raw_text[:100],
            "description": raw_text,
            "due_date": None,
            "target_type": "class"
        }


def create_assignment(
    raw_text: str,
    teacher: User,
    db: Session
) -> Assignment:
    """
    Full assignment creation flow.

    1. Parse natural language
    2. Save to database
    3. Publish event to Redis
    4. Log to audit trail
    """
    # Parse natural language
    parsed = parse_assignment_from_text(raw_text, teacher)

    # Parse due date if present
    due_date = None
    if parsed.get("due_date"):
        try:
            due_date = datetime.fromisoformat(
                parsed["due_date"]
            )
        except ValueError:
            pass

    # Create assignment
    assignment = Assignment(
        tenant_id=str(teacher.tenant_id),
        teacher_id=str(teacher.id),
        title=parsed.get("title", raw_text[:100]),
        description=parsed.get("description"),
        status=AssignmentStatus.ACTIVE,
        target_type=parsed.get("target_type", "class"),
        due_date=due_date,
        raw_input=raw_text
    )
    db.add(assignment)
    db.flush()

    # Audit log
    audit = AuditLog(
        tenant_id=str(teacher.tenant_id),
        user_id=str(teacher.id),
        action=AuditAction.ASSIGNMENT_CREATED,
        entity_type="assignment",
        entity_id=assignment.id,
        correlation_id=get_correlation_id()
    )
    db.add(audit)

    # Publish event → triggers live popup on student dashboards
    publish_event(
        event_type=EventType.ASSIGNMENT_CREATED,
        tenant_id=str(teacher.tenant_id),
        data={
            "assignment_id": assignment.id,
            "title": assignment.title,
            "teacher_name": teacher.full_name,
            "due_date": str(due_date) if due_date else None
        },
        correlation_id=get_correlation_id()
    )

    log.info("assignment_created",
             assignment_id=assignment.id,
             teacher_id=str(teacher.id),
             title=assignment.title,
             correlation_id=get_correlation_id())

    return assignment


def generate_cohort_summary(
    assignments: list,
    submissions: list,
    student_count: int
) -> str:
    """
    Generate AI summary of class progress.

    Example output:
    "5 of 8 submitted. 2 students appear stuck
     on the introduction. 1 student hasn't started."
    """
    llm = get_llm()

    submitted = len([
        s for s in submissions
        if s.status.value != "pending"
    ])

    context = f"""
    Total students: {student_count}
    Submitted: {submitted}
    Pending: {student_count - submitted}
    """

    try:
        response = llm.summariser(
            messages=[{
                "role": "user",
                "content": f"Summarise this class progress: {context}"
            }],
            system=SUMMARISER_PROMPT
        )

        log.info("cohort_summary_generated",
                 submitted=submitted,
                 total=student_count,
                 correlation_id=get_correlation_id())

        return response

    except Exception as e:
        log.error("cohort_summary_failed",
                  error=str(e),
                  exc_info=True)
        return f"{submitted} of {student_count} students submitted."