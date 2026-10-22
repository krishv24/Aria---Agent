"""Mock order database and lookup helpers for Aura Skincare."""

from pydantic import BaseModel, Field


class Order(BaseModel):
    """Represents a customer order in Aura Skincare's database."""

    order_id: str = Field(description="Unique order identifier, e.g. ORD-101")
    customer: str = Field(description="Customer's full name")
    product: str = Field(description="Product name or bundle purchased")
    value: int = Field(description="Total order value in Indian Rupees (₹)")
    status: str = Field(description="Fulfillment status")
    notes: str = Field(description="Shipping carrier, tracking, or delivery notes")


# Mock database matching the DataStraw assessment specification exactly
ORDERS_DATABASE: dict[str, Order] = {
    "ORD-101": Order(
        order_id="ORD-101",
        customer="Priya Sharma",
        product="Vitamin C Serum (30ml)",
        value=699,
        status="Out for Delivery",
        notes="BlueDart BD-982103, expected by 6 PM today",
    ),
    "ORD-102": Order(
        order_id="ORD-102",
        customer="Rahul Verma",
        product="Hydrating Sunscreen SPF 50",
        value=499,
        status="Delivered",
        notes="Delhivery DL-441029, delivered 14 days ago",
    ),
    "ORD-103": Order(
        order_id="ORD-103",
        customer="Ananya Patel",
        product="Green Tea Face Wash + Toner",
        value=850,
        status="Processing",
        notes="Ordered 3 hours ago, eligible for cancellation",
    ),
}


def get_all_orders() -> list[Order]:
    """Retrieve all orders from the database to display in the UI helper panel."""
    return list(ORDERS_DATABASE.values())


def get_order(order_id: str) -> Order | None:
    """Retrieve an order by ID, normalizing variations in case or spacing."""
    # Normalize speech variations like 'ord 101' to 'ORD-101'
    clean_id = order_id.strip().upper().replace(" ", "-").replace("_", "-")
    if clean_id.isdigit():
        clean_id = f"ORD-{clean_id}"
    return ORDERS_DATABASE.get(clean_id)
