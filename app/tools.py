"""Tool functions for Groq function-calling and their matching JSON schemas."""

from app.orders import get_order, compute_policy_flags


def get_order_details(order_id: str) -> dict:
    """Look up an order and return its details plus code-computed policy flags.

    The LLM calls this tool whenever a customer mentions an order ID.
    Policy flags (is_cancellable, is_returnable) are computed here in Python
    so the LLM cannot be prompted into overriding them.
    """
    order = get_order(order_id)

    if order is None:
        return {
            "found": False,
            "order_id": order_id,
            "message": "Order not found in database.",
        }

    flags = compute_policy_flags(order)

    return {
        "found": True,
        "order_id": order.order_id,
        "customer": order.customer,
        "product": order.product,
        "value_inr": order.value,
        "status": order.status,
        "notes": order.notes,
        "is_cancellable": flags["is_cancellable"],
        "is_returnable": flags["is_returnable"],
    }


# The tool registry maps tool names to their Python callables.
# When the LLM returns a tool_call, we look up the name here and run it.
TOOL_FUNCTIONS: dict[str, callable] = {
    "get_order_details": get_order_details,
}


# Groq/OpenAI-compatible tool schema.
# This is exactly the JSON structure passed to the `tools` parameter in the API call.
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_order_details",
            "description": (
                "Look up a customer's order by order ID. "
                "Returns order status, product, shipping notes, "
                "and policy flags: is_cancellable and is_returnable. "
                "Call this whenever the customer mentions an order ID."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": (
                            "The order ID spoken or typed by the customer, "
                            "e.g. 'ORD-101', 'ord 101', 'ORD101', or just '101'."
                        ),
                    }
                },
                "required": ["order_id"],
            },
        },
    }
]
