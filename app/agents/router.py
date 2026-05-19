# app/agents/router.py
# ════════════════════════════════════════════════
# Router / Intent Classification Agent
#
# WHY THIS AGENT EXISTS:
# Every message needs to be classified before
# we know which agent should handle it.
# This agent reads the message and decides:
# "Is this an assignment creation? A submission?
#  A status query? Smalltalk?"
#
# RUNS ON: every inbound message after safety check
# ════════════════════════════════════════════════

from app.core.llm import get_llm
from app.core.logger import get_logger, get_correlation_id

log = get_logger(__name__)

# All possible intents
INTENTS = [
    "assignment.create",    # teacher creating assignment
    "assignment.query",     # asking about an assignment
    "submission",           # student submitting work
    "feedback",             # teacher sending feedback
    "status.update",        # progress update
    "parent.optin",         # parent opting in
    "escalation",           # urgent situation
    "smalltalk",            # casual conversation
    "unknown"               # can't classify
]

ROUTER_SYSTEM_PROMPT = f"""
You are an intent classifier for a school assignment platform.
Classify the message into exactly one of these intents:
{', '.join(INTENTS)}

Respond with JSON only:
{{
  "intent": "the_intent",
  "confidence": 0.0-1.0,
  "reason": "why you chose this intent"
}}

Examples:
- "Essay on climate change due Friday" → assignment.create
- "Here is my essay..." → submission
- "When is the assignment due?" → assignment.query
- "Hi how are you" → smalltalk
"""


def classify_intent(
    message: str,
    user_role: str = None
) -> dict:
    """
    Classify the intent of an incoming message.

    Args:
        message: The user's message
        user_role: Role hint (teacher/student/parent)

    Returns:
        {
            "intent": str,
            "confidence": float,
            "reason": str
        }
    """
    import json
    llm = get_llm()

    # Add role context if available
    content = f"Message: {message}"
    if user_role:
        content += f"\nSender role: {user_role}"

    try:
        response = llm.router(
            messages=[{"role": "user", "content": content}],
            system=ROUTER_SYSTEM_PROMPT
        )

        result = json.loads(response)

        log.info("intent_classified",
                 intent=result.get("intent"),
                 confidence=result.get("confidence"),
                 correlation_id=get_correlation_id())

        return result

    except Exception as e:
        log.error("intent_classification_failed",
                  error=str(e),
                  exc_info=True)
        return {
            "intent": "unknown",
            "confidence": 0.0,
            "reason": "Classification failed"
        }