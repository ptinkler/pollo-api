"""Control VPN status and settings through Gluetun's API.

The routes expose status, restart and server-country controls.
control server.

Docs: https://github.com/qdm12/gluetun-wiki/blob/main/setup/advanced/control-server.md
"""

import logging
import os
import time
from typing import cast

import requests
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from web.types import JsonValue
from web.users import require_admin

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/vpn")

GLUETUN_API = "http://127.0.0.1:8000"
GLUETUN_API_KEY = os.getenv("GLUETUN_API_KEY", "")
_GLUETUN_HEADERS = {"X-API-Key": GLUETUN_API_KEY} if GLUETUN_API_KEY else {}

ALLOWED_VPN_COUNTRIES = [
    "United States",
    "United Kingdom",
    "Canada",
    "Australia",
    "Germany",
    "France",
    "Netherlands",
    "Japan",
    "Singapore",
    "Switzerland",
    "Sweden",
    "Brazil",
    "India",
    "South Korea",
    "Italy",
    "Spain",
    "Norway",
    "Denmark",
    "Ireland",
]


class VpnCountryRequest(BaseModel):
    """Country requested for the VPN server."""

    country: str


def _gluetun_get(path: str, timeout: int = 3) -> requests.Response:
    return requests.get(f"{GLUETUN_API}{path}", headers=_GLUETUN_HEADERS, timeout=timeout)


def _gluetun_put(path: str, body: dict[str, JsonValue], timeout: int = 5) -> requests.Response:
    return requests.put(f"{GLUETUN_API}{path}", json=body, headers=_GLUETUN_HEADERS, timeout=timeout)


def _gluetun_json(
    path: str,
    if_not_ok: dict[str, JsonValue],
    if_unreachable: dict[str, JsonValue],
    timeout: int = 3,
) -> dict[str, JsonValue]:
    """A Gluetun GET's JSON, or a stand-in when it fails or can't be reached."""
    try:
        r = _gluetun_get(path, timeout=timeout)
    except Exception:  # noqa: BLE001 — any connection failure means unreachable
        return if_unreachable
    data = r.json()
    return cast("dict[str, JsonValue]", data) if r.ok and isinstance(data, dict) else if_not_ok


def _egress_ip() -> str | None:
    """The app's own egress IP, used when the control server reports none.

    In vpn mode the app shares gluetun's network, so this is the tunnel's exit IP.
    """
    for url in ("https://api.ipify.org", "https://icanhazip.com"):
        try:
            r = requests.get(url, timeout=6)
            if r.ok and r.text.strip():
                return r.text.strip()
        except Exception:
            log.debug("egress-IP lookup failed at %s; trying the next service", url, exc_info=True)
            continue
    return None


@router.get("/status")
def vpn_status(_admin=Depends(require_admin)) -> dict[str, JsonValue]:
    """Current VPN status, public IP, and server country from Gluetun."""
    # Gluetun's /v1/publicip/ip returns the tunnel's exit IP under "public_ip"
    # (older builds used "ip"); normalise to {ip, country} for the UI.
    raw = _gluetun_json("/v1/publicip/ip", {}, {}, timeout=10)
    ip = raw.get("public_ip") or raw.get("ip")
    country = raw.get("country")
    if not ip:
        ip = _egress_ip()
    settings = _gluetun_json("/v1/vpn/settings", {}, {})
    # The public IP lookup's country stands in when settings name none
    countries = settings.get("server_countries") or ([country] if country else [])
    return {
        "vpn": _gluetun_json("/v1/vpn/status", {"status": "unknown"}, {"status": "unreachable"}),
        "public_ip": {"ip": ip, "country": country},
        "server_countries": countries,
    }


@router.post("/restart")
def vpn_restart(_admin=Depends(require_admin)) -> dict[str, bool | str]:
    """Restart the VPN tunnel by cycling Gluetun's status off then on."""
    try:
        _gluetun_put("/v1/vpn/status", {"status": "stopped"})
        time.sleep(2)
        r = _gluetun_put("/v1/vpn/status", {"status": "running"})
    except Exception as e:
        raise HTTPException(502, detail=f"Cannot reach Gluetun control server: {e}") from e
    if r.ok:
        return {"ok": True, "message": "VPN tunnel restarted — new IP in ~10s"}
    return {"ok": False, "message": f"Gluetun responded {r.status_code}"}


@router.put("/country")
def vpn_change_country(data: VpnCountryRequest, _admin=Depends(require_admin)) -> dict[str, bool | str]:
    """Change VPN server country. Body: {"country": "United Kingdom"}."""
    country = data.country.strip()
    if not country:
        raise HTTPException(400, detail="Missing 'country' field")
    if country not in ALLOWED_VPN_COUNTRIES:
        raise HTTPException(400, detail=f"Invalid country: '{country}'. Allowed: {', '.join(ALLOWED_VPN_COUNTRIES)}")
    try:
        r = _gluetun_put("/v1/vpn/settings", {"server_countries": [country]})
    except Exception as e:
        raise HTTPException(502, detail=f"Cannot reach Gluetun control server: {e}") from e
    if not r.ok:
        return {"ok": False, "message": f"Gluetun responded {r.status_code}: {r.text}"}
    return {"ok": True, "message": f"Switching to {country} — new IP in ~10s"}


@router.get("/countries")
def vpn_countries(_admin=Depends(require_admin)) -> dict[str, list[str]]:
    """The allowed VPN server countries."""
    return {"countries": ALLOWED_VPN_COUNTRIES}
