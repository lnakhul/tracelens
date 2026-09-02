"""Deterministic upstream API used to demonstrate TraceLens locally."""

from __future__ import annotations

import argparse
import asyncio

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel


class OrderRequest(BaseModel):
    """Minimal order request accepted by the demo upstream service."""

    customer_id: str | None = None
    product_id: str


def create_demo_app() -> FastAPI:
    """Create an upstream API with deterministic success, error, and latency cases."""

    app = FastAPI(title="TraceLens Demo API", version="1.0.0")

    @app.get("/users/{user_id}")
    async def get_user(user_id: int) -> dict[str, object]:
        return {"id": user_id, "name": f"Developer {user_id}", "plan": "pro"}

    @app.post("/orders", status_code=201)
    async def create_order(order: OrderRequest) -> dict[str, str]:
        if not order.customer_id:
            raise HTTPException(
                status_code=500,
                detail="OrderService requires customer_id before creating an order",
            )
        return {"order_id": "ord_demo_001", "status": "created"}

    @app.get("/reports/daily")
    async def get_daily_report(slow: bool = False) -> dict[str, object]:
        await asyncio.sleep(0.7 if slow else 0.08)
        return {"report": "daily", "orders": 42, "slow": slow}

    return app


def main(arguments: list[str] | None = None) -> None:
    """Run the demo upstream API."""

    import uvicorn

    parser = argparse.ArgumentParser(description="Run the TraceLens demo upstream API.")
    parser.add_argument(
        "--bind-host",
        default="127.0.0.1",
        choices=["127.0.0.1", "0.0.0.0"],
        help="Listening address; use 0.0.0.0 only inside a container",
    )
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(arguments)
    uvicorn.run(create_demo_app(), host=args.bind_host, port=args.port)


if __name__ == "__main__":
    main()
