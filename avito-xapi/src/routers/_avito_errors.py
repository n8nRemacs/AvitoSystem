"""Shared helper for propagating Avito 4xx errors as FastAPI HTTPExceptions."""
from curl_cffi.requests.exceptions import HTTPError as CurlHTTPError
from fastapi import HTTPException

PROPAGATE = {401, 403, 429}


def reraise_avito_error(exc: CurlHTTPError) -> None:
    """If Avito returned 401/403/429, re-raise as HTTPException with same code.

    Otherwise re-raise the original exception so the generic error handler
    can deal with it (log, 500, etc.).
    """
    status = exc.response.status_code if exc.response is not None else None
    if status in PROPAGATE:
        raise HTTPException(status_code=status, detail=f"Avito {status}")
    raise exc
