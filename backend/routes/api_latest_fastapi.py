"""
FastAPI router for /api/latest and /api/history.

Mirrors Flask behavior from backend/routes/api_latest.py:
- /api/latest: read Redis -> cold start update_data() -> DB fallback
- /api/history: read history_payload:{period} from Redis -> DB fallback
"""
import asyncio
import json
import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.db_models import (
    DbModelMeasurement,
    DbModelPollutant,
    DbModelStation,
)
from backend.dependencies import get_db, get_redis

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["api"])


# =============================================================================
# /api/latest
# =============================================================================

async def _build_latest_from_db(db: AsyncSession) -> dict:
    """
    Build latest payload from DB.
    Returns: {station_id: {info: {...}, measurements_list: [{...}]}}
    """
    result = await db.execute(select(func.max(DbModelMeasurement.measured_at)))
    latest_ts = result.scalar_one_or_none()

    if latest_ts is None:
        return {}

    result = await db.execute(
        select(DbModelStation, DbModelMeasurement, DbModelPollutant)
        .join(DbModelMeasurement, DbModelMeasurement.station_id == DbModelStation.id)
        .join(DbModelPollutant, DbModelPollutant.id == DbModelMeasurement.pollutant_id)
        .where(DbModelMeasurement.measured_at == latest_ts)
    )
    rows = result.all()

    payload: dict = {}
    for station, measurement, pollutant in rows:
        station_key = station.station_id
        if station_key not in payload:
            payload[station_key] = {
                "info": {
                    "station_id": station.station_id,
                    "station_name": station.station_name,
                    "latitude": station.latitude,
                    "longitude": station.longitude,
                    "d96_easting": station.d96_easting,
                    "d96_northing": station.d96_northing,
                    "elevation_meters": station.elevation_meters,
                },
                "measurements_list": [
                    {
                        "station_id": station.station_id,
                        "station_name": station.station_name,
                        "time_to": latest_ts.isoformat(),
                    }
                ],
            }
        payload[station_key]["measurements_list"][0][pollutant.name] = measurement.value

    return payload


@router.get("/latest")
async def get_latest_data(
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis_client=Depends(get_redis),
):
    cache_only = request.query_params.get("cache_only", "0") in ("1", "true", "True", "yes")

    # 1. Try Redis first
    latest_data = None
    try:
        latest_data = await redis_client.get("latest_merged_data")
    except Exception as e:
        logger.exception(f"Failed to get latest_merged_data from redis: {e}")

    # 2. Cold start: call update_data() in thread (it is sync) if redis has no data
    if latest_data is None and not cache_only:
        try:
            from backend.data.update_data import update_data
            await asyncio.to_thread(update_data)
        except Exception as e:
            logger.exception(f"update_data() failed during /api/latest refresh: {e}")

        try:
            latest_data = await redis_client.get("latest_merged_data")
        except Exception as e:
            logger.exception(f"Failed to get latest_merged_data from redis (retry): {e}")

    # 3. Final fallback: build from DB
    if latest_data is None and not cache_only:
        try:
            payload = await _build_latest_from_db(db)
            if payload:
                serialized = json.dumps(payload, ensure_ascii=False, default=str)
                await redis_client.set("latest_merged_data", serialized)
                latest_data = serialized
        except Exception as e:
            logger.exception(f"DB fallback failed in /api/latest: {e}")

    if latest_data:
        if isinstance(latest_data, bytes):
            latest_data = latest_data.decode("utf-8")
        return Response(content=latest_data, media_type="application/json")

    return JSONResponse(status_code=503, content={"error": "No data available yet"})


# =============================================================================
# /api/history
# =============================================================================

@router.get("/history")
async def get_history_data(
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis_client=Depends(get_redis),
):
    period = request.query_params.get("period", "day").lower()
    station_id = request.query_params.get("station_id")

    if period not in {"day", "week", "month", "year"}:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid period. Use day|week|month|year"},
        )

    # 1. Try Redis: history_payload:{period}
    cache_key = f"history_payload:{period}"
    payload = None
    try:
        cached = await redis_client.get(cache_key)
        if cached:
            payload = json.loads(cached)
    except Exception as e:
        logger.exception(f"Failed to read {cache_key} from redis: {e}")

    # 2. Fallback: rebuild from DB (delegated to async history builder)
    if payload is None:
        try:
            from backend.utils.history_cache import build_history_payload_from_db_async
            payload = await build_history_payload_from_db_async(db, period)
        except Exception as e:
            logger.exception(f"Failed to build history payload from DB: {e}")

    if payload is None:
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to load history"},
        )

    # Optional: filter by station_id if provided
    if station_id and "stations" in payload:
        filtered = {station_id: payload["stations"].get(station_id, {})}
        payload = {**payload, "stations": filtered}

    return Response(
        content=json.dumps(payload, ensure_ascii=False, default=str),
        media_type="application/json",
        headers={
            "Cache-Control": (
                "public, max-age=30, stale-while-revalidate=60"
                if period == "day"
                else "public, max-age=120, stale-while-revalidate=300"
            ),
            "Vary": "Accept-Encoding",
        },
    )