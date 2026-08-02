"""
HTTP Request Utilities with Retry Logic

Extracted from powerbi_object_manager.py
"""

import logging
import time
from typing import Dict, Optional

import requests

logger = logging.getLogger(__name__)


class APIError(Exception):
    """Raised when API requests fail"""
    pass


class RateLimitError(APIError):
    """Raised when API rate limit is exceeded"""
    pass


def request_with_retry(
    method: str,
    url: str,
    max_retries: int = 3,
    backoff_factor: int = 2,
    **kwargs
) -> requests.Response:
    """
    Execute an HTTP request with automatic retries for rate limiting errors (429)
    
    Args:
        method: HTTP method ('GET', 'POST', 'PUT', 'DELETE', etc.)
        url: Request URL
        max_retries: Maximum number of retry attempts (default: 3)
        backoff_factor: Multiplier for wait time between retries (default: 2)
        **kwargs: Additional arguments for requests (headers, json, files, etc.)
    
    Returns:
        Response object from requests
    
    Raises:
        APIError: If request fails after all retries
        RateLimitError: If rate limit persists after all retries
    """
    last_exception = None
    
    for attempt in range(max_retries + 1):
        try:
            logger.debug(f"{method} {url} (attempt {attempt + 1}/{max_retries + 1})")
            response = requests.request(method, url, **kwargs)
            response.raise_for_status()
            return response
            
        except requests.exceptions.HTTPError as e:
            last_exception = e
            
            # Check for rate limiting (429)
            if e.response.status_code == 429 and attempt < max_retries:
                # Honor Retry-After header when present, else exponential backoff.
                # NOTE: never write to stdout here — in MCP stdio mode stdout is
                # the JSON-RPC transport and any print corrupts the protocol.
                retry_after = e.response.headers.get('Retry-After')
                try:
                    wait_time = float(retry_after) if retry_after else float(backoff_factor ** attempt)
                except (TypeError, ValueError):
                    wait_time = float(backoff_factor ** attempt)
                logger.warning(
                    f"Rate limit hit (429), retrying in {wait_time}s... "
                    f"(attempt {attempt + 1}/{max_retries})"
                )
                time.sleep(wait_time)
                continue
            
            # Not a rate limit error or out of retries
            raise
        
        except requests.exceptions.RequestException as e:
            last_exception = e
            logger.error(f"Request failed: {e}")
            raise APIError(f"Request failed: {e}")
    
    # If we get here, we exhausted retries
    if isinstance(last_exception, requests.exceptions.HTTPError):
        if last_exception.response.status_code == 429:
            raise RateLimitError(
                f"Rate limit exceeded after {max_retries} retries"
            )
    
    raise APIError(f"Request failed after {max_retries} retries: {last_exception}")


def translate_api_error(error: Exception) -> str:
    """
    Translate API error to user-friendly message
    
    Args:
        error: Exception from API request
        
    Returns:
        User-friendly error message
    """
    if isinstance(error, RateLimitError):
        return "Se ha excedido el límite de solicitudes. Por favor, espera unos momentos y vuelve a intentarlo."
    
    if isinstance(error, requests.exceptions.HTTPError):
        status_code = error.response.status_code
        
        if status_code == 401:
            return "Error de autenticación. El token ha expirado o es inválido."
        elif status_code == 403:
            return "Acceso denegado. No tienes permisos suficientes para esta operación."
        elif status_code == 404:
            return "Recurso no encontrado. Verifica el nombre del workspace o el ID del objeto."
        elif status_code == 409:
            return "Conflicto. El recurso ya existe o está en uso."
        elif status_code >= 500:
            return f"Error del servidor (código {status_code}). Inténtalo de nuevo más tarde."
        
        return f"Error HTTP {status_code}: {error.response.text}"
    
    return f"Error: {str(error)}"
