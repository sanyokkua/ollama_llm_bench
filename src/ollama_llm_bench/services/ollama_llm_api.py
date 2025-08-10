import logging
import time
from typing import Callable, List, Optional, override

from ollama import Client

from ollama_llm_bench.core.interfaces import LLMApi
from ollama_llm_bench.core.models import InferenceResponse

logger = logging.getLogger(__name__)


class OllamaApi(LLMApi):
    def __init__(self, client: Client):
        self._ollama_client = client

    @override
    def get_models_list(self) -> List[dict]:
        try:
            response = self._ollama_client.list()
            model_names = [model["model"] for model in response["models"]]
            model_names.sort()
            logger.debug(f"Models received: {len(model_names)}")
            return model_names
        except Exception:
            # Return empty list if there's any error
            logger.warning(f"Failed to get models from ollama")
            return []

    @override
    def warm_up(self, model_name: str) -> bool:
        try:
            response = self._ollama_client.generate(
                model=model_name,
                prompt='Hello',
            )
            logger.debug(f"Warmup response: {response.response}")
            return True
        except Exception as ex:
            logger.warning(f"Failed to warmup", exc_info=ex)
            return False

    @override
    def inference(
        self,
        model_name: str,
        user_prompt: str,
        system_prompt: Optional[str] = None,
        on_llm_response: Optional[Callable[[str], None]] = None,
    ) -> InferenceResponse:
        try:
            full_response = ""
            tokens_generated = 0
            options = {
            }

            if system_prompt:
                options['system'] = system_prompt

            start_time = time.time()
            logger.debug(f"Starting inference for model: {model_name}")
            if on_llm_response:
                on_llm_response(f"User prompt: {user_prompt}\n")
                on_llm_response(f"Starting inference for model: {model_name}\n")

            response = self._ollama_client.generate(
                model=model_name,
                prompt=user_prompt,
                options=options,
                stream=True,
            )

            for chunk in response:
                if 'response' in chunk:
                    content = chunk['response']
                    full_response += content
                    tokens_generated += len(content.split())

            if on_llm_response:
                on_llm_response("LLM Response:\n")
                on_llm_response(full_response)
                on_llm_response("\n")

            end_time = time.time()
            logger.debug(f"Inference completed for model: {model_name}")
            time_taken_ms = int((end_time - start_time) * 1000)
            logger.debug(f"Time taken for inference: {time_taken_ms}ms")
            if on_llm_response:
                on_llm_response(f"Inference completed for model: {model_name}\n")
                on_llm_response(f"Time taken for inference: {time_taken_ms}ms\n")

            return InferenceResponse(
                llm_response=full_response,
                time_taken_ms=time_taken_ms,
                tokens_generated=tokens_generated,
            )

        except Exception as e:
            logger.warning(f"Failed to run inference for model: {model_name}")
            if on_llm_response:
                on_llm_response(f"Failed to run inference for model: {model_name}\n")
                on_llm_response(f"Error: {str(e)}\n")
            return InferenceResponse(
                has_error=True,
                error_message=str(e),
            )
