# app/agents/student.py
# ════════════════════════════════════════════════
# Student Agent
#
# WHY THIS AGENT EXISTS:
# Handles everything a student does:
# - Receive and acknowledge assignments
# - Process submissions (text/file/voice)
# - Track progress
#
# RUNS ON: messages classified as
#   submission, status.update, assignment.query
# ════════════════════════════════════════════════

import json
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session

from app.core.llm import get_llm
from app.core.logger import get_logger, get_correlation_id
from app.core.events import publish_event, EventType
from app.db.models import (
    Submission, SubmissionStatus,
    AuditLog, AuditAction, User, Assignment
)

log = get_logger(__name__)

STUDENT_SYSTEM_PROMPT = """
You are an AI assistant for students on a school platform.
Help students understand their assignments and submissions.
Be encouraging, clear, and concise.
Never do the assignment for them — guide them instead.
"""


def process_submission(
    student: User,
    assignment: Assignment,
    content: str,
    content_type: str,
    db: Session,
    file_url: str = None,
    voice_transcript: str = None
) -> Submission:
    """
    Process a student submission.

    1. Find or create submission record
    2. Update with submitted content
    3. Publish event → teacher gets live popup
    4. Log to audit trail
    """
    # Find existing pending submission
    submission = db.query(Submission).filter(
        Submission.assignment_id == assignment.id,
        Submission.student_id == str(student.id)
    ).first()

    if not submission:
        # Create new if doesn't exist
        submission = Submission(
            assignment_id=assignment.id,
            student_id=str(student.id),
            tenant_id=str(student.tenant_id)
        )
        db.add(submission)

    # Update submission
    submission.status        = SubmissionStatus.SUBMITTED
    submission.content_type  = content_type
    submission.submitted_at  = datetime.utcnow()

    if content_type == "text":
        submission.text_content = content
    elif content_type == "file":
        submission.file_url = file_url
    elif content_type == "voice":
        submission.voice_transcript = voice_transcript

    db.flush()

    # Audit log
    audit = AuditLog(
        tenant_id=str(student.tenant_id),
        user_id=str(student.id),
        action=AuditAction.SUBMISSION_RECEIVED,
        entity_type="submission",
        entity_id=submission.id,
        correlation_id=get_correlation_id()
    )
    db.add(audit)

    # Publish event → teacher dashboard popup
    publish_event(
        event_type=EventType.SUBMISSION_RECEIVED,
        tenant_id=str(student.tenant_id),
        data={
            "submission_id": submission.id,
            "student_name": student.full_name,
            "assignment_id": str(assignment.id),
            "assignment_title": assignment.title,
            "content_type": content_type
        },
        correlation_id=get_correlation_id()
    )

    log.info("submission_processed",
             submission_id=submission.id,
             student_id=str(student.id),
             assignment_id=str(assignment.id),
             content_type=content_type,
             correlation_id=get_correlation_id())

    return submission


def generate_acknowledgement(
    student: User,
    assignment: Assignment,
    content_type: str
) -> str:
    """
    Generate a friendly acknowledgement message.

    Sent back to student after submission.

    """
    llm = get_llm()

    try:
        response = llm.student(
            messages=[{
                "role": "user",
                "content": f"""
                Student {student.full_name} just submitted
                their {content_type} for '{assignment.title}'.
                Generate a brief friendly confirmation message.
                """
            }],
            system=STUDENT_SYSTEM_PROMPT
        )

        return response

    except Exception as e:
        log.error("acknowledgement_failed",
                  error=str(e),
                  exc_info=True)
        return f"✅ Submission received for {assignment.title}!"