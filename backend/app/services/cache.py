import json
import logging
import redis.asyncio as redis
from redis.exceptions import RedisError
from typing import Dict, Any

from app.config import settings
from app.services.reservations import calculate_total_revenue

logger = logging.getLogger(__name__)
redis_client = redis.Redis.from_url(settings.redis_url)


async def get_revenue_summary(
    property_id: str, tenant_id: str, month: int = None, year: int = None,
) -> Dict[str, Any]:
    if not tenant_id:
        raise ValueError("Tenant is required")
    # Versioned namespace ignores old, tenant-unsafe entries. JSON avoids delimiter collisions.
    identity = dict(tenant_id=tenant_id, property_id=property_id, month=month, year=year)
    cache_key = "revenue:v2:" + json.dumps(identity, sort_keys=True)
    try:
        cached = await redis_client.get(cache_key)
        if cached:
            result = json.loads(cached)
            if isinstance(result, dict) and all(result.get(k) == v for k, v in identity.items()):
                if isinstance(result.get("total"), str) and "currency" in result and "count" in result:
                    return result
    except (RedisError, ValueError, TypeError):
        logger.warning("Revenue cache unavailable or invalid; querying database")

    result = await calculate_total_revenue(property_id, tenant_id, month, year)
    try:
        await redis_client.setex(cache_key, 300, json.dumps(result))
    except RedisError:
        logger.warning("Unable to cache revenue summary")
    return result
