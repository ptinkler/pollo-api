"""
VPN control — status, restart and server country, through Gluetun's
control server.

Docs: https://github.com/qdm12/gluetun-wiki/blob/main/setup/advanced/control-server.md
"""

import os
import time
from typing import Any

import requests
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .auth import verify_api_key

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
    country: str


def _gluetun_get(path: str, timeout: int = 3):
    return requests.get(f"{GLUETUN_API}{path}", headers=_GLUETUN_HEADERS, timeout=timeout)


def _gluetun_put(path: str, body: dict, timeout: int = 5):
    return requests.put(f"{GLUETUN_API}{path}", json=body, headers=_GLUETUN_HEADERS, timeout=timeout)


def _gluetun_json(path: str, if_not_ok: Any, if_unreachable: Any, timeout: int = 3) -> Any:
    """A Gluetun GET's JSON, or a stand-in when it fails or can't be reached."""
    try:
        r = _gluetun_get(path, timeout=timeout)
    except Exception:  # noqa: BLE001 — any connection failure means unreachable
        return if_unreachable
    return r.json() if r.ok else if_not_ok


@router.get("/status")
def vpn_status(_api_key: str = Depends(verify_api_key)):
    """Current VPN status, public IP, and server country from Gluetun."""
    public_ip = _gluetun_json("/v1/publicip/ip", {}, {}, timeout=5)
    settings = _gluetun_json("/v1/vpn/settings", {}, {})
    # The public IP lookup's country stands in when settings name none
    countries = settings.get("server_countries") or ([public_ip["country"]] if public_ip.get("country") else [])
    return {
        "vpn": _gluetun_json("/v1/vpn/status", {"status": "unknown"}, {"status": "unreachable"}),
        "public_ip": public_ip,
        "server_countries": countries,
    }


@router.post("/restart")
def vpn_restart(_api_key: str = Depends(verify_api_key)):
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
def vpn_change_country(data: VpnCountryRequest, _api_key: str = Depends(verify_api_key)):
    """Change VPN server country. Body: {"country": "United Kingdom"}"""
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
def vpn_countries():
    """The allowed VPN server countries."""
    return {"countries": ALLOWED_VPN_COUNTRIES}
