"""Fixed-origin JSON transport; never expose remote bodies, request URLs or credentials."""

import json
import urllib.error
import urllib.parse
import urllib.request

from chihuitong.errors import BusinessError, require


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise BusinessError("provider_redirect", "外部服务地址异常", 503)


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "provider_response", "外部服务返回结构异常", 503)
        result[key] = value
    return result


def request_json(host, path, *, query=None, data=None):
    require(host in {"apis.map.qq.com", "api.weixin.qq.com"} and path.startswith("/") and not path.startswith("//") and "?" not in path, "provider_origin", "外部服务配置错误", 503)
    url = "https://" + host + path
    if query:
        url += "?" + urllib.parse.urlencode(query)
    payload = None if data is None else json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()
    request = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json", "Accept": "application/json"}, method="GET" if data is None else "POST")
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        with opener.open(request, timeout=8) as response:
            raw = response.read(1024 * 1024 + 1)
        require(len(raw) <= 1024 * 1024, "provider_response", "外部服务返回过大", 503)
        result = json.loads(raw, object_pairs_hook=unique_pairs)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise BusinessError("provider_unavailable", "外部服务暂不可用，请稍后重试", 503) from exc
    except (ValueError, UnicodeError) as exc:
        raise BusinessError("provider_response", "外部服务返回结构异常", 503) from exc
    require(isinstance(result, dict), "provider_response", "外部服务返回结构异常", 503)
    return result
