from fastapi import FastAPI, Request, Depends
from fastapi.openapi.docs import get_swagger_ui_html

from resources.model_routes import router as model_output_router
from resources.scripts.limiter_config import limiter
from resources.scripts.get_api_key import get_api_key
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler
from slowapi.middleware import SlowAPIMiddleware
from dotenv import load_dotenv
import os

# Carrega as variáveis de ambiente definidas no arquivo .env
load_dotenv()

app = FastAPI(
    title="API de Análise de Conversas CX",
    description="API que utiliza Genai para analisar conversas de atendimento ao cliente.",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.include_router(model_output_router, prefix="/model-output")


@app.get(
    "/",
    dependencies=[Depends(get_api_key)],
    summary="Verifica se a API está funcionando",
    description="Endpoint que verifica se a API está funcionando corretamente."
)
@limiter.limit("5/minute")
async def read_root(request: Request):
    kustomer_api_key = os.getenv("KUSTOMER_API_KEY")
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    return {
        "message": "API de Análise de Conversas CX funcionando!",
        "KUSTOMER_API_KEY": bool(kustomer_api_key),
        "GEMINI_API_KEY": bool(gemini_api_key)
    }


@app.get(
    "/openapi.json",
    include_in_schema=False,
    dependencies=[Depends(get_api_key)],
    summary="Obtém o schema OpenAPI",
    description="Endpoint que retorna o schema OpenAPI da API."
)
@limiter.limit("5/minute")
async def get_openapi(request: Request):
    return app.openapi()


@app.get(
    "/docs",
    include_in_schema=False,
    dependencies=[Depends(get_api_key)],
    summary="Documentação Swagger",
    description="Endpoint que exibe a documentação Swagger da API."
)
@limiter.limit("5/minute")
async def get_docs(request: Request):
    return get_swagger_ui_html(openapi_url="/openapi.json", title="docs")

