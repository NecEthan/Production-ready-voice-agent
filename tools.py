import uuid
from typing import Annotated

from livekit.agents import function_tool

import data


@function_tool(
    description=(
        "Check peptide inventory. Pass a peptide name (e.g. 'BPC-157') to get "
        "details on a specific peptide, or pass a health goal / symptom "
        "(e.g. 'fat loss', 'sleep', 'healing') to find all matching peptides in stock."
    )
)
async def check_peptide_stock(
    query: Annotated[str, "Peptide name or health goal/symptom to search for"],
) -> str:
    q = query.lower().strip()

    if q in ("all", "list", "everything", "inventory", "stock", "what do you have"):
        in_stock = [
            f"{name} (${item['price']}/unit)"
            for name, item in data.PEPTIDE_STOCK.items()
            if item["quantity"] > 0
        ]
        return "In stock: " + ", ".join(in_stock) + "." if in_stock else "No peptides currently in stock."

    for name, item in data.PEPTIDE_STOCK.items():
        if name.lower() == q:
            status = f"{item['quantity']} {item['unit']}" if item["quantity"] > 0 else "OUT OF STOCK"
            return (
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
        return f"Peptides matching '{query}':\n" + "\n".join(matches)

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
    async def check_available_slots(
        query: Annotated[
            str,
            "Date 'YYYY-MM-DD', 'next', or 'week'. Optionally prefix with appointment type, e.g. 'follow_up 2025-09-10'.",
        ],
    ) -> str:
        parts = query.strip().lower().split()

        appt_type = None
        date_query = query.strip()
        for key in data.APPOINTMENT_TYPES:
            if parts[0] == key:
                appt_type = key
                date_query = " ".join(parts[1:]) if len(parts) > 1 else "week"
                break

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
            return type_info + "Available slots:\n" + "\n".join(lines)

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
async def answer_faq(
    topic: Annotated[
        str,
        (
            "FAQ topic. One of: hours, location, services, pricing, "
            "insurance, cancellation, new_patient."
        ),
    ],
) -> str:
    answer = data.FAQS.get(topic)
    if not answer:
        valid = ", ".join(data.FAQS.keys())
        return f"No FAQ found for '{topic}'. Valid topics: {valid}."
    return answer


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
    async def book_appointment(
        caller_name: Annotated[str, "Full name of the caller"],
        caller_phone: Annotated[str, "Caller's phone number"],
        slot: Annotated[str, "Appointment slot in 'YYYY-MM-DD HH:MM' format"],
        appointment_type: Annotated[
            str,
            "Type of appointment: initial_consultation, follow_up, peptide_review, or lab_review",
        ],
    ) -> str:
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

        booking_id = str(uuid.uuid4())
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
        db.add(appointment)
        db.commit()

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
    async def cancel_appointment(
        appointment_id: Annotated[str, "The full booking ID (UUID) of the appointment to cancel"],
    ) -> str:
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

        db.delete(appointment)
        db.commit()
        return f"Appointment {appointment_id.upper()} has been cancelled."

    return cancel_appointment


def make_get_appointments(user_id: str, db: Session):
    """Return a get_appointments tool bound to user_id and db session."""

    @function_tool(
        description="List all upcoming appointments for the current caller."
    )
    async def get_appointments() -> str:
        from models import Appointment

        appointments = db.query(Appointment).filter(Appointment.user_id == user_id).all()
        if not appointments:
            return "You have no upcoming appointments."
        lines = [
            f"ID: {a.id[:8].upper()} | {a.label} on {a.slot} | {a.caller_name} ({a.caller_phone})"
            for a in appointments
        ]
        return "Your appointments:\n" + "\n".join(lines)

    return get_appointments
