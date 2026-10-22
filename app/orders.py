"""Mock order database, lookup helpers, and policy-derived flags for Aura Skincare."""

import re
from pydantic import BaseModel, Field


# How many days after delivery a return is still allowed (from brand policy)
RETURN_WINDOW_DAYS = 7

# Only "Processing" orders can be cancelled (policy rule in code, not just in prompt)
CANCELLABLE_STATUSES = {"Processing"}

# Orders that have left the warehouse cannot be cancelled
NON_CANCELLABLE_STATUSES = {"Shipped", "Out for Delivery", "Delivered"}


class Order(BaseModel):
    """Represents a customer order in Aura Skincare's database."""

    order_id: str = Field(description="Unique order identifier, e.g. ORD-101")
    customer: str = Field(description="Customer's full name")
    product: str = Field(description="Product name or bundle purchased")
    value: int = Field(description="Total order value in Indian Rupees (₹)")
    status: str = Field(description="Fulfillment status")
    notes: str = Field(description="Shipping carrier, tracking, or delivery notes")
    # How many days ago the order was delivered; None if not yet delivered
    delivered_days_ago: int | None = Field(
        default=None,
        description="Days since delivery; used to compute return eligibility"
    )


# Mock database matching the DataStraw assessment specification exactly
ORDERS_DATABASE: dict[str, Order] = {
    "ORD-101": Order(
        order_id="ORD-101",
        customer="Priya Sharma",
        product="Vitamin C Serum (30ml)",
        value=699,
        status="Out for Delivery",
        notes="BlueDart BD-982103, expected by 6 PM today",
        delivered_days_ago=None,
    ),
    "ORD-102": Order(
        order_id="ORD-102",
        customer="Rahul Verma",
        product="Hydrating Sunscreen SPF 50",
        value=499,
        status="Delivered",
        notes="Delhivery DL-441029, delivered 14 days ago",
        delivered_days_ago=14,
    ),
    "ORD-103": Order(
        order_id="ORD-103",
        customer="Ananya Patel",
        product="Green Tea Face Wash + Toner",
        value=850,
        status="Processing",
        notes="Ordered 3 hours ago, eligible for cancellation",
        delivered_days_ago=None,
    ),
}


def normalize_order_id(raw: str) -> str:
    """Convert any spoken or typed variation to the canonical 'ORD-NNN' format.

    Handles:
      'ord 101'  -> 'ORD-101'
      'ORD101'   -> 'ORD-101'
      'ord-101'  -> 'ORD-101'
      '101'      -> 'ORD-101'
    """
    # Strip whitespace, uppercase everything
    s = raw.strip().upper()
    # Extract just the numeric part with a regex so we handle all separators
    match = re.search(r"(\d+)", s)
    if not match:
        # Return as-is so the caller gets a clean not-found rather than a crash
        return s
    number = match.group(1)
    return f"ORD-{number}"


def compute_policy_flags(order: Order) -> dict:
    """Derive is_cancellable and is_returnable from policy constants.

    These flags come from CODE, not from the LLM prompt, so the agent
    cannot be talked into overriding them.
    """
    # Cancellable only while the warehouse hasn't shipped it yet
    is_cancellable = order.status in CANCELLABLE_STATUSES

    # Returnable: must be delivered AND within the 7-day return window
    is_returnable = (
        order.status == "Delivered"
        and order.delivered_days_ago is not None
        and order.delivered_days_ago <= RETURN_WINDOW_DAYS
    )

    return {"is_cancellable": is_cancellable, "is_returnable": is_returnable}


def cancel_order_in_db(order_id: str) -> tuple[bool, str, Order | None]:
    """Attempt to cancel an order in the mock database according to business policy."""
    clean_id = normalize_order_id(order_id)
    order = ORDERS_DATABASE.get(clean_id)
    if not order:
        return False, f"Order {order_id} was not found.", None

    flags = compute_policy_flags(order)
    if not flags["is_cancellable"]:
        return (
            False,
            f"Order {clean_id} cannot be cancelled because its status is '{order.status}'. Only orders in 'Processing' status can be cancelled.",
            order,
        )

    order.status = "Cancelled"
    order.notes = "Cancelled by customer via Aria support"
    return True, f"Order {clean_id} has been successfully cancelled in the database.", order


def reset_orders_db() -> None:
    """Reset the mock database to initial state."""
    global ORDERS_DATABASE
    ORDERS_DATABASE = {
        "ORD-101": Order(
            order_id="ORD-101",
            customer="Priya Sharma",
            product="Vitamin C Serum (30ml)",
            value=699,
            status="Out for Delivery",
            notes="BlueDart BD-982103, expected by 6 PM today",
            delivered_days_ago=None,
        ),
        "ORD-102": Order(
            order_id="ORD-102",
            customer="Rahul Verma",
            product="Hydrating Sunscreen SPF 50",
            value=499,
            status="Delivered",
            notes="Delhivery DL-441029, delivered 14 days ago",
            delivered_days_ago=14,
        ),
        "ORD-103": Order(
            order_id="ORD-103",
            customer="Ananya Patel",
            product="Green Tea Face Wash + Toner",
            value=850,
            status="Processing",
            notes="Ordered 3 hours ago, eligible for cancellation",
            delivered_days_ago=None,
        ),
    }


def get_all_orders() -> list[Order]:
    """Retrieve all orders from the database to display in the UI helper panel."""
    return list(ORDERS_DATABASE.values())


def get_order(order_id: str) -> Order | None:
    """Retrieve an order by its normalized ID."""
    clean_id = normalize_order_id(order_id)
    return ORDERS_DATABASE.get(clean_id)
