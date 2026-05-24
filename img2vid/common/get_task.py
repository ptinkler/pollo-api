"""
Get task status from the Pollo API.

API Docs: https://docs.pollo.ai/task/get-task-status?playground=open
"""
import requests
from .cloudflare import is_cloudflare_block
from .config import POLLO_API_BASE, POLLO_API_TIMEOUT


# Each result tuple: (status, failMsg, url, credits)
TaskResult = tuple[str, str | None, str | None, int | None]


def get_task_status(task_id: str, api_key: str) -> list[TaskResult]:
    headers = {"x-api-key": api_key}
    url = f"{POLLO_API_BASE}/{task_id}/status"
    response = requests.request("GET", url, headers=headers, timeout=POLLO_API_TIMEOUT)

    if is_cloudflare_block(response):
        return [("cloudflare_blocked", "Cloudflare blocked the request — check your VPN or switch regions.", None, None)]

    if response.status_code != 200:
        print("Error fetching task status.")
        try:
            for issue in response.json().get("data", {}).get("issues", []):
                return [("error", issue.get("message", "No message provided."), None, None)]
        except (ValueError, KeyError):
            pass
        return [("error", f"HTTP {response.status_code}", None, None)]

    try:
        data = response.json().get("data", {})
    except ValueError:
        return [("error", "Invalid JSON response", None, None)]

    # Top-level credit field (total for the task)
    top_credit = data.get("credit")
    if top_credit is not None:
        try:
            top_credit = int(top_credit)
        except (ValueError, TypeError):
            top_credit = None

    generations = data.get("generations", [])

    # Fall back to "result" key (alternative response shape)
    if not generations:
        generations = data.get("result", [])

    if not generations:
        print("No generations found in the response.")
        return [("error", "No generations found.", None, None)]

    results = []
    for gen in generations:
        status = gen.get('status')
        fail_msg = gen.get('failMsg')
        video_url = gen.get('url') or gen.get('videoUrl')
        # Per-generation credit (string or int in API response)
        credit = gen.get('credit')
        if credit is not None:
            try:
                credit = int(credit)
            except (ValueError, TypeError):
                credit = None
        results.append((status, fail_msg, video_url, credit))

    # If no per-generation credit but we have a top-level one, assign it to first result
    if top_credit and results and results[0][3] is None:
        s, f, u, _ = results[0]
        results[0] = (s, f, u, top_credit)

    return results


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
