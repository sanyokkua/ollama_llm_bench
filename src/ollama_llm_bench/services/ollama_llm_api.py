import logging
import time
from typing import Callable, List, Optional, override

from ollama import Client

from ollama_llm_bench.core.interfaces import LLMApi
from ollama_llm_bench.core.models import InferenceResponse
from ollama_llm_bench.utils.text_utils import sanitize_text

logger = logging.getLogger(__name__)


class OllamaApi(LLMApi):
    """
    Implementation of LLMApi using the Ollama client for local LLM inference.
    Handles model listing, warm-up, and inference with error recovery.
    """

    def __init__(self, client: Client):
        """
        Initialize the Ollama API wrapper.

        Args:
            client: Configured Ollama client instance.
        """
        self._ollama_client = client

    @override
    def get_models_list(self) -> List[dict]:
        """
        Retrieve the list of available models from the Ollama server.

        Returns:
            Sorted list of model names, or empty list if request fails.
        """
        try:
            response = self._ollama_client.list()
            model_names = { model["model"] for model in response["models"] }
            model_names = list(model_names)
            model_names.sort()
            logger.debug(f"Models received: {len(model_names)}")
            return model_names
        except Exception:
            # Return empty list if there's any error
            logger.warning(f"Failed to get models from ollama")
            return []

    @override
    def warm_up(self, model_name: str) -> bool:
        """
        Load and initialize a model in memory to reduce inference latency.

        Args:
            model_name: Name of the model to warm up.

        Returns:
            True if warm-up succeeded within retry limits, False otherwise.
        """
        for retry in range(5):
            response_received = False
            try:
                response = self._ollama_client.generate(
                    model=model_name,
                    prompt='Say Hello',
                )
                logger.debug(f"Warmup response: {response.response}")
                response_received = True
            except Exception as ex:
                logger.warning(f"Failed to warmup", exc_info=ex)
            if not response_received:
                logger.debug(f"Failed to warm up, retrying: #{retry}")
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
            options = { }

            if system_prompt:
                options['system'] = system_prompt

            start_time = time.time()
            logger.debug(f"Starting inference for model: {model_name}")
            if on_llm_response:
                if not is_judge_mode:
                    on_llm_response(f"User prompt: {user_prompt}")
                on_llm_response(f"Starting inference for model: {model_name}")

            response = self._ollama_client.generate(
                model=model_name,
                prompt=user_prompt,
                options=options,
                stream=False,
            )
            full_response = sanitize_text(response.response)
            tokens_generated = response.eval_count

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

        except Exception as e:
            logger.warning(f"Failed to run inference for model: {model_name}")
            if on_llm_response:
                on_llm_response(f"Failed to run inference for model: {model_name}")
                on_llm_response(f"Error: {str(e)}")
            return InferenceResponse(
                has_error=True,
                error_message=str(e),
            )
