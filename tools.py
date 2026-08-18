import asyncio
import functools
import logging
import re
import uuid as _uuid
from typing import Annotated

from livekit.agents import function_tool
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

import data

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

_SLOT_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_PHONE_RE = re.compile(r"^[\d\s\+\-\(\)\.x]{7,25}$")
_APPT_ID_RE = re.compile(r"^[0-9a-fA-F]{8}$|^[0-9a-fA-F\-]{36}$")
_MAX_QUERY_LEN = 200
_MAX_OUTPUT_LEN = 1500


def _truncate(s: str) -> str:
    if len(s) <= _MAX_OUTPUT_LEN:
        return s
    return s[:_MAX_OUTPUT_LEN] + " … [truncated]"


# ---------------------------------------------------------------------------
# Tool guard: per-call timeout + retry on transient DB errors
# ---------------------------------------------------------------------------

_TOOL_TIMEOUT = 8.0   # seconds per attempt
_TOOL_RETRIES = 2     # retries on OperationalError (e.g. SQLite db locked)
_RETRY_BACKOFF = 0.3  # seconds; doubles each attempt


def tool_guard(timeout: float = _TOOL_TIMEOUT, retries: int = _TOOL_RETRIES):
    """Wrap an async tool: timeout per attempt, retry on transient DB errors.

    Apply UNDER @function_tool so livekit-agents sees the original signature
    via functools.wraps / inspect.signature's __wrapped__ follow-through.

    Note: asyncio.wait_for cancels only at await points. Synchronous SQLAlchemy
    calls (SQLite) are fast enough that this is a safety net, not a hard cap.
    """
    def decorator(fn):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            for attempt in range(retries + 1):
                try:
                    return await asyncio.wait_for(fn(*args, **kwargs), timeout=timeout)
                except asyncio.TimeoutError:
                    return f"Request timed out after {timeout:.0f}s. Please try again."
                except OperationalError:
                    if attempt < retries:
                        await asyncio.sleep(_RETRY_BACKOFF * (2 ** attempt))
                    else:
                        return "Database temporarily unavailable. Please try again in a moment."
                except Exception:
                    logger.exception("Unhandled error in tool %s", fn.__name__)
                    return "An unexpected error occurred. Please try again."
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@function_tool(
    description=(
        "Check peptide inventory. Pass a peptide name (e.g. 'BPC-157') to get "
        "details on a specific peptide, or pass a health goal / symptom "
        "(e.g. 'fat loss', 'sleep', 'healing') to find all matching peptides in stock."
    )
)
@tool_guard()
async def check_peptide_stock(
    query: Annotated[str, "Peptide name or health goal/symptom to search for"],
) -> str:
    if not query or not query.strip():
        return "Please provide a peptide name or health goal."
    if len(query) > _MAX_QUERY_LEN:
        return f"Query too long (max {_MAX_QUERY_LEN} characters). Please be more specific."

    q = query.lower().strip()

    if q in ("all", "list", "everything", "inventory", "stock", "what do you have"):
        in_stock = [
            f"{name} (${item['price']}/unit)"
            for name, item in data.PEPTIDE_STOCK.items()
            if item["quantity"] > 0
        ]
        result = "In stock: " + ", ".join(in_stock) + "." if in_stock else "No peptides currently in stock."
        return _truncate(result)

    for name, item in data.PEPTIDE_STOCK.items():
        if name.lower() == q:
            status = f"{item['quantity']} {item['unit']}" if item["quantity"] > 0 else "OUT OF STOCK"
            return _truncate(
                f"{name}: {item['description']} "
                f"| In stock: {status} | ${item['price']} per unit."
            )

    matches = []
    for name, item in data.PEPTIDE_STOCK.items():
        if item["quantity"] > 0 and any(q in goal.lower() for goal in item["goals"]):
            matches.append(
                f"{name}: {item['description']} | {item['quantity']} {item['unit']} | ${item['price']}/unit"
            )

    if matches:
        return _truncate(f"Peptides matching '{query}':\n" + "\n".join(matches))

    return (
        f"No peptides found matching '{query}'. "
        "Try a goal like 'fat loss', 'healing', 'sleep', 'cognitive', "
        "'anti-aging', 'immune', 'muscle', or 'sexual health'."
    )


def make_check_available_slots(db: Session):
    """Return a check_available_slots tool with DB-backed booked slot exclusion."""

    @function_tool(
        description=(
            "Check available appointment slots. "
            "Pass a date string 'YYYY-MM-DD' to see slots for that day, "
            "or pass 'next' to get the next available slot, "
            "or pass 'week' to list all available slots in the next 7 business days. "
            "Also accepts appointment type to show price/duration: "
            "initial_consultation, follow_up, peptide_review, lab_review."
        )
    )
    @tool_guard()
    async def check_available_slots(
        query: Annotated[
            str,
            "Date 'YYYY-MM-DD', 'next', or 'week'. Optionally prefix with appointment type, e.g. 'follow_up 2025-09-10'.",
        ],
    ) -> str:
        if not query or not query.strip():
            return "Please provide a date ('YYYY-MM-DD'), 'next', or 'week'."
        if len(query) > 60:
            return "Query too long. Provide a date ('YYYY-MM-DD'), 'next', or 'week'."

        parts = query.strip().lower().split()

        appt_type = None
        date_query = query.strip()
        for key in data.APPOINTMENT_TYPES:
            if parts[0] == key:
                appt_type = key
                date_query = " ".join(parts[1:]) if len(parts) > 1 else "week"
                break

        dq_check = date_query.strip().lower()
        if dq_check not in ("next", "week") and not _DATE_RE.match(dq_check):
            return (
                f"Invalid date or query '{date_query}'. "
                "Use 'YYYY-MM-DD', 'next', or 'week'."
            )

        type_info = ""
        if appt_type:
            t = data.APPOINTMENT_TYPES[appt_type]
            type_info = f"{t['label']} ({t['duration_min']} min, ${t['price']}). "

        from models import Appointment
        booked_slots = {a.slot for a in db.query(Appointment.slot).all()}

        available = {
            slot: v
            for slot, v in data.AVAILABLE_SLOTS.items()
            if v and slot not in booked_slots
        }

        if not available:
            return type_info + "No available slots in the next 7 business days."

        dq = date_query.strip().lower()

        if dq == "next":
            slot = sorted(available.keys())[0]
            return type_info + f"Next available slot: {slot}."

        if dq == "week":
            grouped: dict[str, list[str]] = {}
            for slot in sorted(available.keys()):
                day, time = slot.split(" ")
                grouped.setdefault(day, []).append(time)
            lines = [f"{day}: {', '.join(times)}" for day, times in grouped.items()]
            return _truncate(type_info + "Available slots:\n" + "\n".join(lines))

        day_slots = sorted(s for s in available if s.startswith(dq))
        if not day_slots:
            return type_info + f"No available slots on {dq}. Try 'week' to see all open days."
        times = [s.split(" ")[1] for s in day_slots]
        return type_info + f"Available on {dq}: {', '.join(times)}."

    return check_available_slots


@function_tool(
    description=(
        "Answer a frequently asked question about the clinic. "
        "Valid topics: hours, location, services, pricing, "
        "insurance, cancellation, new_patient."
    )
)
@tool_guard()
async def answer_faq(
    topic: Annotated[
        str,
        (
            "FAQ topic. One of: hours, location, services, pricing, "
            "insurance, cancellation, new_patient."
        ),
    ],
) -> str:
    if not topic or not topic.strip():
        return "Please provide a topic. Valid topics: " + ", ".join(data.FAQS.keys()) + "."
    if len(topic) > 50:
        return "Topic too long. Choose from: " + ", ".join(data.FAQS.keys()) + "."
    answer = data.FAQS.get(topic.strip().lower())
    if not answer:
        valid = ", ".join(data.FAQS.keys())
        return f"No FAQ found for '{topic}'. Valid topics: {valid}."
    return _truncate(answer)


def make_book_appointment(user_id: str, db: Session):
    """Return a book_appointment tool bound to user_id and db session."""

    @function_tool(
        description=(
            "Book an appointment for a caller. "
            "Requires: caller_name, caller_phone, slot ('YYYY-MM-DD HH:MM'), "
            "and appointment_type (initial_consultation, follow_up, peptide_review, lab_review). "
            "Always confirm the slot is available with check_available_slots first."
        )
    )
    @tool_guard()
    async def book_appointment(
        caller_name: Annotated[str, "Full name of the caller"],
        caller_phone: Annotated[str, "Caller's phone number"],
        slot: Annotated[str, "Appointment slot in 'YYYY-MM-DD HH:MM' format"],
        appointment_type: Annotated[
            str,
            "Type of appointment: initial_consultation, follow_up, peptide_review, or lab_review",
        ],
    ) -> str:
        caller_name = caller_name.strip()
        caller_phone = caller_phone.strip()
        slot = slot.strip()
        appointment_type = appointment_type.strip()

        if len(caller_name) < 2 or len(caller_name) > 100:
            return "Caller name must be between 2 and 100 characters."
        if any(ord(c) < 32 for c in caller_name):
            return "Caller name contains invalid characters."

        if not _PHONE_RE.match(caller_phone):
            return (
                "Invalid phone number. Use digits, spaces, hyphens, parentheses, "
                "or a plus sign (7–25 characters)."
            )

        if not _SLOT_RE.match(slot):
            return "Slot must be in 'YYYY-MM-DD HH:MM' format (e.g. '2025-09-10 09:00')."

        if appointment_type not in data.APPOINTMENT_TYPES:
            valid = ", ".join(data.APPOINTMENT_TYPES.keys())
            return f"Unknown appointment type '{appointment_type}'. Valid types: {valid}."

        if slot not in data.AVAILABLE_SLOTS:
            return (
                f"Slot '{slot}' not recognised. Use format 'YYYY-MM-DD HH:MM' "
                "and confirm availability with check_available_slots first."
            )

        from models import Appointment
        already_booked = db.query(Appointment).filter(Appointment.slot == slot).first()
        if already_booked:
            return f"Slot '{slot}' is already booked. Please choose another time."

        booking_id = str(_uuid.uuid4())
        display_id = booking_id[:8].upper()
        appt_type = data.APPOINTMENT_TYPES[appointment_type]

        appointment = Appointment(
            id=booking_id,
            user_id=user_id,
            caller_name=caller_name,
            caller_phone=caller_phone,
            slot=slot,
            appointment_type=appointment_type,
            label=appt_type["label"],
            duration_min=appt_type["duration_min"],
            price=appt_type["price"],
        )
        try:
            db.add(appointment)
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Failed to commit booking for slot %s", slot)
            return "Failed to save your appointment due to a database error. Please try again."

        return (
            f"Appointment confirmed! Booking ID: {display_id}. "
            f"{caller_name} is booked for a {appt_type['label']} "
            f"on {slot} ({appt_type['duration_min']} min, ${appt_type['price']}). "
            "Please remind them to arrive 15 minutes early if it's their first visit."
        )

    return book_appointment


def make_cancel_appointment(user_id: str, db: Session):
    """Return a cancel_appointment tool bound to user_id and db session."""

    @function_tool(
        description=(
            "Cancel an existing appointment by its booking ID. "
            "The caller can only cancel their own appointments."
        )
    )
    @tool_guard()
    async def cancel_appointment(
        appointment_id: Annotated[str, "The full booking ID (UUID) of the appointment to cancel"],
    ) -> str:
        appointment_id = appointment_id.strip()
        if not _APPT_ID_RE.match(appointment_id):
            return (
                "Invalid appointment ID format. Provide the 8-character display ID "
                "or the full UUID from your booking confirmation."
            )

        from models import Appointment

        # Support both 8-char display ID prefix and full UUID
        if len(appointment_id) == 8:
            appointment = (
                db.query(Appointment)
                .filter(Appointment.id.like(f"{appointment_id.lower()}%"))
                .first()
            )
        else:
            appointment = db.query(Appointment).filter(Appointment.id == appointment_id.lower()).first()

        if not appointment:
            return f"No appointment found with ID '{appointment_id}'."

        if appointment.user_id != user_id:
            return "You are not authorised to cancel that appointment."

        try:
            db.delete(appointment)
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Failed to cancel appointment %s", appointment_id)
            return "Failed to cancel your appointment due to a database error. Please try again."

        return f"Appointment {appointment_id.upper()} has been cancelled."

    return cancel_appointment


def make_get_appointments(user_id: str, db: Session):
    """Return a get_appointments tool bound to user_id and db session."""

    @function_tool(
        description="List all upcoming appointments for the current caller."
    )
    @tool_guard()
    async def get_appointments() -> str:
        from models import Appointment

        appointments = db.query(Appointment).filter(Appointment.user_id == user_id).all()
        if not appointments:
            return "You have no upcoming appointments."
        lines = [
            f"ID: {a.id[:8].upper()} | {a.label} on {a.slot} | {a.caller_name} ({a.caller_phone})"
            for a in appointments
        ]
        return _truncate("Your appointments:\n" + "\n".join(lines))

    return get_appointments
