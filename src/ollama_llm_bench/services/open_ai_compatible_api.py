import logging
import time
from typing import Callable, List, Optional, override

import requests  # Requires 'requests' library: pip install requests [[1]]

from ollama_llm_bench.core.interfaces import LLMApi
from ollama_llm_bench.core.models import InferenceResponse
from ollama_llm_bench.utils.text_utils import sanitize_text

logger = logging.getLogger(__name__)


class OpenAICompatibleApi(LLMApi):
    """
    Implementation of LLMApi using an HTTP client for OpenAI-compatible LLM inference.
    Handles model listing, warm-up, and inference with error recovery.
    """

    def __init__(self, base_url: str, api_key: Optional[str] = None):
        """
        Initialize the OpenAI-compatible API wrapper.

        Args:
            base_url: Base URL for the OpenAI-compatible API endpoint.
            api_key: Optional API key for authorization.
        """
        self._base_url = base_url.rstrip('/')
        self._api_key = api_key
        self._session = requests.Session()  # Reuse connection for efficiency
        if self._api_key:
            self._session.headers.update({ "Authorization": f"Bearer {self._api_key}" })
        # Set a default content type for JSON requests
        self._session.headers.update({ "Content-Type": "application/json" })

    def _make_request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """Helper method to make HTTP requests."""
        url = f"{self._base_url}{endpoint}"
        response = self._session.request(method, url, **kwargs)
        response.raise_for_status()  # Raises an HTTPError for bad responses (4xx or 5xx)
        return response

    @override
    def get_models_list(self) -> List[str]:
        """
        Retrieve the list of available models from the API server.

        Returns:
            Sorted list of model names, or empty list if request fails.
        """
        try:
            response = self._make_request("GET", "/v1/models")
            data = response.json()
            # Assuming the API returns a list of models under a 'data' key,
            # and each model object has an 'id' key.
            # This structure is common but might need adjustment based on the specific API.
            model_names = [model["id"] for model in data.get("data", [])]
            model_names.sort()
            logger.debug(f"Models received: {len(model_names)}")
            return model_names
        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to get models from API: {e}")
            return []
        except (KeyError, ValueError) as e:
            logger.warning(f"Failed to parse model list response: {e}")
            return []

    @override
    def warm_up(self, model_name: str) -> bool:
        """
        Load and initialize a model in memory to reduce inference latency.
        Sends a simple test prompt.

        Args:
            model_name: Name of the model to warm up.

        Returns:
            True if warm-up succeeded within retry limits, False otherwise.
        """
        for retry in range(5):
            response_received = False
            try:
                # Use the chat completion endpoint for warm-up
                payload = {
                    "model": model_name,
                    "messages": [{ "role": "user", "content": "Say Hello" }],
                    "max_tokens": 10,  # Limit tokens for a quick response
                    "stream": False
                }
                response = self._make_request("POST", "/v1/chat/completions", json=payload)
                result = response.json()
                # Check if a choice with content was returned
                if result.get("choices") and result["choices"][0].get("message", { }).get("content"):
                    logger.debug(f"Warmup response: {result['choices'][0]['message']['content']}")
                    response_received = True
            except requests.exceptions.RequestException as ex:
                logger.warning(f"Failed to warmup model {model_name}", exc_info=ex)
            except (KeyError, ValueError) as ex:
                logger.warning(f"Failed to parse warmup response for model {model_name}", exc_info=ex)

            if not response_received:
                logger.debug(f"Failed to warm up {model_name}, retrying: #{retry}")
                time.sleep(30)
            else:
                return response_received
        return False

    @override
    def inference(
        self,
        model_name: str,
        user_prompt: str,
        system_prompt: Optional[str] = None,
        on_llm_response: Optional[Callable[[str], None]] = None,
        on_is_stop_signal: Optional[Callable[[], bool]] = None,
        is_judge_mode: bool = False,
    ) -> InferenceResponse:
        """
        Perform inference using the specified model and prompts.
        Uses the /v1/chat/completions endpoint.

        Args:
            model_name: Name of the model to use for inference.
            user_prompt: Input prompt provided by the user.
            system_prompt: Optional system-level instruction to guide model behavior.
            on_llm_response: Optional callback to receive response chunks or status messages.
            on_is_stop_signal: Optional callback that returns True if inference should be interrupted.
            is_judge_mode: If True, suppresses user prompt logging in callbacks.

        Returns:
            InferenceResponse containing generated text, timing, token count, and error status.
        """
        try:
            # Prepare messages for the chat endpoint
            messages = []
            if system_prompt:
                messages.append({ "role": "system", "content": system_prompt })
            messages.append({ "role": "user", "content": user_prompt })

            start_time = time.time()
            logger.debug(f"Starting inference for model: {model_name}")
            if on_llm_response:
                if not is_judge_mode:
                    on_llm_response(f"User prompt: {user_prompt}")
                on_llm_response(f"Starting inference for model: {model_name}")

            # Prepare the payload for chat completion
            payload = {
                "model": model_name,
                "messages": messages,
                "stream": False,  # We are not implementing streaming here for simplicity
                # Note: Options like temperature, max_tokens, etc., might go here depending on the API
            }

            response = self._make_request("POST", "/v1/chat/completions", json=payload)
            result = response.json()

            # Extract the response content and token usage
            full_response = ""
            tokens_generated = 0
            if result.get("choices") and result["choices"][0].get("message", { }).get("content"):
                full_response = result["choices"][0]["message"]["content"]
                full_response = sanitize_text(full_response)
                # Token counts might be in 'usage' key, structure can vary
                tokens_generated = result.get("usage", { }).get("completion_tokens", 0)

            if on_llm_response:
                on_llm_response("LLM Response:")
                on_llm_response(full_response)

            end_time = time.time()
            logger.debug(f"Inference completed for model: {model_name}")
            time_taken_ms = int((end_time - start_time) * 1000)
            logger.debug(f"Time taken for inference: {time_taken_ms}ms")
            if on_llm_response:
                on_llm_response(f"Inference completed for model: {model_name}")
                on_llm_response(f"Time taken for inference: {time_taken_ms}ms")

            return InferenceResponse(
                llm_response=full_response,
                time_taken_ms=time_taken_ms,
                tokens_generated=tokens_generated,
            )

        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to run inference for model: {model_name}: {e}")
            error_message = f"HTTP Error: {e}"
            if on_llm_response:
                on_llm_response(f"Failed to run inference for model: {model_name}")
                on_llm_response(f"Error: {error_message}")
            return InferenceResponse(
                has_error=True,
                error_message=error_message,
            )
        except (KeyError, ValueError) as e:
            logger.warning(f"Failed to parse inference response for model: {model_name}: {e}")
            error_message = f"Parsing Error: {e}"
            if on_llm_response:
                on_llm_response(f"Failed to run inference for model: {model_name}")
                on_llm_response(f"Error: {error_message}")
            return InferenceResponse(
                has_error=True,
                error_message=error_message,
            )
