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

    # List all in stock
    if q in ("all", "list", "everything", "inventory", "stock", "what do you have"):
        in_stock = [
            f"{name} (${item['price']}/unit)"
            for name, item in data.PEPTIDE_STOCK.items()
            if item["quantity"] > 0
        ]
        return "In stock: " + ", ".join(in_stock) + "." if in_stock else "No peptides currently in stock."

    # Exact name match
    for name, item in data.PEPTIDE_STOCK.items():
        if name.lower() == q:
            status = f"{item['quantity']} {item['unit']}" if item["quantity"] > 0 else "OUT OF STOCK"
            return (
                f"{name}: {item['description']} "
                f"| In stock: {status} | ${item['price']} per unit."
            )

    # Goal/keyword search
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
