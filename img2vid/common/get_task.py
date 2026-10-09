"""
Get task status from the Pollo API.

API Docs: https://docs.pollo.ai/task/get-task-status?playground=open
"""

import requests

from .cloudflare import is_cloudflare_block
from .config import POLLO_API_BASE, POLLO_API_TIMEOUT

# Each result tuple: (status, failMsg, url, credits)
TaskResult = tuple[str, str | None, str | None, int | None]


CLOUDFLARE_MESSAGE = "Cloudflare blocked the request — check your VPN or switch regions."


def get_task_status(task_id: str, api_key: str) -> list[TaskResult]:
    """One result per generation of the task; a single ("error", …) or
    ("cloudflare_blocked", …) result when the status can't be read."""
    url = f"{POLLO_API_BASE}/{task_id}/status"
    response = requests.request("GET", url, headers={"x-api-key": api_key}, timeout=POLLO_API_TIMEOUT)
    if is_cloudflare_block(response):
        return [("cloudflare_blocked", CLOUDFLARE_MESSAGE, None, None)]
    if response.status_code != 200:
        print("Error fetching task status.")
        return [("error", _error_message(response), None, None)]
    try:
        data = response.json().get("data", {})
    except ValueError:
        return [("error", "Invalid JSON response", None, None)]

    # Generations come under "generations" or, in another response shape, "result"
    generations = data.get("generations") or data.get("result") or []
    if not generations:
        print("No generations found in the response.")
        return [("error", "No generations found.", None, None)]
    results = [
        (gen.get("status"), gen.get("failMsg"), gen.get("url") or gen.get("videoUrl"), _credit(gen.get("credit")))
        for gen in generations
    ]
    # Only a task-level total: it goes on the first result
    top_credit = _credit(data.get("credit"))
    if top_credit and results[0][3] is None:
        results[0] = (*results[0][:3], top_credit)
    return results


def _error_message(response: requests.Response) -> str:
    """The first issue Pollo reports in an error response, else the HTTP status."""
    try:
        issues = response.json().get("data", {}).get("issues", [])
    except (ValueError, KeyError, AttributeError):
        issues = []
    if issues:
        return issues[0].get("message", "No message provided.")
    return f"HTTP {response.status_code}"


def _credit(value) -> int | None:
    """A credit count from the API (a string or an int), None if missing or unreadable."""
    try:
        return int(value) if value is not None else None
    except (ValueError, TypeError):
        return None


def get_credit_balance(api_key: str) -> dict[str, int] | None:
    """Fetch current credit balance from Pollo API.

    Returns {"availableCredits": N, "totalCredits": N} or None on failure.
    """
    headers = {"x-api-key": api_key}
    # The credit balance endpoint is at the platform root, not under /generation
    base = POLLO_API_BASE.rsplit("/generation", 1)[0]
    url = f"{base}/credit/balance"
    try:
        response = requests.get(url, headers=headers, timeout=POLLO_API_TIMEOUT)
        if response.status_code == 200:
            resp_json = response.json()
            # API wraps response in {"code":"SUCCESS","data":{...}}
            data = resp_json.get("data", resp_json)
            return {
                "availableCredits": data.get("availableCredits", 0),
                "totalCredits": data.get("totalCredits", 0),
            }
    except Exception as e:
        print(f"[Credits] Failed to fetch balance: {e}")
    return None
