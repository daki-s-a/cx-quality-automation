import google.generativeai as genai
from google.ai.generativelanguage_v1beta.types import content
from datetime import datetime
import requests
import json
import re

class CustomerToGenai2:
    def __init__(self, kustomer_api_key, gemini_api_key, conversation_id):
        self.kustomer_api_key = kustomer_api_key
        self.gemini_api_key = gemini_api_key
        self.conversation_id = conversation_id
        self.kustomer_url = f"https://api.prod2.kustomerapp.com/v1/conversations/{self.conversation_id}/messages"
        self.complete_prompt = ''
        self.diretrizes_falhas_graves = """
[Diretrizes de Falha Grave]
1. Agir de maneira ofensiva: Uso de palavras de baixo calão, tom rude ou ameaças.
2. Não resolver o problema / Encerrar sem tratativa: Quando o analista pode resolver, mas não resolve, ou encerra o ticket antes de tentar solucionar.
3. Tratativa incoerente ou problema não resolvido: Solução não corresponde ao problema ou é indevida para encerrar o ticket.
4. Falta de comunicação sobre a conclusão: Não informar ao cliente a solução final ou status.
5. Reembolso não realizado ou divergente: Promessa de reembolso diferente do realizado ou ausência de reembolso.
6. Uso indevido de tags/macros para inibir pesquisa: Inserir tags/macros que impeçam a pesquisa de satisfação.
7. Ações que podem prejudicar cliente/empresa: Cancelar pedido sem autorização ou negar alteração de reembolso.
8. Compartilhamento indevido de informações: Fornecer dados privados da loja/entregador ao cliente, ou vice-versa (solicitar dados é permitido).
        """
        self.diretrizes_gerais = """
[Diretrizes Gerais de Atendimento]
1. APRESENTAÇÃO/ACOLHIMENTO (Nota Máxima: 5): Apresenta-se com nome? Tranquiliza o cliente? Usa palavras acolhedoras?
2. ATENÇÃO (Nota Máxima: 10): Mostra concentração? Evita repetir perguntas já respondidas?
3. ESCRITA (Nota Máxima: 5): Erros gramaticais/ortográficos? Uso adequado de emojis? Sem ruídos de entendimento?
4. RESPOSTAS VAGAS/INCOMPLETAS/INDEVIDAS (Nota Máxima: 10): Responde de forma clara/completa? Explica a solução? Evita frases incompletas?
5. ANÁLISE/SONDAGEM (Nota Máxima: 10): Verifica histórico? Faz perguntas pertinentes? Demonstra esforço?
6. CORDIALIDADE/EMPATIA/TOM DE VOZ (Nota Máxima: 10): Mantém paciência/interesse/empatia? Evita tom inadequado?
7. USO DE RESPOSTAS PRONTAS (MACROS) (Nota Máxima: 10): Evita uso excessivo? Adapta ao contexto?
8. AVALIAÇÃO TÉCNICA (ADERÊNCIA AOS PROCESSOS) (Nota Máxima: 20): Explicações corretas? Cumpriu prazos/ferramentas? Ações em sistema = ações informadas?
9. REGISTRO (Nota Máxima: 10): Registro adequado (tags, taxonomia, Order ID, etc.)?
10. ENCERRAMENTO/DESPEDIDA (Nota Máxima: 10): Pergunta se pode ajudar em algo mais? Despede-se de forma amigável? Solicita avaliação?
        """


    @staticmethod
    def _parse_messages(messages):
        email_pattern = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
        url_pattern = re.compile(r'https?://\S+')
        parsed = []
        for msg in messages:
            attributes = msg.get('attributes', {})
            direction = attributes.get('direction', 'unknown')
            timestamp = attributes.get('sentAt', None)
            content = attributes.get('preview', '')
            redacted_content = email_pattern.sub('[EMAIL REDACTED]', content)
            redacted_content = url_pattern.sub('[LINK REDACTED]', redacted_content)
            parsed.append({'direction': direction, 'timestamp': timestamp, 'content': redacted_content})
        return parsed


    @staticmethod
    def _sort_parsed_messages_by_timestamp(parsed_messages, reverse=False):
        sorted_messages = sorted(
            parsed_messages,
            key=lambda msg: datetime.fromisoformat(msg["timestamp"].replace("Z", "+00:00")),
            reverse=reverse
        )
        return sorted_messages
    

    def _get_customer_messages(self):
        headers = {"accept": "application/json", "authorization": f"Bearer {self.kustomer_api_key}"}
        response = requests.get(self.kustomer_url, headers=headers)
        message_data = response.json()
        messages = message_data['data']
        parsed_messages = CustomerToGenai2._parse_messages(messages)
        sorted_messages = CustomerToGenai2._sort_parsed_messages_by_timestamp(parsed_messages)

        prompt = "```\n"
        for i, message in enumerate(sorted_messages):
            prompt += f"Mensagem {i}: {message}\n"
        prompt += "```"
        self.complete_prompt = prompt


    def _get_falhas_graves(self):
        system_instructions = """
[Instruções do Sistema]
Você é um auditor de qualidade de atendimento. Sua tarefa é analisar uma conversa e identificar *APENAS* se ocorreram **falhas graves**, com base nas diretrizes fornecidas.

**IGNORE COMPLETAMENTE MENSAGENS DE CHATBOT.** Avalie *somente* as mensagens de atendentes *humanos*.

[Formato da Conversa]
A conversa será apresentada no seguinte formato:

Mensagem 0: {{'direction': 'out', 'timestamp': '...', 'content': '...'}}
Mensagem 1: {{'direction': 'in', 'timestamp': '...', 'content': '...'}}
...

[Formato da Resposta]
Retorne um objeto JSON com os seguintes campos:

{
    "falha-grave-encontrada": boolean,
    "falhas-graves": [
        {
            "diretriz": string,
            "mensagem": string,
            "motivo": string
        }
    ],
    "chain-of-thought": string
}



**IMPORTANTE:**

*   **FALHA GRAVE = AÇÃO DO ATENDENTE.**  A falha grave se refere à *ação (ou falta de ação) do atendente*, e *não* ao comportamento do cliente.
*   **FALTA DE RESPOSTA DO CLIENTE != FALHA GRAVE.** Se o *cliente* parar de responder, isso *NÃO* é uma falha grave do atendente, a menos que o atendente *tenha deixado de fornecer uma solução ou informação crucial*.
*   Falha grave só se configura se o problema *não* for resolvido ou se o atendente *prejudicar ativamente* o cliente/empresa, *desrespeitando procedimentos*.
*   Informar sobre prazos/procedimentos *não* é falha grave, *a menos que* o procedimento esteja errado ou impeça a resolução.
*   Se *não* houver falha, `falha-grave-encontrada` deve ser `false` e `falhas-graves` deve ser uma lista *vazia*.
*   Em caso de *dúvida*, indique a *possível* falha (falso positivo).

[Exemplos]
*   **Exemplo 1 (FALHA GRAVE):**
    *   Cliente: "Meu pedido não chegou."
    *   Atendente: Encerra o chat sem responder.
    *   **Isso É falha grave** (não resolver).

*   **Exemplo 2 (NÃO é Falha Grave):**
    *   Cliente: "Meu pedido não chegou."
    *   Atendente: "Verifiquei e o pedido está a caminho.  Previsão de entrega em 30 minutos."
    *   Cliente: (Não responde)
    *   **Isso NÃO é falha grave.** O atendente forneceu uma informação. A falta de resposta é do cliente.

*    **Exemplo 3 (FALHA GRAVE):**
    *   Cliente: "Meu pedido não chegou e eu quero cancelar!"
    *   Atendente: "Não posso cancelar agora, você precisa esperar 24h." (e não oferece outra solução, nem explica o motivo, nem tenta resolver o problema do pedido não ter chegado)
    *   **Isso É falha grave** (não resolver e prejudicar o cliente).
"""

        prompt = self.diretrizes_falhas_graves

        genai.configure(api_key=self.gemini_api_key)

        generation_config = {
            "temperature": 0.1,
            "top_p": 0.95,
            "top_k": 40,
            "max_output_tokens": 8192, 
            "response_schema": content.Schema(
                type = content.Type.OBJECT,
                enum = [],
                required = ["chain-of-thought", "falha-grave-encontrada", "falhas-graves"],
                properties = {
                    "chain-of-thought": content.Schema(
                        type = content.Type.STRING,
                    ),
                    "falha-grave-encontrada": content.Schema(
                        type = content.Type.BOOLEAN,
                    ),
                    "falhas-graves": content.Schema(
                        type = content.Type.ARRAY,
                        items = content.Schema(
                            type = content.Type.STRING,
                        ),
                    ),
                },
            ),
            "response_mime_type": "application/json",
        }

        model = genai.GenerativeModel(
            model_name="gemini-2.0-flash",
            generation_config=generation_config,
            system_instruction=system_instructions
        )

        chat_session = model.start_chat(
            history=[
                {
                    "role": "user",
                    "parts": [
                        prompt
                    ]
                },
                {
                    "role": "model",
                    "parts": [
                        "Entendido. Analisarei o histórico do chat e verificarei se alguma dessas falhas graves ocorreu."
                    ]
                }
            ]
        )

        response = chat_session.send_message(self.complete_prompt)
        return json.loads(response.text)

    
    def _get_diretrizes_gerais(self):
        system_instructions = """
[Instruções do Sistema]
Você é um auditor de qualidade. Sua tarefa é avaliar o atendimento de um *atendente humano* em relação a diretrizes gerais, atribuindo notas a cada uma.

**IGNORE COMPLETAMENTE MENSAGENS DE CHATBOT.** Avalie *somente* as mensagens de atendentes *humanos*.

[Formato da Conversa]
A conversa será apresentada no seguinte formato:

Mensagem 0: {{'direction': 'out', 'timestamp': '...', 'content': '...'}}
Mensagem 1: {{'direction': 'in', 'timestamp': '...', 'content': '...'}}
...

[Formato da Resposta]
Retorne um objeto JSON com a seguinte estrutura:

{
  "notas-diretrizes-gerais": {
    "APRESENTAÇÃO/ACOLHIMENTO": { "nota_maxima": 5, "nota_final": integer, "justificativa": string },
    "ATENÇÃO": { "nota_maxima": 10, "nota_final": integer, "justificativa": string },
    "ESCRITA": { "nota_maxima": 5, "nota_final": integer, "justificativa": string },
    "RESPOSTAS VAGAS/INCOMPLETAS/INDEVIDAS": { "nota_maxima": 10, "nota_final": integer, "justificativa": string },
    "ANÁLISE/SONDAGEM": { "nota_maxima": 10, "nota_final": integer, "justificativa": string },
    "CORDIALIDADE/EMPATIA/TOM DE VOZ": { "nota_maxima": 10, "nota_final": integer, "justificativa": string },
    "USO DE RESPOSTAS PRONTAS (MACROS)": { "nota_maxima": 10, "nota_final": integer, "justificativa": string },
    "AVALIAÇÃO TÉCNICA (ADERÊNCIA AOS PROCESSOS)": { "nota_maxima": 20, "nota_final": integer, "justificativa": string },
    "REGISTRO": { "nota_maxima": 10, "nota_final": integer, "justificativa": string },
    "ENCERRAMENTO/DESPEDIDA": { "nota_maxima": 10, "nota_final": integer, "justificativa": string }
  },
  "chain-of-thought": string
}

**Instruções:**

*   Comece com a `nota_maxima` para cada diretriz.
*   *Deduza* pontos *somente* se houver *evidência clara* de descumprimento.
*   **Preencha *TODOS* os campos `nota_final`, *SEM EXCEÇÃO*. Se a diretriz foi totalmente cumprida, `nota_final` DEVE ser igual a `nota_maxima`.**
*   `justificativa`:
    *   Se a diretriz foi *totalmente* cumprida, use "" ou "Diretriz cumprida integralmente".
    *   Se houve dedução de pontos, explique *brevemente* o motivo.
*   No `chain-of-thought`, apresente o raciocínio *detalhado*, mensagem por mensagem.
"""

        prompt = self.diretrizes_gerais

        genai.configure(api_key=self.gemini_api_key)

        generation_config = {
            "temperature": 0.1,
            "top_p": 0.95,
            "top_k": 40,
            "max_output_tokens": 8192, 
            "response_schema": content.Schema(
                type = content.Type.OBJECT,
                enum = [],
                required = ["chain-of-thought", "notas-diretrizes-gerais"],
                properties = {
                    "chain-of-thought": content.Schema(
                        type = content.Type.STRING,
                    ),
                    "notas-diretrizes-gerais": content.Schema( # Schema simplificado
                        type=content.Type.OBJECT,
                        properties={
                            "APRESENTAÇÃO E ACOLHIMENTO DA QUESTÃO": content.Schema(
                                type=content.Type.OBJECT,
                                properties={
                                    "nota_maxima": content.Schema(type=content.Type.INTEGER),
                                    "nota_final": content.Schema(type=content.Type.INTEGER),
                                    "justificativa": content.Schema(type=content.Type.STRING),
                                },
                            ),
                            "ATENÇÃO": content.Schema(
                                type=content.Type.OBJECT,
                                properties={
                                    "nota_maxima": content.Schema(type=content.Type.INTEGER),
                                    "nota_final": content.Schema(type=content.Type.INTEGER),
                                    "justificativa": content.Schema(type=content.Type.STRING),
                                },
                            ),
                            "ESCRITA": content.Schema(
                                type=content.Type.OBJECT,
                                properties={
                                    "nota_maxima": content.Schema(type=content.Type.INTEGER),
                                    "nota_final": content.Schema(type=content.Type.INTEGER),
                                    "justificativa": content.Schema(type=content.Type.STRING),
                                },
                            ),
                            "RESPOSTAS VAGAS, INCOMPLETAS E/OU INDEVIDAS": content.Schema(
                                type=content.Type.OBJECT,
                                properties={
                                    "nota_maxima": content.Schema(type=content.Type.INTEGER),
                                    "nota_final": content.Schema(type=content.Type.INTEGER),
                                    "justificativa": content.Schema(type=content.Type.STRING),
                                },
                            ),
                            "ANÁLISE/SONDAGEM": content.Schema(
                                type=content.Type.OBJECT,
                                properties={
                                    "nota_maxima": content.Schema(type=content.Type.INTEGER),
                                    "nota_final": content.Schema(type=content.Type.INTEGER),
                                    "justificativa": content.Schema(type=content.Type.STRING),
                                },
                            ),
                            "CORDIALIDADE, EMPATIA E TOM DE VOZ": content.Schema(
                                type=content.Type.OBJECT,
                                properties={
                                    "nota_maxima": content.Schema(type=content.Type.INTEGER),
                                    "nota_final": content.Schema(type=content.Type.INTEGER),
                                    "justificativa": content.Schema(type=content.Type.STRING),
                                },
                            ),
                            "USO DE RESPOSTAS PRONTAS (MACROS)": content.Schema(
                                type=content.Type.OBJECT,
                                properties={
                                    "nota_maxima": content.Schema(type=content.Type.INTEGER),
                                    "nota_final": content.Schema(type=content.Type.INTEGER),
                                    "justificativa": content.Schema(type=content.Type.STRING),
                                },
                            ),
                            "AVALIAÇÃO TÉCNICA (ADERÊNCIA AOS PROCESSOS)": content.Schema(
                                type=content.Type.OBJECT,
                                properties={
                                    "nota_maxima": content.Schema(type=content.Type.INTEGER),
                                    "nota_final": content.Schema(type=content.Type.INTEGER),
                                    "justificativa": content.Schema(type=content.Type.STRING),
                                },
                            ),
                            "REGISTRO": content.Schema(
                                type=content.Type.OBJECT,
                                properties={
                                    "nota_maxima": content.Schema(type=content.Type.INTEGER),
                                    "nota_final": content.Schema(type=content.Type.INTEGER),
                                    "justificativa": content.Schema(type=content.Type.STRING),
                                },
                            ),
                            "ENCERRAMENTO E DESPEDIDA": content.Schema(
                                type=content.Type.OBJECT,
                                properties={
                                    "nota_maxima": content.Schema(type=content.Type.INTEGER),
                                    "nota_final": content.Schema(type=content.Type.INTEGER),
                                    "justificativa": content.Schema(type=content.Type.STRING),
                                },
                            ),
                        },
                    ),
                },
            ),
            "response_mime_type": "application/json",
        }

        model = genai.GenerativeModel(
            model_name="gemini-2.0-flash",
            generation_config=generation_config,
            system_instruction=system_instructions
        )

        chat_session = model.start_chat(
            history=[
                {
                    "role": "user",
                    "parts": [
                        prompt
                    ]
                },
                {
                    "role": "model",
                    "parts": [
                        "Ok. Avaliarei também o atendimento de acordo com essas diretrizes gerais, atribuindo notas conforme o desempenho do atendente."
                    ]
                }
            ]
        )

        response = chat_session.send_message(self.complete_prompt)

        return json.loads(response.text)
    

    def main(self):
        self._get_customer_messages()

        resultado_falhas_graves = self._get_falhas_graves()
        
        resultado_diretrizes_gerais = self._get_diretrizes_gerais()

        resultado_final = {
            "falha-grave-encontrada": resultado_falhas_graves["falha-grave-encontrada"],
            "falhas-graves": resultado_falhas_graves["falhas-graves"],
            "notas-diretrizes-gerais": resultado_diretrizes_gerais["notas-diretrizes-gerais"],
            "conclusion": "Análise completa do atendimento."
        }

        resultado_final['chain-of-thought'] = f"**Análise de Falhas Graves:**\n{resultado_falhas_graves['chain-of-thought']}\n\n**Análise de Diretrizes Gerais:**\n{resultado_diretrizes_gerais['chain-of-thought']}"

        return resultado_final