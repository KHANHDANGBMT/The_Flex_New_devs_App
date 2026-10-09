"""Regression cases; intentionally not executed during the no-run code review."""
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from redis.exceptions import ConnectionError

from app.services import cache, reservations
from app.core.tenant_resolver import TenantResolver


class RevenueTests(unittest.IsolatedAsyncioTestCase):
    def test_local_month_and_dst(self):
        start, end = reservations.month_bounds(2024, 3, "Europe/Paris")
        self.assertEqual(start, datetime(2024, 2, 29, 23, tzinfo=timezone.utc))
        self.assertEqual(end, datetime(2024, 3, 31, 22, tzinfo=timezone.utc))
        start, end = reservations.month_bounds(2024, 3, "America/New_York")
        self.assertEqual(start, datetime(2024, 3, 1, 5, tzinfo=timezone.utc))
        self.assertEqual(end, datetime(2024, 4, 1, 4, tzinfo=timezone.utc))
        _, end = reservations.month_bounds(2024, 12, "UTC")
        self.assertEqual(end, datetime(2025, 1, 1, tzinfo=timezone.utc))

    def session(self, rows, exists=True):
        property_result = Mock()
        property_result.fetchone.return_value = SimpleNamespace(timezone="Europe/Paris") if exists else None
        revenue_result = Mock()
        revenue_result.fetchall.return_value = rows
        return SimpleNamespace(execute=AsyncMock(side_effect=[property_result, revenue_result]))

    async def test_decimal_rounding_after_sum_and_scoped_query(self):
        for amount, expected in [("2250.000", "2250.00"), ("1.005", "1.01"), ("-1.005", "-1.01")]:
            session = self.session([SimpleNamespace(total=Decimal(amount), currency="USD", count=4)])
            result = await reservations.calculate_total_revenue("prop-001", "tenant-a", 3, 2024, session)
            self.assertEqual(result["total"], expected)
            query, params = session.execute.call_args.args
            self.assertIn("tenant_id = :tenant_id", str(query))
            self.assertIn("check_in_date < :end", str(query))
            self.assertEqual(params["tenant_id"], "tenant-a")
            self.assertEqual(params["start"], datetime(2024, 2, 29, 23, tzinfo=timezone.utc))

    async def test_unknown_property_and_empty_owned_property(self):
        session = self.session([], exists=False)
        with self.assertRaises(reservations.PropertyNotFoundError):
            await reservations.calculate_total_revenue("other-property", "tenant-a", db_session=session)
        self.assertEqual(session.execute.await_count, 1)
        result = await reservations.calculate_total_revenue("prop-001", "tenant-b", db_session=self.session([]))
        self.assertEqual(result["total"], "0.00")
        self.assertEqual(result["count"], 0)
        self.assertIsNone(result["currency"])

    async def test_mixed_currency_rejected(self):
        rows = [SimpleNamespace(total=Decimal("10"), currency=currency, count=1) for currency in ("USD", "EUR")]
        with self.assertRaises(reservations.MixedCurrencyError):
            await reservations.calculate_total_revenue("prop-001", "tenant-a", db_session=self.session(rows))

    async def test_database_failure_is_not_mock_revenue(self):
        session = SimpleNamespace(execute=AsyncMock(side_effect=RuntimeError("offline")))
        with self.assertRaises(RuntimeError):
            await reservations.calculate_total_revenue("prop-001", "tenant-a", db_session=session)

    async def test_unknown_identity_has_no_default_tenant(self):
        self.assertIsNone(await TenantResolver.resolve_tenant_id("unknown", "unknown@example.com"))

    async def test_cache_separates_tenant_and_period(self):
        entries = {}
        fake_redis = SimpleNamespace(get=AsyncMock(side_effect=lambda key: entries.get(key)), setex=AsyncMock())
        async def save(key, ttl, value):
            entries[key] = value
        fake_redis.setex.side_effect = save
        async def summary(property_id, tenant_id, month, year):
            return dict(property_id=property_id, tenant_id=tenant_id, month=month, year=year,
                        total="2250.00" if tenant_id == "tenant-a" else "0.00", currency="USD", count=4)
        calculate = AsyncMock(side_effect=summary)
        with patch.object(cache, "redis_client", fake_redis), patch.object(cache, "calculate_total_revenue", calculate):
            a = await cache.get_revenue_summary("prop-001", "tenant-a", 3, 2024)
            b = await cache.get_revenue_summary("prop-001", "tenant-b", 3, 2024)
            await cache.get_revenue_summary("prop-001", "tenant-a", 4, 2024)
            self.assertEqual(await cache.get_revenue_summary("prop-001", "tenant-a", 3, 2024), a)
            self.assertNotEqual(a["total"], b["total"])
            self.assertEqual(calculate.await_count, 3)

    async def test_cache_failure_falls_back_to_database(self):
        fake_redis = SimpleNamespace(get=AsyncMock(side_effect=ConnectionError()), setex=AsyncMock(side_effect=ConnectionError()))
        calculate = AsyncMock(return_value={"total": "2250.00"})
        with patch.object(cache, "redis_client", fake_redis), patch.object(cache, "calculate_total_revenue", calculate):
            self.assertEqual(await cache.get_revenue_summary("prop-001", "tenant-a", 3, 2024), {"total": "2250.00"})
