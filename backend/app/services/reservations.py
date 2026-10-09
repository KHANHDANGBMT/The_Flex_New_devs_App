from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict
from zoneinfo import ZoneInfo

from sqlalchemy import text

from app.core.database_pool import db_pool


class PropertyNotFoundError(Exception):
    pass


class MixedCurrencyError(Exception):
    pass


def month_bounds(year: int, month: int, property_timezone: str):
    """Half-open local calendar month, converted to UTC (including DST)."""
    zone = ZoneInfo(property_timezone)
    start = datetime(year, month, 1, tzinfo=zone)
    end = datetime(year + (month == 12), month % 12 + 1, 1, tzinfo=zone)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


async def _summary(session, property_id, tenant_id, month=None, year=None):
    if not tenant_id:
        raise ValueError("Tenant is required")
    if (month is None) != (year is None):
        raise ValueError("Month and year must be supplied together")
    result = await session.execute(text("""
        SELECT timezone FROM properties
        WHERE id = :property_id AND tenant_id = :tenant_id
    """), {"property_id": property_id, "tenant_id": tenant_id})
    property_row = result.fetchone()
    if property_row is None:
        raise PropertyNotFoundError()

    params = {"property_id": property_id, "tenant_id": tenant_id}
    period_filter = ""
    if month is not None:
        params["start"], params["end"] = month_bounds(year, month, property_row.timezone)
        period_filter = "AND check_in_date >= :start AND check_in_date < :end"
    result = await session.execute(text(f"""
        SELECT currency, SUM(total_amount) AS total, COUNT(*) AS count
        FROM reservations
        WHERE property_id = :property_id AND tenant_id = :tenant_id
        {period_filter}
        GROUP BY currency
    """), params)
    rows = result.fetchall()
    # No exchange-rate policy exists; never add different currencies together.
    if len(rows) > 1 or (rows and not rows[0].currency):
        raise MixedCurrencyError()
    total = Decimal(rows[0].total) if rows else Decimal("0")
    return {
        "property_id": property_id,
        "tenant_id": tenant_id,
        "month": month,
        "year": year,
        "total": str(total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
        "currency": rows[0].currency if rows else None,
        "count": rows[0].count if rows else 0,
    }


async def calculate_total_revenue(
    property_id: str, tenant_id: str, month: int = None, year: int = None,
    db_session=None,
) -> Dict[str, Any]:
    if db_session is not None:
        return await _summary(db_session, property_id, tenant_id, month, year)
    await db_pool.initialize()
    async with db_pool.get_session() as session:
        return await _summary(session, property_id, tenant_id, month, year)


async def calculate_monthly_revenue(
    property_id: str, month: int, year: int, tenant_id: str, db_session=None,
) -> Decimal:
    result = await calculate_total_revenue(property_id, tenant_id, month, year, db_session)
    return Decimal(result["total"])
