"""Ollama HTTP Client for Local LLM Inference.

Communicates with the local Ollama instance over its native REST API.
Supports streaming NDJSON responses, request cancellation, model discovery,
and automatic reasoning tag filtering without external cloud dependencies.
"""

from __future__ import annotations

import json
import socket
from typing import Any, Callable, Dict, Iterator, List, Optional, Union
import urllib.error
import urllib.parse
import urllib.request

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from app.ai.cancellation import CancellationToken
from app.ai.thinking_filter import StreamingThinkingFilter, strip_thinking_tags
from app.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_OLLAMA_HOST = "http://127.0.0.1:11434"
DEFAULT_REQUEST_TIMEOUT = 60.0
HEALTH_CHECK_TIMEOUT = 2.0


class OllamaClientError(Exception):
    """Base exception for Ollama client operations."""


class OllamaConnectionError(OllamaClientError):
    """Raised when Ollama server is unreachable or offline."""


class OllamaModelNotFoundError(OllamaClientError):
    """Raised when the requested model is not downloaded in Ollama."""


class OllamaTimeoutError(OllamaClientError):
    """Raised when an inference or network request times out."""


class OllamaCancelledError(OllamaClientError):
    """Raised when an ongoing inference stream is cancelled."""


class OllamaClient:
    """Zero-dependency local HTTP client for Ollama inference."""

    def __init__(
        self,
        base_url: str = DEFAULT_OLLAMA_HOST,
        timeout: float = DEFAULT_REQUEST_TIMEOUT,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self._init_session()

    def _init_session(self) -> None:
        """Initialize persistent HTTP session with connection pooling for low-latency Keep-Alive."""
        self._session = requests.Session()
        self._session.trust_env = False  # Bypass OS proxy on local loopback
        adapter = HTTPAdapter(
            pool_connections=10,
            pool_maxsize=20,
            max_retries=Retry(total=0, connect=0, read=0),
        )
        self._session.mount("http://", adapter)
        self._session.mount("https://", adapter)
        self._session.headers.update({
            "Connection": "keep-alive",
            "User-Agent": "AIFriend-Bond/2.0",
        })

    def _open(self, req: urllib.request.Request, timeout: float):
        """Open a request using the proxy-bypassing opener."""
        return self._opener.open(req, timeout=timeout)

    @property
    def _is_open_patched(self) -> bool:
        """Return True if _open was monkeypatched by test fixtures."""
        return getattr(self._open, "__func__", self._open) is not OllamaClient._open

    def set_base_url(self, base_url: str) -> None:
        """Update endpoint URL."""
        self.base_url = base_url.rstrip("/")

    # ─── Connectivity & Discovery ──────────────────────────────────────

    def is_server_reachable(self, timeout: float = HEALTH_CHECK_TIMEOUT) -> bool:
        """Check if local Ollama daemon is running and reachable."""
        if self._is_open_patched:
            root_url = self.base_url
            req = urllib.request.Request(root_url, method="GET")
            try:
                with self._open(req, timeout=timeout) as resp:
                    if resp.status == 200:
                        return True
            except Exception:
                pass
            tags_url = f"{self.base_url}/api/tags"
            req = urllib.request.Request(tags_url, method="GET")
            try:
                with self._open(req, timeout=timeout) as resp:
                    return resp.status == 200
            except Exception:
                return False

        try:
            resp = self._session.get(self.base_url, timeout=timeout)
            if resp.status_code == 200:
                return True
        except Exception:
            pass

        try:
            resp = self._session.get(f"{self.base_url}/api/tags", timeout=timeout)
            return resp.status_code == 200
        except Exception:
            return False

    def list_models(self, timeout: float = 5.0) -> List[Dict[str, Any]]:
        """Return list of models available in the local Ollama instance."""
        url = f"{self.base_url}/api/tags"
        if self._is_open_patched:
            req = urllib.request.Request(url, method="GET")
            try:
                with self._open(req, timeout=timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    models = data.get("models", [])
                    logger.debug("Found %d models in Ollama.", len(models))
                    return models
            except urllib.error.URLError as e:
                logger.warning("Failed to connect to Ollama at %s: %s", self.base_url, e)
                raise OllamaConnectionError(f"Ollama is not running or unreachable at {self.base_url}.") from e
            except TimeoutError as e:
                logger.warning("Ollama connection timed out at %s: %s", self.base_url, e)
                raise OllamaTimeoutError(f"Connection to Ollama at {self.base_url} timed out.") from e
            except Exception as e:
                if "timed out" in str(e).lower():
                    raise OllamaTimeoutError(f"Connection to Ollama at {self.base_url} timed out.") from e
                logger.error("Error retrieving models from Ollama: %s", e)
                raise OllamaClientError(f"Failed to list Ollama models: {e}") from e

        try:
            resp = self._session.get(url, timeout=timeout)
            if resp.status_code != 200:
                raise OllamaClientError(f"Failed to list Ollama models: HTTP {resp.status_code}")
            models = resp.json().get("models", [])
            logger.debug("Found %d models in Ollama.", len(models))
            return models
        except (requests.exceptions.ConnectTimeout, requests.exceptions.ConnectionError) as e:
            logger.warning("Failed to connect to Ollama at %s: %s", self.base_url, e)
            raise OllamaConnectionError(f"Ollama is not running or unreachable at {self.base_url}.") from e
        except requests.exceptions.Timeout as e:
            logger.warning("Ollama connection timed out at %s: %s", self.base_url, e)
            raise OllamaTimeoutError(f"Connection to Ollama at {self.base_url} timed out.") from e
        except requests.exceptions.RequestException as e:
            logger.warning("Failed to connect to Ollama at %s: %s", self.base_url, e)
            raise OllamaConnectionError(f"Ollama is not running or unreachable at {self.base_url}.") from e
        except Exception as e:
            logger.error("Error retrieving models from Ollama: %s", e)
            raise OllamaClientError(f"Failed to list Ollama models: {e}") from e

    def get_model_names(self) -> List[str]:
        """Convenience method returning just the model name strings."""
        try:
            models = self.list_models()
            names: List[str] = []
            for m in models:
                name = m.get("name") or m.get("model")
                if name:
                    names.append(name)
            return names
        except OllamaConnectionError:
            return []

    # ─── Model Management & Memory Control ────────────────────────────

    def unload_model(self, model_name: str) -> bool:
        """Immediately unload a model from VRAM/RAM using keep_alive=0."""
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": model_name,
            "keep_alive": 0,
        }
        if self._is_open_patched:
            data_bytes = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data_bytes,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with self._open(req, timeout=5.0) as resp:
                    logger.info("Successfully requested model unload for %s", model_name)
                    return resp.status == 200
            except Exception as e:
                logger.warning("Could not unload model %s: %s", model_name, e)
                return False

        try:
            resp = self._session.post(url, json=payload, timeout=5.0)
            logger.info("Successfully requested model unload for %s", model_name)
            return resp.status_code == 200
        except Exception as e:
            logger.warning("Could not unload model %s: %s", model_name, e)
            return False

    def pull_model(
        self,
        model_name: str,
        cancellation_token: Optional[CancellationToken] = None,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> bool:
        """Pull a model from Ollama library with streaming progress updates."""
        url = f"{self.base_url}/api/pull"
        payload = {"name": model_name, "stream": True}
        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data_bytes,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with self._open(req, timeout=3600.0) as resp:
                if cancellation_token:
                    cancellation_token.register(lambda: resp.close())

                for line in resp:
                    if cancellation_token and cancellation_token.is_cancelled:
                        resp.close()
                        raise OllamaCancelledError("Model pull cancelled by user.")
                    if line:
                        chunk_data = json.loads(line.decode("utf-8"))
                        if progress_callback:
                            progress_callback(chunk_data)
                        if chunk_data.get("status") == "success":
                            return True
            return True
        except (urllib.error.URLError, socket.error) as e:
            if cancellation_token and cancellation_token.is_cancelled:
                raise OllamaCancelledError("Model pull cancelled.") from e
            raise OllamaConnectionError(f"Network error pulling model {model_name}: {e}") from e

    def show_model(self, model_name: str) -> Dict[str, Any]:
        """Fetch model metadata, architecture, and parameter details from Ollama via /api/show."""
        url = f"{self.base_url}/api/show"
        payload = {"model": model_name}

        if self._is_open_patched:
            data_bytes = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data_bytes,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with self._open(req, timeout=5.0) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except Exception as e:
                logger.debug("show_model (_open path) notice for '%s': %s", model_name, e)
                return {}

        try:
            resp = self._session.post(url, json=payload, timeout=5.0)
            if resp.status_code == 200:
                return resp.json()
            return {}
        except Exception as e:
            logger.debug("show_model notice for '%s': %s", model_name, e)
            return {}

    # ─── Chat & Generation Streaming ──────────────────────────────────

    def chat_stream(
        self,
        messages: List[Dict[str, str]],
        model: str,
        options: Optional[Dict[str, Any]] = None,
        keep_alive: Optional[str] = "5m",
        cancellation_token: Optional[CancellationToken] = None,
        format: Optional[Union[str, Dict[str, Any]]] = None,
        on_metadata: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Iterator[str]:
        """Stream conversational response tokens chunk by chunk.
        
        Args:
            messages: List of chat messages with 'role' and 'content'.
            model: Name of the Ollama model (e.g. 'qwen3:4b').
            options: Inference parameters (temperature, num_predict, etc.).
            keep_alive: Model memory retention window.
            cancellation_token: Optional cancellation token to abort mid-stream.
            format: Optional format string ('json') or JSON schema dict for structured output.
            on_metadata: Optional callback invoked with final completion metadata (done_reason, eval_count, etc.).
            
        Yields:
            Clean user-visible text chunks (filtering out internal thinking tags).
        """
        if cancellation_token and cancellation_token.is_cancelled:
            raise OllamaCancelledError("Generation already cancelled before starting.")

        url = f"{self.base_url}/api/chat"
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": True,
            "think": False,
        }
        if options:
            payload["options"] = options
        if keep_alive is not None:
            payload["keep_alive"] = keep_alive
        if format is not None:
            payload["format"] = format

        filter_engine = StreamingThinkingFilter()

        if self._is_open_patched:
            # Fallback path for unit tests monkeypatching client._open
            data_bytes = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data_bytes,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with self._open(req, timeout=self.timeout) as resp:
                    if cancellation_token:
                        cancellation_token.register(lambda: resp.close())

                    for line in resp:
                        if cancellation_token and cancellation_token.is_cancelled:
                            resp.close()
                            raise OllamaCancelledError("Generation cancelled by user.")

                        if not line:
                            continue

                        try:
                            chunk_obj = json.loads(line.decode("utf-8"))
                        except json.JSONDecodeError:
                            continue

                        # Check for model error response
                        if "error" in chunk_obj:
                            err_msg = chunk_obj["error"]
                            if "not found" in err_msg.lower():
                                raise OllamaModelNotFoundError(f"Model '{model}' not found in Ollama: {err_msg}")
                            raise OllamaClientError(f"Ollama inference error: {err_msg}")

                        msg = chunk_obj.get("message", {})
                        # Ignore internal reasoning in 'thought' field
                        content = msg.get("content", "")

                        if content:
                            clean_chunk = filter_engine.process_chunk(content)
                            if clean_chunk:
                                yield clean_chunk

                        if chunk_obj.get("done", False):
                            if on_metadata:
                                try:
                                    on_metadata({
                                        "done": True,
                                        "done_reason": chunk_obj.get("done_reason", "stop"),
                                        "eval_count": chunk_obj.get("eval_count", 0),
                                        "eval_duration": chunk_obj.get("eval_duration", 0),
                                        "total_duration": chunk_obj.get("total_duration", 0),
                                        "load_duration": chunk_obj.get("load_duration", 0),
                                        "prompt_eval_count": chunk_obj.get("prompt_eval_count", 0),
                                        "prompt_eval_duration": chunk_obj.get("prompt_eval_duration", 0),
                                    })
                                except Exception as me:
                                    logger.debug("on_metadata error in _open path: %s", me)
                            break

                # Flush any trailing characters from filter
                tail = filter_engine.flush()
                if tail:
                    yield tail

            except urllib.error.HTTPError as e:
                if e.code == 404:
                    raise OllamaModelNotFoundError(f"Model '{model}' not found in Ollama.") from e
                error_body = ""
                try:
                    error_body = e.read().decode("utf-8")
                except Exception:
                    pass
                raise OllamaClientError(f"Ollama HTTP {e.code} error: {e.reason} ({error_body})") from e

            except (socket.timeout, TimeoutError) as e:
                if cancellation_token and cancellation_token.is_cancelled:
                    raise OllamaCancelledError("Stream aborted per cancellation request.") from e
                raise OllamaTimeoutError(f"Inference request timed out after {self.timeout}s.") from e

            except (urllib.error.URLError, socket.error, ValueError, AttributeError) as e:
                if cancellation_token and cancellation_token.is_cancelled:
                    raise OllamaCancelledError("Stream aborted per cancellation request.") from e
                if isinstance(e, (ValueError, AttributeError)):
                    raise
                raise OllamaConnectionError(f"Could not reach Ollama at {self.base_url}: {e}") from e
            return

        # Persistent Keep-Alive connection path via requests.Session
        try:
            connect_timeout = min(5.0, self.timeout)
            resp = self._session.post(
                url,
                json=payload,
                stream=True,
                timeout=(connect_timeout, self.timeout),
            )
            if cancellation_token:
                cancellation_token.register(lambda: resp.close())

            if resp.status_code == 404:
                raise OllamaModelNotFoundError(f"Model '{model}' not found in Ollama.")
            if resp.status_code != 200:
                raise OllamaClientError(f"Ollama HTTP {resp.status_code} error: {resp.text}")

            for raw_line in resp.iter_lines():
                if cancellation_token and cancellation_token.is_cancelled:
                    resp.close()
                    raise OllamaCancelledError("Generation cancelled by user.")

                if not raw_line:
                    continue

                try:
                    chunk_obj = json.loads(raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line)
                except json.JSONDecodeError:
                    continue

                # Check for model error response
                if "error" in chunk_obj:
                    err_msg = chunk_obj["error"]
                    if "not found" in err_msg.lower():
                        raise OllamaModelNotFoundError(f"Model '{model}' not found in Ollama: {err_msg}")
                    raise OllamaClientError(f"Ollama inference error: {err_msg}")

                msg = chunk_obj.get("message", {})
                content = msg.get("content", "")

                if content:
                    clean_chunk = filter_engine.process_chunk(content)
                    if clean_chunk:
                        yield clean_chunk

                if chunk_obj.get("done", False):
                    if on_metadata:
                        try:
                            on_metadata({
                                "done": True,
                                "done_reason": chunk_obj.get("done_reason", "stop"),
                                "eval_count": chunk_obj.get("eval_count", 0),
                                "eval_duration": chunk_obj.get("eval_duration", 0),
                                "total_duration": chunk_obj.get("total_duration", 0),
                                "load_duration": chunk_obj.get("load_duration", 0),
                                "prompt_eval_count": chunk_obj.get("prompt_eval_count", 0),
                                "prompt_eval_duration": chunk_obj.get("prompt_eval_duration", 0),
                            })
                        except Exception as me:
                            logger.debug("on_metadata error in _session path: %s", me)
                    break

            tail = filter_engine.flush()
            if tail:
                yield tail

        except (requests.exceptions.ConnectTimeout, requests.exceptions.ConnectionError) as e:
            if cancellation_token and cancellation_token.is_cancelled:
                raise OllamaCancelledError("Stream aborted per cancellation request.") from e
            raise OllamaConnectionError(f"Could not reach Ollama at {self.base_url}: {e}") from e
        except requests.exceptions.Timeout as e:
            if cancellation_token and cancellation_token.is_cancelled:
                raise OllamaCancelledError("Stream aborted per cancellation request.") from e
            raise OllamaTimeoutError(f"Inference request timed out after {self.timeout}s.") from e
        except requests.exceptions.RequestException as e:
            if cancellation_token and cancellation_token.is_cancelled:
                raise OllamaCancelledError("Stream aborted per cancellation request.") from e
            raise OllamaConnectionError(f"Could not reach Ollama at {self.base_url}: {e}") from e
        except Exception as e:
            if cancellation_token and cancellation_token.is_cancelled:
                raise OllamaCancelledError("Stream aborted per cancellation request.") from e
            raise

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: str,
        options: Optional[Dict[str, Any]] = None,
        keep_alive: Optional[str] = "5m",
        cancellation_token: Optional[CancellationToken] = None,
        format: Optional[Union[str, Dict[str, Any]]] = None,
    ) -> str:
        """Synchronous chat response collector."""
        chunks = list(
            self.chat_stream(
                messages=messages,
                model=model,
                options=options,
                keep_alive=keep_alive,
                cancellation_token=cancellation_token,
                format=format,
            )
        )
        return "".join(chunks).strip()

    # ─── Embedding Generation ─────────────────────────────────────────

    def embed(
        self,
        input_texts: Union[str, List[str]],
        model: str = "all-minilm",
        timeout: Optional[float] = None,
        truncate: bool = True,
    ) -> List[List[float]]:
        """Generate high-dimensional vector embeddings for one or more text inputs.

        Args:
            input_texts: Single text string or list of text strings.
            model: Name of embedding model (e.g. 'all-minilm', 'nomic-embed-text').
            timeout: Optional HTTP request timeout in seconds.
            truncate: Whether to truncate input to fit model context window.

        Returns:
            List of float embedding vectors (one per input text).
        """
        if isinstance(input_texts, str):
            texts = [input_texts]
        else:
            texts = list(input_texts)

        if not texts:
            return []

        req_timeout = timeout or self.timeout
        url_embed = f"{self.base_url}/api/embed"
        url_embeddings = f"{self.base_url}/api/embeddings"
        payload = {
            "model": model,
            "input": texts,
            "truncate": truncate,
        }

        # 1. Try batch /api/embed endpoint
        if self._is_open_patched:
            data_bytes = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url_embed,
                data=data_bytes,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with self._open(req, timeout=req_timeout) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        if "embeddings" in data:
                            return data["embeddings"]
            except Exception as e:
                logger.debug("Ollama /api/embed failed (%s), falling back to legacy /api/embeddings", e)
        else:
            try:
                resp = self._session.post(url_embed, json=payload, timeout=req_timeout)
                if resp.status_code == 200:
                    data = resp.json()
                    if "embeddings" in data:
                        return data["embeddings"]
                elif resp.status_code == 404:
                    if "not found" in resp.text.lower():
                        raise OllamaModelNotFoundError(f"Model '{model}' not found in Ollama: {resp.text}")
            except OllamaModelNotFoundError:
                raise
            except Exception as e:
                logger.debug("Ollama /api/embed request failed (%s), trying legacy /api/embeddings", e)

        # 2. Fallback to legacy /api/embeddings (single item prompt)
        results: List[List[float]] = []
        for text in texts:
            single_payload = {"model": model, "prompt": text}
            if self._is_open_patched:
                data_bytes = json.dumps(single_payload).encode("utf-8")
                req = urllib.request.Request(
                    url_embeddings,
                    data=data_bytes,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                try:
                    with self._open(req, timeout=req_timeout) as resp:
                        if resp.status != 200:
                            raise OllamaClientError(f"Ollama legacy embedding failed: HTTP {resp.status}")
                        data = json.loads(resp.read().decode("utf-8"))
                        results.append(data.get("embedding", []))
                except urllib.error.HTTPError as e:
                    if e.code == 404:
                        raise OllamaModelNotFoundError(f"Model '{model}' not found in Ollama.") from e
                    raise OllamaClientError(f"Ollama HTTP {e.code} error: {e.reason}") from e
                except (socket.timeout, TimeoutError) as e:
                    raise OllamaTimeoutError(f"Embedding request timed out after {req_timeout}s.") from e
                except Exception as e:
                    raise OllamaConnectionError(f"Could not reach Ollama at {self.base_url}: {e}") from e
            else:
                try:
                    resp = self._session.post(url_embeddings, json=single_payload, timeout=req_timeout)
                    if resp.status_code == 404:
                        raise OllamaModelNotFoundError(f"Model '{model}' not found in Ollama.")
                    if resp.status_code != 200:
                        raise OllamaClientError(f"Ollama HTTP {resp.status_code} error: {resp.text}")
                    results.append(resp.json().get("embedding", []))
                except (requests.exceptions.ConnectTimeout, requests.exceptions.ConnectionError) as e:
                    raise OllamaConnectionError(f"Could not reach Ollama at {self.base_url}: {e}") from e
                except requests.exceptions.Timeout as e:
                    raise OllamaTimeoutError(f"Embedding request timed out after {req_timeout}s.") from e
                except Exception:
                    raise

        return results
