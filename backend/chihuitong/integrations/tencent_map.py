import io
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal, InvalidOperation

from django.conf import settings
from PIL import Image, UnidentifiedImageError

from chihuitong.errors import BusinessError, require

from .safe_json import NoRedirect, request_json


def static_map(latitude, longitude, zoom):
    """Fixed-origin raster only: no third-party JavaScript in authenticated backends."""
    require(
        settings.TENCENT_MAP_KEY,
        "map_not_configured",
        "地图服务尚未配置，请联系平台配置后核对位置",
        503,
    )
    query = urllib.parse.urlencode(
        {
            "key": settings.TENCENT_MAP_KEY,
            "center": f"{latitude},{longitude}",
            "zoom": zoom,
            "size": "600*360",
            "scale": 1,
            "format": "png",
        }
    )
    request = urllib.request.Request(
        "https://apis.map.qq.com/ws/staticmap/v2/?" + query,
        headers={"Accept": "image/png"},
    )
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        with opener.open(request, timeout=8) as response:
            raw = response.read(2 * 1024 * 1024 + 1)
        require(len(raw) <= 2 * 1024 * 1024, "map_response", "地图图片返回过大", 503)
        with Image.open(io.BytesIO(raw)) as picture:
            require(
                picture.format == "PNG" and picture.size == (600, 360),
                "map_response",
                "地图图片格式异常",
                503,
            )
            picture.verify()
    except (
        urllib.error.URLError,
        TimeoutError,
        OSError,
        UnidentifiedImageError,
        ValueError,
    ) as exc:
        raise BusinessError("map_unavailable", "地图暂不可用，请稍后重试", 503) from exc
    return raw


def geocode(address):
    key = settings.TENCENT_MAP_KEY
    require(
        isinstance(key, str) and key,
        "map_not_configured",
        "地址定位服务尚未配置，可在地图人工选点后提交审核",
        503,
    )
    result = request_json(
        "apis.map.qq.com",
        "/ws/geocoder/v1/",
        query={"key": key, "address": address, "output": "json"},
    )
    require(
        type(result.get("status")) is int and result["status"] == 0,
        "geocode_failed",
        "地址未能解析，请完善省市区及门牌信息或在地图选点",
        409,
    )
    item = result.get("result")
    require(
        isinstance(item, dict) and isinstance(item.get("location"), dict),
        "geocode_response",
        "定位结果格式异常",
        503,
    )
    try:
        lng, lat = (
            Decimal(str(item["location"].get("lng"))),
            Decimal(str(item["location"].get("lat"))),
        )
        require(
            lng.is_finite()
            and lat.is_finite()
            and -180 <= lng <= 180
            and -90 <= lat <= 90
            and (lng or lat),
            "geocode_response",
            "定位结果坐标不合法",
            503,
        )
    except (InvalidOperation, ValueError) as exc:
        raise BusinessError("geocode_response", "定位结果坐标不合法", 503) from exc
    level, reliability = item.get("level"), item.get("reliability")
    require(
        (level is None or type(level) is int and 1 <= level <= 11)
        and type(reliability) is int
        and 1 <= reliability <= 10,
        "geocode_response",
        "定位精度信息不合法",
        503,
    )
    return {
        "longitude": str(lng),
        "latitude": str(lat),
        "coordinate_system": "GCJ-02",
        "address_snapshot": address,
        "source": "tencent",
        "status": "unconfirmed",
        "precision": level,
        "reliability": reliability,
        "needs_manual_adjustment": level is None or level < 9 or reliability < 7,
        "requires_map_confirmation": True,
    }
