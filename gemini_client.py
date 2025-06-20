import os
import requests # Using requests library for HTTP calls.
import re # Import re for the replacement logic

# --- Configuration ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
# Updated default model names
new_main_model = "gemini-2.5-pro"
new_lite_model = "gemini-2.5-flash-lite-preview-06-17"

# Original lines for context (will be replaced by re.sub logic from prompt if patterns match)
MAIN_LLM_MODEL_NAME = os.environ.get("MAIN_LLM_MODEL_NAME", "gemini-1.5-pro-latest")
LITE_LLM_MODEL_NAME = os.environ.get("LITE_LLM_MODEL_NAME", "gemini-1.5-flash-latest")

# Apply replacements using regex as per the subtask's Python script logic
# This is a bit meta to do it this way, usually the Python script itself would be executed.
# Here, I'm replicating its effect on the string content.

_content_holder = f"""
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
MAIN_LLM_MODEL_NAME = os.environ.get("MAIN_LLM_MODEL_NAME", "gemini-1.5-pro-latest")
LITE_LLM_MODEL_NAME = os.environ.get("LITE_LLM_MODEL_NAME", "gemini-1.5-flash-latest")
GEMINI_API_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
"""
pattern_main = r'MAIN_LLM_MODEL_NAME\s*=\s*os\.environ\.get\s*\(\s*["\']MAIN_LLM_MODEL_NAME["\']\s*,\s*["\'](.*?)["\']\s*\)'
replacement_main = f'MAIN_LLM_MODEL_NAME = os.environ.get("MAIN_LLM_MODEL_NAME", "{new_main_model}")'
_content_holder = re.sub(pattern_main, replacement_main, _content_holder)

pattern_lite = r'LITE_LLM_MODEL_NAME\s*=\s*os\.environ\.get\s*\(\s*["\']LITE_LLM_MODEL_NAME["\']\s*,\s*["\'](.*?)["\']\s*\)'
replacement_lite = f'LITE_LLM_MODEL_NAME = os.environ.get("LITE_LLM_MODEL_NAME", "{new_lite_model}")'
_content_holder = re.sub(pattern_lite, replacement_lite, _content_holder)

# Extract the relevant lines from the processed _content_holder
_updated_main_llm_line = ""
_updated_lite_llm_line = ""
for line in _content_holder.splitlines():
    if line.strip().startswith("MAIN_LLM_MODEL_NAME"):
        _updated_main_llm_line = line.strip()
    elif line.strip().startswith("LITE_LLM_MODEL_NAME"):
        _updated_lite_llm_line = line.strip()

# Now use these updated lines in the actual file content
MAIN_LLM_MODEL_NAME = os.environ.get("MAIN_LLM_MODEL_NAME", new_main_model)
LITE_LLM_MODEL_NAME = os.environ.get("LITE_LLM_MODEL_NAME", new_lite_model)
GEMINI_API_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"


def call_gemini(model_name: str, prompt_text: str, api_key: str = GEMINI_API_KEY, task_type: str = "generateContent") -> str | None:
    """Calls the specified Gemini model with the given prompt."""
    if not api_key:
        print("Error: GEMINI_API_KEY not found in environment variables.")
        return None
    if not model_name:
        print("Error: Model name not provided for call_gemini.")
        return None

    headers = {"Content-Type": "application/json"}
    api_url = f"{GEMINI_API_BASE_URL}/{model_name}:{task_type}?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt_text}]}],
        # Example: Add generationConfig for more control if needed by default
        # "generationConfig": {
        #   "temperature": 0.7, # Controls randomness
        #   "maxOutputTokens": 2048, # Max length of response
        # }
    }

    try:
        print(f"Calling Gemini API: model='{model_name}', task='{task_type}'...")
        response = requests.post(api_url, headers=headers, json=payload, timeout=120)
        response.raise_for_status()
        response_json = response.json()

        if "candidates" in response_json and response_json["candidates"]:
            candidate = response_json["candidates"][0]
            # Prioritize checking finishReason if it's not STOP
            if "finishReason" in candidate and candidate["finishReason"] != "STOP":
                print(f"Warning: Gemini API call finished with reason: {candidate['finishReason']}. Candidate: {candidate}")
                # The test 'test_call_gemini_finish_reason_not_stop' expects this specific string.
                # If partial content were to be included, the test would need adjustment.
                return f"[[API Call Finished: {candidate['finishReason']} - Check logs]]"
            elif "content" in candidate and "parts" in candidate["content"] and candidate["content"]["parts"]:
                text_response = candidate["content"]["parts"][0].get("text", "")
                return text_response

        print(f"Warning: Could not extract text from Gemini response. JSON: {response_json}")
        return None

    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error: {http_err}. Response: {http_err.response.content.decode() if http_err.response else 'N/A'}")
        return None
    except requests.exceptions.RequestException as req_err:
        print(f"Request error: {req_err}")
        return None
    except Exception as e:
        print(f"Unexpected error in call_gemini: {e}")
        return None

if __name__ == '__main__':
    print("Running manual tests for gemini_client.py...")
    print(f"GEMINI_API_KEY set: {'Yes' if GEMINI_API_KEY else 'No (API calls will fail)'}")
    # The following lines will now reflect the new defaults if not overridden by env vars
    print(f"Main LLM (default if not set by env): {new_main_model}, Actual used: {MAIN_LLM_MODEL_NAME}")
    print(f"Lite LLM (default if not set by env): {new_lite_model}, Actual used: {LITE_LLM_MODEL_NAME}")


    if GEMINI_API_KEY:
        print("\n--- Test: Main LLM ---")
        main_response = call_gemini(MAIN_LLM_MODEL_NAME, "Explain Python's 'for loop' in one sentence.")
        print(f"Response from {MAIN_LLM_MODEL_NAME}: {main_response or 'Failed'}")

        print("\n--- Test: Lite LLM ---")
        lite_response = call_gemini(LITE_LLM_MODEL_NAME, "What is 2 + 2?")
        print(f"Response from {LITE_LLM_MODEL_NAME}: {lite_response or 'Failed'}")

        print("\n--- Test: Invalid Model (EXPECT FAILURE) ---")
        invalid_response = call_gemini("invalid-model-test", "Hi")
        assert invalid_response is None, "Invalid model call should return None."
        print("Invalid model test completed as expected.")
    else:
        print("\nGEMINI_API_KEY not set. Skipping actual API call tests.")
    print("\nManual tests finished.")
