import json
import requests
from typing import Dict, Any
import logging

# -------------------------
# LOGGING CONFIG
# -------------------------
logging.basicConfig(
    level=logging.DEBUG,  # change to INFO if too noisy
    format="%(asctime)s [%(levelname)s] %(message)s",
)

# -------------------------
# CONFIG
# -------------------------
BASE_URL: str = "https://backend.composio.dev/api/v3"
API_KEY: str = "ak_wFvqJjMj9lvvJi_vf0tm"
HR_EMAIL: str = "shreya2002pandey@gmail.com"
SERVER_URL: str = "https://leave-policy-logger.onrender.com/leaves"

CONNECTED_ACCOUNT_ID: str = "ca_jCD32HyrUI7L"  # Active Gmail connection

# -------------------------
# HELPERS
# -------------------------
def _headers() -> Dict[str, str]:
    return {"x-api-key": API_KEY, "Content-Type": "application/json"}


def _execute_tool(tool_name: str, arguments: Dict[str, Any], connected_account_id: str) -> Dict[str, Any]:
    url: str = f"{BASE_URL}/connected_accounts/{connected_account_id}/execute_tool"
    payload: Dict[str, Any] = {"tool_name": tool_name, "arguments": arguments}
    logging.debug(f"Executing tool: {tool_name} with payload={payload} at {url}")
    response = requests.post(url, headers=_headers(), json=payload, timeout=60)
    logging.debug(f"Execute tool response: {response.status_code} {response.text}")
    response.raise_for_status()
    return response.json()


def _ensure_active(connected_account_id: str) -> None:
    url: str = f"{BASE_URL}/connected_accounts/{connected_account_id}"
    logging.debug(f"Checking Gmail connection status at {url}")
    response = requests.get(url, headers=_headers(), timeout=60)
    logging.debug(f"Ensure active response: {response.status_code} {response.text}")
    response.raise_for_status()

    # Log full JSON for debugging
    conn_json = response.json()
    logging.debug(f"Connection JSON: {json.dumps(conn_json, indent=2)}")

    status: str = (
        conn_json.get("connection", {})
        .get("state", {})
        .get("val", {})
        .get("status", "")
    )
    logging.info(f"Resolved Gmail connection status = {status}")
    if status != "ACTIVE":
        raise RuntimeError(f"Gmail connection {connected_account_id} is not active (status={status}).")


# -------------------------
# TOOLS
# -------------------------
def leave_request(name: str, email: str, start_date: str, end_date: str, days: int, description: str) -> str:
    leave_payload: Dict[str, Any] = {
        "name": name,
        "email": email,
        "start_date": start_date,
        "end_date": end_date,
        "days": days,
        "description": description,
        "connected_account_id": CONNECTED_ACCOUNT_ID,
    }
    logging.debug(f"Sending leave request payload: {leave_payload}")
    leave_resp = requests.post(SERVER_URL, json=leave_payload, timeout=60)
    logging.debug(f"Leave request response: {leave_resp.status_code} {leave_resp.text}")
    leave_resp.raise_for_status()
    leave_data: Dict[str, Any] = leave_resp.json()

    if leave_data.get("status") == "rejected":
        result = {
            "leave_data": leave_data,
            "email_status": None,
            "note": "Leave request rejected, email not sent.",
        }
        return json.dumps(result, indent=2)

    email_body: str = (
        f"Leave Application:\n\n"
        f"Name: {leave_data['name']}\n"
        f"Email: {leave_data['email']}\n"
        f"Start Date: {leave_data['start_date']}\n"
        f"End Date: {leave_data['end_date']}\n"
        f"Days: {leave_data['days']}\n"
        f"Reason: {leave_data['description']}\n"
        f"Leaves Left: {leave_data.get('leaves_left')}\n"
    )

    _ensure_active(CONNECTED_ACCOUNT_ID)
    arguments: Dict[str, Any] = {"to": HR_EMAIL, "subject": f"Leave Application from {name}", "body": email_body}
    email_status = _execute_tool("gmail_send_email", arguments, CONNECTED_ACCOUNT_ID)

    result: Dict[str, Any] = {"leave_data": leave_data, "email_status": email_status}
    return json.dumps(result, indent=2)


# -------------------------
# MAIN
# -------------------------
def main():
    try:
        result = leave_request(
            name="Rahul",
            email="rahulharlalka96@gmail.com",
            start_date="31-10-2025",
            end_date="31-10-2025",
            days=1,
            description="travel",
        )
        logging.info("✅ Leave request executed successfully")
        print(result)
    except Exception as e:
        logging.exception("❌ Error while executing leave request")


if __name__ == "__main__":
    main()
