from fastapi import HTTPException, Security, status
from fastapi.security.api_key import APIKeyHeader
import os


api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)

def get_api_key(api_key: str = Security(api_key_header)):
    if api_key == os.getenv("API_KEY"):
        return api_key
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API Key inválida"
        )