import os
import json
import requests

GENAI_API_URL = "<URL_HERE>"
GENAI_HUB_TOKEN = os.getenv("GENAI_HUB_TOKEN")

CONTEXT_PATH = os.path.join(
    os.path.dirname(__file__),
    "prompt_templates",
    "context.txt"
)

def read_context_file() -> str:
    with open(CONTEXT_PATH, "r", encoding="utf-8") as f:
        return f.read()


def call_genai_api(model_name: str, regex: str) -> dict:


    # Read context.txt and append JSON array of regex
    context = read_context_file()
    regex_list_json = json.dumps([regex], separators=(",", ":"))
    payload_text = context + regex_list_json

    conversation_request = {
        "model": model_name,
        "request": {
            "system_prompt": (
                "You are the world's most accurate PERL to Go regex converter tool. "
                "Your task is to convert PERL regex into equivalent Golang compliant regex."
            ),
            "messages": [
                {
                    "role": "user",
                    "text": payload_text
                }
            ]
        }
    }

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {GENAI_HUB_TOKEN}"
    }

    response = requests.post(
        GENAI_API_URL,
        headers=headers,
        json=conversation_request,
        timeout=300
    )

    if response.status_code != 200:
        raise Exception(f"❌ GenAIHub API error: {response.status_code}\n{response.text}")

    response_json = response.json()

    # Pull JSON array from conversation text
    text_content = response_json["resources"][0]["content"]
    start_idx = text_content.find("[")
    end_idx = text_content.rfind("]") + 1
    json_str = text_content[start_idx:end_idx]

    regex_array = json.loads(json_str)

    if not regex_array:
        raise Exception("⚠ No regex results returned from GenAIHub.")

    return regex_array[0]
