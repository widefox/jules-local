import unittest
from unittest import mock
import os
import requests # For requests.exceptions

# Adjust import path based on test execution context
try:
    from .. import gemini_client
except ImportError:
    import sys
    sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
    import gemini_client

class TestGeminiClient(unittest.TestCase):

    def setUp(self):
        # Store original environment variables to restore them later
        self.original_api_key = os.environ.get("GEMINI_API_KEY")
        self.original_main_model = os.environ.get("MAIN_LLM_MODEL_NAME")
        self.original_lite_model = os.environ.get("LITE_LLM_MODEL_NAME")

        # Set specific values for testing if needed, or clear them
        os.environ["GEMINI_API_KEY"] = "test_api_key_for_mocking"
        # We'll test with module defaults first, then override with env vars if needed for a specific test.
        # Re-import to pick up env vars if module uses them at import time (gemini_client.py does)
        import importlib
        importlib.reload(gemini_client)


    def tearDown(self):
        # Restore original environment variables
        if self.original_api_key is None:
            if "GEMINI_API_KEY" in os.environ: del os.environ["GEMINI_API_KEY"]
        else:
            os.environ["GEMINI_API_KEY"] = self.original_api_key

        if self.original_main_model is None:
            if "MAIN_LLM_MODEL_NAME" in os.environ: del os.environ["MAIN_LLM_MODEL_NAME"]
        else:
            os.environ["MAIN_LLM_MODEL_NAME"] = self.original_main_model

        if self.original_lite_model is None:
            if "LITE_LLM_MODEL_NAME" in os.environ: del os.environ["LITE_LLM_MODEL_NAME"]
        else:
            os.environ["LITE_LLM_MODEL_NAME"] = self.original_lite_model

        import importlib # Reload to ensure clean state for next test
        importlib.reload(gemini_client)


    @mock.patch('requests.post')
    def test_call_gemini_successful_response(self, mock_post):
        expected_text = "This is a successful response."
        mock_response = mock.Mock()
        mock_response.json.return_value = {
            "candidates": [{
                "content": {"parts": [{"text": expected_text}]},
                "finishReason": "STOP"
            }]
        }
        mock_response.raise_for_status.return_value = None # No HTTPError
        mock_post.return_value = mock_response

        prompt = "Tell me a joke."
        # Use the reloaded module's constants for model names
        response = gemini_client.call_gemini(gemini_client.MAIN_LLM_MODEL_NAME, prompt)

        self.assertEqual(response, expected_text)
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertIn(f"{gemini_client.GEMINI_API_BASE_URL}/{gemini_client.MAIN_LLM_MODEL_NAME}:generateContent?key=test_api_key_for_mocking", args[0])
        self.assertEqual(kwargs['json']['contents'][0]['parts'][0]['text'], prompt)

    @mock.patch('requests.post')
    def test_call_gemini_no_candidates(self, mock_post):
        mock_response = mock.Mock()
        mock_response.json.return_value = {"candidates": []} # Empty candidates
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        response = gemini_client.call_gemini(gemini_client.LITE_LLM_MODEL_NAME, "A simple question.")
        self.assertIsNone(response) # Should return None if text can't be extracted

    @mock.patch('requests.post')
    def test_call_gemini_finish_reason_not_stop(self, mock_post):
        mock_response = mock.Mock()
        mock_response.json.return_value = {
            "candidates": [{"finishReason": "MAX_TOKENS", "content": {"parts": [{"text": "Partial "}]}}]
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        # Expecting a specific string indicating the finish reason
        response = gemini_client.call_gemini(gemini_client.MAIN_LLM_MODEL_NAME, "Generate long text.")
        self.assertIn("[[API Call Finished: MAX_TOKENS", response)


    @mock.patch('requests.post')
    def test_call_gemini_http_error(self, mock_post):
        mock_http_response = mock.Mock()
        mock_http_response.content = b"Auth error" # Simulate content of an error response
        mock_response = mock.Mock()
        # Simulate an HTTPError (e.g., 401 Unauthorized)
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(response=mock_http_response)
        mock_post.return_value = mock_response

        response = gemini_client.call_gemini(gemini_client.MAIN_LLM_MODEL_NAME, "Test prompt")
        self.assertIsNone(response)

    @mock.patch('requests.post')
    def test_call_gemini_request_exception(self, mock_post):
        # Simulate a network error or other requests.exceptions.RequestException
        mock_post.side_effect = requests.exceptions.Timeout("Connection timed out")

        response = gemini_client.call_gemini(gemini_client.MAIN_LLM_MODEL_NAME, "Test prompt")
        self.assertIsNone(response)

    def test_call_gemini_no_api_key(self):
        # Temporarily unset the API key for this test
        # The setUp reloads, so this test needs to ensure the reloaded module sees no key.
        # Patch the constant directly for this test's scope
        with mock.patch('gemini_client.GEMINI_API_KEY', None):
            response = gemini_client.call_gemini(gemini_client.MAIN_LLM_MODEL_NAME, "Test prompt")
            self.assertIsNone(response)
        # GEMINI_API_KEY is restored by tearDown's reload based on original_api_key

    def test_call_gemini_no_model_name(self):
        response = gemini_client.call_gemini(model_name="", prompt_text="Test prompt")
        self.assertIsNone(response)

    @mock.patch('requests.post')
    def test_call_gemini_uses_env_var_for_model_override(self, mock_post):
        # Test if setting env var for model name overrides module default
        custom_main_model = "custom-pro-model-from-env"
        os.environ["MAIN_LLM_MODEL_NAME"] = custom_main_model
        import importlib
        importlib.reload(gemini_client) # Reload to pick up new env var

        mock_response = mock.Mock()
        mock_response.json.return_value = {"candidates": [{"content": {"parts": [{"text": "response"}]}, "finishReason": "STOP"}]}
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        gemini_client.call_gemini(gemini_client.MAIN_LLM_MODEL_NAME, "Test")

        # Check that the API call was made with the custom model name from env var
        args, _ = mock_post.call_args
        self.assertIn(custom_main_model, args[0]) # URL should contain the custom model

        # No need to del os.environ here as tearDown will restore based on self.original_main_model
        # and then reload gemini_client.

if __name__ == '__main__':
    unittest.main(argv=['first-arg-is-ignored'], exit=False)
