# app/db/models.py
# ════════════════════════════════════════════════
# Database Models
#
# WHY THIS FILE EXISTS:
# Defines every table in our database using
# SQLAlchemy ORM. Each class = one table.
#
# WHY SQLALCHEMY ORM?
# Instead of writing raw SQL like:
#   SELECT * FROM users WHERE id = '123'
# We write Python like:
#   user = session.get(User, '123')
# Safer, cleaner, less error prone.
#
# --------------- important --------------
# Each model class maps to one database table.
# Each class variable maps to one column.
# Never write raw SQL — always use these models.
# ════════════════════════════════════════════════

import uuid
from datetime import datetime
from enum import Enum as PyEnum
from sqlalchemy import UniqueConstraint

from sqlalchemy import (
    Column, String, Boolean, DateTime,
    ForeignKey, Text, Integer, Enum, JSON 
)
from sqlalchemy.dialects.postgresql import UUID,JSONB
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func

# ── Base ──────────────────────────────────────────
# All models inherit from this.
# It keeps track of all our tables.
Base = declarative_base()


# ── Helper: UUID primary key ──────────────────────
def generate_uuid():
    """
    Generate a unique ID for every row.
    We use UUID instead of integer IDs because:
    - Integer IDs expose how many records you have
    - Integer IDs are easy to guess (try id=1, id=2...)
    - UUIDs are random and impossible to guess
    Example: '550e8400-e29b-41d4-a716-446655440000'
    """
    return str(uuid.uuid4())

class UserRole(PyEnum):
    """
    controls what we can show to relevant users
    teacher creates assignment and sends feedback
    student recieve assignment and submit work
    parent recieve digest only
    admin manage tenanets feature flags
    """
    TEACHER = "teacher"
    STUDENT = "student"
    PARENT  = "parent"
    ADMIN   = "admin"

class Channel(PyEnum):
    """
    which messaginf channel they prefer, telegram whatsapp or web ?
    """
    TELEGRAM = "telegram"
    WHATSAPP = "whatsapp"
    WEB      = "web"

class AssignmentStatus(PyEnum):
    """
    Basically draft  draft active closed archieved 
    """
    DRAFT    = "draft"
    ACTIVE   = "active"
    CLOSED   = "closed"
    ARCHIVED = "archived"
    
class SubmissionStatus(PyEnum):
    """
    Lifecycle of a student submission.
    PENDING   → assignment given, nothing submitted yet
    SUBMITTED → student sent their work
    REVIEWED  → teacher has opened and read it
    FEEDBACK  → teacher sent feedback back
    """
    PENDING   = "pending"
    SUBMITTED = "submitted"
    REVIEWED  = "reviewed"
    FEEDBACK  = "feedback"
    
class AuditAction(PyEnum):
    """
    Every important action we log in audit_logs.
    This gives us a complete trail of everything.
    Never delete from audit_logs — append only.
    """
    USER_LOGIN          = "user_login"
    USER_LOGOUT         = "user_logout"
    ASSIGNMENT_CREATED  = "assignment_created"
    ASSIGNMENT_UPDATED  = "assignment_updated"
    SUBMISSION_RECEIVED = "submission_received"
    FEEDBACK_SENT       = "feedback_sent"
    REMINDER_SENT       = "reminder_sent"
    DIGEST_SENT         = "digest_sent"
    ESCALATION_SENT     = "escalation_sent"
    MAGIC_LINK_SENT     = "magic_link_sent"
    MAGIC_LINK_USED     = "magic_link_used"
    CHANNEL_BOUND       = "channel_bound"
    
    
# ── Model 1: Tenant ───────────────────────────────
# One row per school.
# Every other table has tenant_id pointing here.
# This is what makes the app multi-school safe —
# a teacher from School A can never see School B data.

class Tenant(Base):
    __tablename__ = "tenants"
    
    id = Column(
        UUID(as_uuid=False),
        primary_key=True,
        default=generate_uuid,
        nullable=False
    )
    #school name and URL
    name = Column(String(255), nullable=False, unique=True)
    slug = Column(String(100), nullable=False, unique=True)
    
    #channels Creds can be nullable because not everyone will use  every channel 
    telegram_bot_token = Column(Text, nullable=True)
    twilio_sid         = Column(Text, nullable=True)
    twilio_auth_token  = Column(Text, nullable=True)
    
    # Reminder policy — overrides global defaults
    # Admin can change these per school
    max_nudges_per_day    = Column(Integer, default=2,  nullable=False)
    quiet_hours_start     = Column(Integer, default=22, nullable=False)
    quiet_hours_end       = Column(Integer, default=8,  nullable=False)
    escalation_threshold  = Column(Integer, default=3,  nullable=False)
    
    # feature Flags stored as JSON
    # admin can toggle feature  per school without any need of deployemnet
    feature_flags = Column(JSON, nullable=True, default=dict)
    is_active  = Column(Boolean, default=True, nullable=False)
    
    # server_default means the DB sets this automatically
    # even if we forget to set it in Python
    created_at = Column(
        DateTime,
        server_default=func.now(),
        nullable=False
    )
    updated_at = Column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    # ── Relationships ─────────────────────────────
    # This tells SQLAlchemy:
    # "A tenant has many users"
    # We can now do: tenant.users to get all users
    users       = relationship("User",       back_populates="tenant")
    assignments = relationship("Assignment", back_populates="tenant")
    audit_logs  = relationship("AuditLog",   back_populates="tenant")
    nudges      = relationship("Nudge",      back_populates="tenant")
    submissions = relationship("Submission", back_populates="tenant")

    def __repr__(self):
        """
        What prints when you do print(tenant)
        Useful for debugging
        """
        return f"<Tenant {self.name}>"

class User(Base):
    __tablename__ = "users"
    
    # Primary Key
    id = Column(
        UUID(as_uuid=False),
        primary_key=True,
        default=generate_uuid,
        nullable=False
    )
    
    #which school this belongs to
    
    tenant_id = Column(
        UUID(as_uuid=False),
        ForeignKey("tenants.id"),
        nullable=False
    )
    
    # Basic info
    email     = Column(String(255), nullable=False, unique=True)
    full_name = Column(String(255), nullable=True)

    # Role controls access — teacher/student/parent/admin
    role = Column(
        Enum(UserRole),
        nullable=False
    )

    # Which channel they prefer — set during onboarding
    preferred_channel = Column(
        Enum(Channel),
        nullable=True
    )

    #messaging channel Identities
    telegram_id      = Column(String(100), nullable=True, unique=True)
    whatsapp_number  = Column(String(20),  nullable=True)
    channel_verified = Column(Boolean, default=False, nullable=False)
    
    # Parent → Student link (self join)
    # If this user is a parent, parent_of points
    # to the student's user id
    parent_of = Column(
        UUID(as_uuid=False),
        ForeignKey("users.id"),
        nullable=True
    )
    
    is_active   = Column(Boolean, default=True,  nullable=False)
    created_at  = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at  = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    last_seen_at = Column(DateTime, nullable=True)
    
    # ── Relationships ─────────────────────────────
    tenant          = relationship("Tenant",     back_populates="users")
    assignments     = relationship("Assignment", back_populates="teacher",
                                   foreign_keys="Assignment.teacher_id")
    submissions     = relationship("Submission", back_populates="student",
                                   foreign_keys="Submission.student_id")
    refresh_tokens  = relationship("RefreshToken",   back_populates="user")
    channel_bindings = relationship("ChannelBinding", back_populates="user")
    audit_logs      = relationship("AuditLog",   back_populates="user")
    nudges          = relationship("Nudge",      back_populates="student",
                                   foreign_keys="Nudge.student_id")

    # Self referential — get this parent's student
    student = relationship("User", remote_side=[id], foreign_keys=[parent_of])

    def __repr__(self):
        return f"<User {self.email} ({self.role})>"

# ── Model 3: Assignment ───────────────────────────
# Created by teachers for students.
# target_type and target_ids control who gets it:
#   target_type = "student"  → specific students
#   target_type = "group"    → a group of students
#   target_type = "class"    → entire class
# raw_input stores what teacher originally typed
# so we can always trace how AI parsed it

class Assignment(Base):
    __tablename__ = "assignments"

    id = Column(
        UUID(as_uuid=False),
        primary_key=True,
        default=generate_uuid,
        nullable=False
    )
    
    # Every assignment belongs to a school
    tenant_id = Column(
        UUID(as_uuid=False),
        ForeignKey("tenants.id"),
        nullable=False
    )
    
    # Who created this assignment
    teacher_id = Column(
        UUID(as_uuid=False),
        ForeignKey("users.id"),
        nullable=False
    )
    # Assignment details
    title       = Column(String(500), nullable=False)
    description = Column(Text,        nullable=True)

    # Lifecycle status
    status = Column(
        Enum(AssignmentStatus),
        default=AssignmentStatus.DRAFT,
        nullable=False
    )

    # Who is this for?
    # target_type: "student", "group", "class"
    # target_ids: ["uuid1", "uuid2"] stored as JSON
    target_type = Column(String(20),  nullable=True)
    target_ids  = Column(JSONB,       nullable=True)

    # When is it due
    due_date = Column(DateTime, nullable=True)

    # What teacher originally typed before AI parsed it
    # Important for debugging AI parsing issues
    raw_input = Column(Text, nullable=True)

    created_at = Column(
        DateTime,
        server_default=func.now(),
        nullable=False
    )
    updated_at = Column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    # ── Relationships ─────────────────────────────
    #back populates is nothing but the join
    tenant      = relationship("Tenant", back_populates="assignments")
    teacher     = relationship("User",   back_populates="assignments",
                               foreign_keys=[teacher_id])
    submissions = relationship("Submission", back_populates="assignment")
    nudges      = relationship("Nudge",      back_populates="assignment")

    def __repr__(self):
        return f"<Assignment {self.title} ({self.status})>"

# ── Model 4: Submission ───────────────────────────
# One row per student per assignment.
# Created automatically as PENDING when assignment
# is sent. Updated when student submits work.
#
# UNIQUE(assignment_id, student_id) means:
# one student can only submit once per assignment.
# Trying to submit twice updates the existing row.

class Submission(Base):
    __tablename__ = "submissions"

    id = Column(
        UUID(as_uuid=False),
        primary_key=True,
        default=generate_uuid,
        nullable=False
    )
    
    # The assignment this submission is for
    assignment_id = Column(
        UUID(as_uuid=False),
        ForeignKey("assignments.id"),
        nullable=False
    )

    # The student who submitted
    student_id = Column(
        UUID(as_uuid=False),
        ForeignKey("users.id"),
        nullable=False
    )
    
    # Which school
    tenant_id = Column(
        UUID(as_uuid=False),
        ForeignKey("tenants.id"),
        nullable=False
    )
    
     # Where the submission is in its lifecycle
    status = Column(
        Enum(SubmissionStatus),
        default=SubmissionStatus.PENDING,
        nullable=False
    )
    
    # What type of content did student send?
    # "text", "file", "voice"
    content_type = Column(String(20), nullable=True)

    # The actual submitted content
    # Only one of these will have a value
    text_content     = Column(Text, nullable=True)  # if text
    file_url         = Column(Text, nullable=True)  # if file
    voice_transcript = Column(Text, nullable=True)  # if voice

    # Teacher feedback
    feedback_text = Column(Text, nullable=True)
    
    # Timestamps for each lifecycle stage
    submitted_at = Column(DateTime, nullable=True)
    reviewed_at  = Column(DateTime, nullable=True)
    feedback_at  = Column(DateTime, nullable=True)
    
    created_at = Column(
        DateTime,
        server_default=func.now(),
        nullable=False
    )
    updated_at = Column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )
    
    # ── Constraints ───────────────────────────────
    # Prevents a student submitting twice
    # for the same assignment
    __table_args__ = (
        UniqueConstraint(
            "assignment_id",
            "student_id",
            name="uq_submission_assignment_student"
        ),
    )
    
    # ── Relationships ─────────────────────────────
    assignment = relationship("Assignment", back_populates="submissions")
    student    = relationship("User",       back_populates="submissions",
                              foreign_keys=[student_id])
    tenant     = relationship("Tenant",     back_populates="submissions")

    def __repr__(self):
        return f"<Submission {self.student_id} → {self.assignment_id} ({self.status})>"

# ── Model 5: AuditLog ─────────────────────────────
# Permanent record of every important action.
# NEVER update or delete rows in this table.
# Append only — this is our CCTV footage.
#
# correlation_id links this log entry to the
# exact request that triggered it.
# Filter by correlation_id to see full journey
# of any single request across the system.

class AuditLog(Base):
    __tablename__ = "audit_logs"
    
    id = Column(
        UUID(as_uuid=False),
        primary_key=True,
        default=generate_uuid,
        nullable=False
    )
    
    # Which school this action happened in
    tenant_id = Column(
        UUID(as_uuid=False),
        ForeignKey("tenants.id"),
        nullable=False
    )
    
    # Who performed this action
    # nullable because some system actions
    # have no specific user (e.g. cron jobs)
    user_id = Column(
        UUID(as_uuid=False),
        ForeignKey("users.id"),
        nullable=True
    )
    
    # What happened
    action = Column(
        Enum(AuditAction),
        nullable=False
    )

    # Which channel triggered this action
    channel = Column(
        Enum(Channel),
        nullable=True
    )

    # Trace ID — links all logs for one request
    # Example: "req_a3f9bc12"
    # Filter by this to see full request journey
    correlation_id = Column(String(50), nullable=True)

    # What entity was affected
    # entity_type: "assignment", "submission", "user"
    # entity_id: the UUID of that entity
    entity_type = Column(String(50), nullable=True)
    entity_id   = Column(UUID(as_uuid=False), nullable=True)

    # Extra context stored as JSON
    # Different actions store different metadata
    # Example for ASSIGNMENT_CREATED:
    # {"title": "Essay on climate", "student_count": 8}
    # Example for REMINDER_SENT:
    # {"nudge_count": 2, "channel": "telegram"}
    extradata = Column(JSONB, nullable=True)
    
    # IP address of the request
    # Useful for security investigations
    ip_address = Column(String(45), nullable=True)

    # Only created_at — never updated
    created_at = Column(
        DateTime,
        server_default=func.now(),
        nullable=False
    )

    # ── Relationships ─────────────────────────────
    tenant = relationship("Tenant", back_populates="audit_logs")
    user   = relationship("User",   back_populates="audit_logs")

    def __repr__(self):
        return f"<AuditLog {self.action} by {self.user_id} at {self.created_at}>"

# ── Model 6: RefreshToken ─────────────────────────
# Stores JWT refresh tokens for session management.
#
# HOW REFRESH TOKEN ROTATION WORKS:
# 1. User logs in → we issue access token + refresh token
# 2. Access token expires after 60 mins
# 3. User sends refresh token → we issue NEW access token
#    + NEW refresh token
# 4. Old refresh token is immediately revoked
# 5. parent_token_id tracks the chain:
#    token_1 → token_2 → token_3
#
# WHY THIS IS SECURE:
# If someone steals a refresh token and uses it,
# the real user's next request will find their
# token already revoked → we know there's a breach
# → revoke entire chain automatically

class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(
        UUID(as_uuid=False),
        primary_key=True,
        default=generate_uuid,
        nullable=False
    )

    # Which user this token belongs to
    user_id = Column(
        UUID(as_uuid=False),
        ForeignKey("users.id"),
        nullable=False
    )

    # We never store the raw token — only its hash
    # If database is breached, hashes are useless
    # without the original tokens
    token_hash = Column(String(255), nullable=False, unique=True)

    # Points to the previous token in the chain
    # Allows us to revoke entire session chain
    # if we detect token theft
    parent_token_id = Column(
        UUID(as_uuid=False),
        ForeignKey("refresh_tokens.id"),
        nullable=True
    )

    # Once used to get a new token, immediately
    # set to True — can never be used again
    is_revoked = Column(Boolean, default=False, nullable=False)

    # What device/browser issued this token
    # Useful for "active sessions" feature
    # Example: "Chrome on MacOS" or "Telegram Bot"
    device_info = Column(String(255), nullable=True)

    # When this token stops working
    expires_at = Column(DateTime, nullable=False)

    created_at = Column(
        DateTime,
        server_default=func.now(),
        nullable=False
    )

    # ── Relationships ─────────────────────────────
    user = relationship("User", back_populates="refresh_tokens")

    # Self referential — previous token in chain
    parent_token = relationship(
        "RefreshToken",
        remote_side=[id],
        foreign_keys=[parent_token_id]
    )

    def __repr__(self):
        return f"<RefreshToken {self.id} revoked={self.is_revoked}>"
    

# ── Model 7: ChannelBinding ───────────────────────
# Links a web account to Telegram or WhatsApp.
#
# HOW CHANNEL BINDING WORKS:
# 1. Teacher clicks "Connect Telegram" on web app
# 2. We generate a short-lived signed nonce
#    e.g. "bind_a3f9bc12"
# 3. Teacher sends that nonce to our Telegram bot
# 4. Bot verifies nonce → links telegram_id to
#    their web account
# 5. is_verified = True, nonce cleared
#
# WHY NONCE AND NOT JUST CHAT HANDLE?
# Anyone could claim to be "@rahul" on Telegram.
# A signed nonce proves the person sending it
# is the same person who is logged into the web app.
# Security requirement from the assignment spec.

class ChannelBinding(Base):
    __tablename__ = "channel_bindings"
     
    id = Column(
        UUID(as_uuid=False),
        primary_key=True,
        default=generate_uuid,
        nullable=False
    )
    
    # Which channel — telegram or whatsapp
    channel = Column(
        Enum(Channel),
        nullable=False
    )
    
    # The user's ID on that channel
    # For Telegram: their numeric chat ID
    # For WhatsApp: their phone number
    channel_user_id = Column(
        String(100),
        nullable=False,
        unique=True
    )
    
    # Short lived signed token used to verify binding
    # Generated when user clicks "Connect Channel"
    # Cleared after successful verification
    nonce            = Column(String(100), nullable=True)
    nonce_expires_at = Column(DateTime,    nullable=True)

    # Whether the binding has been verified
    is_verified = Column(Boolean, default=False, nullable=False)
    verified_at = Column(DateTime, nullable=True)
    
    created_at = Column(
        DateTime,
        server_default=func.now(),
        nullable=False
    )

    # ── Constraints ───────────────────────────────
    # One channel_user_id can only be bound
    # to one account — prevents someone binding
    # their Telegram to multiple school accounts
    __table_args__ = (
        UniqueConstraint(
            "channel",
            "channel_user_id",
            name="uq_binding_channel_user"
        ),
    )

    # ── Relationships ─────────────────────────────
    user = relationship("User", back_populates="channel_bindings")

    def __repr__(self):
        return f"<ChannelBinding {self.channel} → {self.user_id} verified={self.is_verified}>"
    
# ── Model 8: Nudge ────────────────────────────────
# Tracks every reminder sent to a student.
#
# WHY WE TRACK NUDGES:
# 1. Enforce max_nudges_per_day policy
#    → don't spam students
# 2. Track consecutive_missed
#    → when it hits escalation_threshold,
#       parent gets alerted
# 3. Audit trail of every reminder sent
#
# HOW ESCALATION WORKS:
# Student misses reminder → consecutive_missed + 1
# Student submits work   → consecutive_missed = 0
# consecutive_missed hits tenant threshold (default 3)
# → Parent Agent sends escalation WhatsApp message

class Nudge(Base):
    __tablename__ = "nudges"

    id = Column(
        UUID(as_uuid=False),
        primary_key=True,
        default=generate_uuid,
        nullable=False
    )
    
    # Which school
    tenant_id = Column(
        UUID(as_uuid=False),
        ForeignKey("tenants.id"),
        nullable=False
    )
    
    # Which student is being nudged
    student_id = Column(
        UUID(as_uuid=False),
        ForeignKey("users.id"),
        nullable=False
    )
    
    # Which assignment this nudge is about
    assignment_id = Column(
        UUID(as_uuid=False),
        ForeignKey("assignments.id"),
        nullable=False
    )
    # Type of nudge
    # "reminder"   → regular deadline reminder
    # "escalation" → parent alert
    # "digest"     → weekly parent digest
    nudge_type = Column(String(20), nullable=False)

    # Which channel was used to send this nudge
    channel = Column(Enum(Channel), nullable=True)

    # Did the message actually reach the user?
    # False if Telegram/WhatsApp API call failed
    was_delivered = Column(Boolean, default=False, nullable=False)

    # How many reminders has this student missed
    # in a row for this assignment?
    # Resets to 0 when student submits
    # Triggers escalation when hits threshold
    consecutive_missed = Column(Integer, default=0, nullable=False)

    # When the nudge was sent
    sent_at = Column(DateTime, nullable=True)
    
    created_at = Column(
        DateTime,
        server_default=func.now(),
        nullable=False
    )

    # ── Relationships ─────────────────────────────
    tenant     = relationship("Tenant",     back_populates="nudges")
    student    = relationship("User",       back_populates="nudges",
                              foreign_keys=[student_id])
    assignment = relationship("Assignment", back_populates="nudges")

    def __repr__(self):
        return f"<Nudge {self.nudge_type} → {self.student_id} delivered={self.was_delivered}>"
