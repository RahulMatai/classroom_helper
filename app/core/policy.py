# app/core/policy.py
# ════════════════════════════════════════════════
# Centralised Policy / RBAC Layer
#
# WHY THIS FILE EXISTS:
# Controls who can do what in the application.
# Instead of if/else checks scattered everywhere,
# all permission logic lives here.

#---------Important-----------------------------
# Never write permission checks in route handlers.
# Always use the functions in this file.
# If you need a new permission — add it here.
# ════════════════════════════════════════════════

from app.db.models import User, UserRole
from app.core.logger import get_logger

log = get_logger(__name__)

#-----Role check--------
def is_teacher(user: User)-> bool:
    # if it a teacher check
    return user.role == UserRole.TEACHER

def is_student(user: User)-> bool:
    # if it a teacher check
    return user.role == UserRole.STUDENT

def is_parent(user: User)-> bool:
    # if it a teacher check
    return user.role == UserRole.PARENT

def is_admin(user: User)-> bool:
    # if it a teacher check
    return user.role == UserRole.ADMIN

def is_teacher_or_admin(user: User)-> bool:
    # if it a teacher check
    return user.role in [UserRole.TEACHER, UserRole.ADMIN]

def can_view_assignment(user: User, assignment)-> bool:
    #can this user view assignment ?
    
    #1. must be the same tenant for eg akash group can only check akash group and not fitjee
    if user.tenant_id != assignment.tenant_id:
        log.warning("cross_tenant_access_attempt",
                    user_id=user.id,
                    user_tenant=user.tenant_id,
                    resource_tenant=assignment.tenant_id)
    if is_admin(user):
        return True
    if is_teacher(user):
        return True
    if is_student(user):
        # Student can see if they are targeted
        if assignment.target_type == "class":
            return True
        target_ids = assignment.target_ids or []
        return str(user.id) in [str(t) for t in target_ids]

    return False
def can_create_assignment(user:User)->bool:
    return is_teacher_or_admin(user)

def can_submit_work(user:User,assignment) -> bool:
    #can this student submit the assignment?
    from app.db.models import AssignmentStatus
    if not is_student(user):
        return False
    if assignment.status != AssignmentStatus.ACTIVE:
        return False
    return can_view_assignment(user,assignment)
def can_send_feedback(user, tenant_id: str)-> bool:
    if not is_admin(user):
        return False
    return str(user.tenant_id) ==str(tenant_id)

def can_manage_tenant(user: User, tenant_id: str) -> bool:
    """
    Can this user manage tenant settings?
    Admin only — and only their own tenant.
    """
    if not is_admin(user):
        return False
    return str(user.tenant_id) == str(tenant_id)

def check_permission(
    user: User,
    action: str,
    resource=None,
    resource_id: str = None
) -> bool:
    #permission check witrh logs 
        allowed = False
        if action == "create_assignment":
            allowed = can_create_assignment(user)
        elif action == "view_assignment" and resource:
            allowed = can_view_assignment(user, resource)
        elif action == "submit_work" and resource:
            allowed = can_submit_work(user, resource)
        elif action == "send_feedback" and resource:
            allowed = can_send_feedback(user, resource)
        elif action == "manage_tenant" and resource_id:
            allowed = can_manage_tenant(user, resource_id)
        else:
            allowed = False
        log.info("permission_check",
             user_id=user.id,
             role=str(user.role),
             action=action,
             resource_id=resource_id,
             allowed=allowed)

        return allowed
    
        
    

