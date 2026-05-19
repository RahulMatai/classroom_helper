# app/agents/summariser.py
# ════════════════════════════════════════════════
# Summariser Agent
#
# WHY THIS AGENT EXISTS:
# Generates human-readable summaries of:
# - Cohort progress for teachers
# - Per-student progress for parents
# - Assignment completion stats
#
# RUNS ON: teacher requests + parent digest cron
# ════════════════════════════════════════════════

from sqlalchemy.orm import Session

from app.core.llm import get_llm
from app.core.logger import get_logger, get_correlation_id
from app.db.models import (
    User, Assignment, Submission,
    SubmissionStatus
)

log = get_logger(__name__)

COHORT_SUMMARY_PROMPT = """
You are summarising student progress for a teacher.
Be concise, factual, and actionable.
Format:
- First sentence: how many submitted vs total
- Second sentence: any patterns you notice
- Third sentence: recommended action if needed
Maximum 3 sentences total.
"""

STUDENT_SUMMARY_PROMPT = """
You are summarising one student's progress
for a weekly parent digest.
Be positive, factual, and brief.
Maximum 2 sentences.
"""


def summarise_cohort(
    teacher: User,
    assignment: Assignment,
    submissions: list,
    total_students: int
) -> str:
    """
    Summarise entire class progress on an assignment.

    Example output:
    "5 of 8 students submitted the climate essay.
     2 students submitted late. Consider sending
     a final reminder to the 3 pending students."

    """
    llm = get_llm()

    submitted = [
        s for s in submissions
        if s.status != SubmissionStatus.PENDING
    ]
    pending = total_students - len(submitted)

    context = f"""
    Assignment: {assignment.title}
    Due date: {assignment.due_date}
    Total students: {total_students}
    Submitted: {len(submitted)}
    Pending: {pending}
    """

    try:
        response = llm.summariser(
            messages=[{
                "role": "user",
                "content": f"Summarise cohort progress: {context}"
            }],
            system=COHORT_SUMMARY_PROMPT
        )

        log.info("cohort_summary_generated",
                 teacher_id=str(teacher.id),
                 assignment_id=str(assignment.id),
                 submitted=len(submitted),
                 pending=pending,
                 correlation_id=get_correlation_id())

        return response

    except Exception as e:
        log.error("cohort_summary_failed",
                  error=str(e),
                  exc_info=True)
        return (
            f"{len(submitted)} of {total_students} "
            f"students submitted '{assignment.title}'. "
            f"{pending} still pending."
        )


def summarise_student_progress(
    student: User,
    assignments: list,
    submissions: list
) -> str:
    """
    Summarise one student's progress.
    Used in parent weekly digest.
    
    """
    llm = get_llm()

    submitted = len([
        s for s in submissions
        if s.status != SubmissionStatus.PENDING
    ])

    context = f"""
    Student: {student.full_name}
    Total assignments: {len(assignments)}
    Completed: {submitted}
    Pending: {len(assignments) - submitted}
    """

    try:
        response = llm.summariser(
            messages=[{
                "role": "user",
                "content": f"Summarise student progress: {context}"
            }],
            system=STUDENT_SUMMARY_PROMPT
        )

        log.info("student_summary_generated",
                 student_id=str(student.id),
                 submitted=submitted,
                 correlation_id=get_correlation_id())

        return response

    except Exception as e:
        log.error("student_summary_failed",
                  error=str(e),
                  exc_info=True)
        return (
            f"{student.full_name} completed "
            f"{submitted} of {len(assignments)} assignments."
        )


def get_assignment_stats(
    assignment_id: str,
    db: Session
) -> dict:
    """
    Get quick stats for an assignment.

    Returns:
        {
            "total": int,
            "submitted": int,
            "pending": int,
            "reviewed": int,
            "feedback_given": int
        }
    """
    submissions = db.query(Submission).filter(
        Submission.assignment_id == assignment_id
    ).all()

    stats = {
        "total": len(submissions),
        "submitted": 0,
        "pending": 0,
        "reviewed": 0,
        "feedback_given": 0
    }

    for s in submissions:
        if s.status == SubmissionStatus.PENDING:
            stats["pending"] += 1
        elif s.status == SubmissionStatus.SUBMITTED:
            stats["submitted"] += 1
        elif s.status == SubmissionStatus.REVIEWED:
            stats["reviewed"] += 1
        elif s.status == SubmissionStatus.FEEDBACK:
            stats["feedback_given"] += 1

    log.info("assignment_stats_generated",
             assignment_id=assignment_id,
             stats=stats,
             correlation_id=get_correlation_id())

    return stats