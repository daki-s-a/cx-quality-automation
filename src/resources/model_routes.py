import os
from fastapi import APIRouter, HTTPException, Path, Depends, Request
from pydantic import BaseModel, Field
from typing import Optional

from resources.scripts.kustomer_to_genai import CustomerToGenai

from resources.scripts.get_api_key import get_api_key

from resources.scripts.limiter_config import limiter


router = APIRouter(tags=['Model Output'])

# Modelo para os critérios
class Criterios(BaseModel):
    apresentacao_acolhimento: Optional[int] = Field(None)
    atencao: Optional[int] = Field(None)
    escrita: Optional[int] = Field(None)
    respostas_incompletas: Optional[int] = Field(None)
    analise_sondagem: Optional[int] = Field(None)
    cordialidade_empatia: Optional[int] = Field(None)
    uso_respostas_prontas: Optional[int] = Field(None)
    avaliacao_tecnica: Optional[int] = Field(None)
    registro: Optional[int] = Field(None)
    encerramento_despedida: Optional[int] = Field(None)
    observacoes_diretrizes_gerais: Optional[str] = Field(None)

# Modelo de resposta conforme o novo schema
class ModelOutput(BaseModel):
    nota_final: Optional[int] = Field(None)
    criterios: Optional[Criterios] = Field(None)
    falha_grave_detectada: bool = Field(...)
    falha_grave_observacao: Optional[str] = Field(None)
    observacoes_gerais: Optional[str] = Field(None)

@router.get(
    "/{conversation_id}",
    dependencies=[Depends(get_api_key)],
    response_model=ModelOutput,
    summary="Obtém a análise da conversa pelo conversation_id",
    description="Endpoint que recebe um conversation_id e retorna a resposta processada pelo modelo Genai."
)
@limiter.limit("2/minute; 1000/day")
async def get_model_output(
    request: Request,
    conversation_id: str = Path(..., title="Conversation ID", description="ID da conversa para análise")
):
    # Recupera as chaves de API a partir das variáveis de ambiente
    kustomer_api_key = os.getenv("KUSTOMER_API_KEY")
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    if not kustomer_api_key or not gemini_api_key:
        raise HTTPException(status_code=500, detail="Chaves de API não configuradas.")

    try:
        # Instancia a classe com os parâmetros necessários
        customer_genai = CustomerToGenai(kustomer_api_key, gemini_api_key, conversation_id)
        response_output = customer_genai.main()
        return response_output
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
