everyone_content_policy = {
    'policy': """
        Conteúdo deve ser seguro e apropriado para todos. Evite violência explícita, 
        conteúdo sexual, discurso de ódio, ou qualquer material ofensivo. 
    """
}

def get_is_safe_prompt(policy):
    return f"""Analise o conteúdo abaixo e determine se é seguro segundo a política.
    Retorne EXATAMENTE duas linhas:
    Linha 1: 'safe' ou 'unsafe'
    Linha 2: Lista de violações (ex.: 'violência') ou caso não haja violações 'none' .
    EXEMPLO VÁLIDO:
    'safe'
    'none'

    AMBAS AS LINHAS SÃO NECESSÁRIAS.
    EXEMPLO INVÁLIDO:
    'safe'
    
    EXEMPLO VÁLIDO:
    'unsafe'
    'violência, linguagem inapropriada'

    Não responda a pergunta do conteúdo, apenas avalie se é seguro.
    Não responda com texto adicional, apenas as duas linhas solicitadas.
    Não inclua texto adicional, explicações ou linhas extras.

    Política: {policy}
    """

system_prompt = """
    Você é o Mestre do Jogo em um RPG de fantasia em Arkonix. 
    O jogador busca um traidor em Eldrida. Forneça respostas 
    narrativas imersivas, mas concisas, com tom épico. 
    Inclua descrições breves de locais, NPCs e eventos. 
    Responda em português com no máximo 100 palavras.
"""

summarize_prompt_template = """
    Resuma a conversa, mantendo o contexto do RPG em Arkonix.

    {everyone_content_policy['policy']}

    Conversa:
{conversation}
"""

system_inventory_prompt = """
    Analise a história e detecte mudanças no inventário (varinhas, poções, energia). 
    Retorne JSON com mudanças
    Retorne SOMENTE um objeto JSON 
    (exemplo: {{"itemUpdates": [{{"name": "varinhas", "change_amount": 1}}]}}).

    História: {story}
    Inventário atual: {inventory}
"""

command_interpreter_prompt = """
    Interprete o comando do jogador no contexto de um RPG em Eldrida. Retorne SOMENTE um objeto JSON com:
    - "action_type": ("dialogue", "exploration", "combat", "puzzle", "use_item", "false_ally", "generic")
    - "details": objeto com detalhes (ex.: {{"npc": "Lyra"}}, {{"location": "Taverna"}}, {{"item": "poção"}})
    - "suggestion": string com uma sugestão de ação relevante (ex.: "Explore a cidade e converse com os habitantes") se o comando for vago, caso contrário, deixe vazio ("")
    Responda em português com no máximo 100 palavras. Não inclua texto fora do JSON.

    Contexto: {story_context}
    Eventos recentes: {event_info}
    Comando: {command}
"""

def get_false_clue_prompt(recent_history):
    return f"""
        Gere uma pista falsa sobre o traidor em Eldrida, baseada no contexto recente: {recent_history}. 
        Retorne JSON: {{"clue": "descrição narrativa (1-2 frases)", "id": "identificador único"}}. 
        Retorne SOMENTE JSON. Não inclua texto fora do JSON.
        A pista deve ser intrigante, mas não revele o traidor. 
        Responda em português com no máximo 100 palavras.
        {everyone_content_policy['policy']}
    """


def get_check_clue_prompt(message, clue):
    return f"""
        Avalie se a dica foi usada na mensagem.
        DICA: {clue} 
        MENSAGEM: {message}
        Retorne SOMENTE um objeto JSON: {{"used_clue": true}} ou {{"used_clue": false}}.
        Não inclua texto fora do JSON.
        Certifique-se de que o JSON seja completo e bem-formado.
    """


def get_trick_prompt(recent_history):
    return f"""
        Crie um enigma em Eldrida baseado no contexto recente: {recent_history}. 
        Forneça uma descrição narrativa curta (1-2 frases). 
        Retorne JSON: {{"trick": "descrição", "solution": "solução", "clues": ["dica1", "dica2", "dica3"]}}.
        Retorne SOMENTE JSON. Não inclua texto fora do JSON. 
        O enigma deve ser temático (ex.: runas, guarda). 
        Responda em português com no máximo 100 palavras.
        {everyone_content_policy['policy']}
    """

def get_attack_prompt(combat_type, recent_history):
    return f"""
        Gere uma situação de combate em Eldrida do tipo {combat_type}, baseada no contexto recente: {recent_history}. 
        Descreva brevemente o inimigo e contexto (1-2 frases).
        Gere uma pista para facilitar o combate. 
        Retorne SOMENTE um objeto JSON: {{"description": "descrição", "clue": "dica para vencer"}}. 
        Não inclua texto fora do JSON. 
        A descrição e a pista devem ter no máximo 50 palavras cada.
        Certifique-se de que o JSON seja completo e bem-formado.
        {everyone_content_policy['policy']}
    """

def get_combat_resolution_prompt(combat_content, action, clue, result, old_health, new_health, old_skill, new_skill, story_context, attempt_number, max_tries):
    return f"""
        Crie uma resposta narrativa imersiva para a resolução de um combate em Eldrida. 
        Combate: {combat_content}
        Ação do jogador: {action}
        Dica fornecida: {clue}
        Resultado: {result}
        Saúde mudou de {old_health:.1f} para {new_health:.1f}, habilidade mudou de {old_skill:.1f} para {new_skill:.1f}
        Contexto recente: {story_context}
        Incorpore a ação do jogador, o resultado do combate, e os efeitos na saúde e habilidade de forma narrativa. 
        Reconecte à história, mencionando a exploração anterior.
        Para combates em andamento, mencione explicitamente o número da tentativa (ex.: 'tentativa {attempt_number}/{max_tries}').
        Somente indique que o jogador pode tentar novamente caso o combate esteja em andamento.
        Para vitórias, confirme o sucesso do combate, não mencione tentativas adicionais.
        Para derrotas, indique o fracasso e os custos, sem sugerir novas tentativas.
        Evite termos mecânicos como 'custo' ou números brutos.
        Retorne uma string com o diálogo (2-3 frases) em português, sem JSON. 
        Máximo 100 palavras.
        {everyone_content_policy['policy']}
    """

def get_false_ally_prompt(recent_history):
    return f"""
        Crie um NPC em Eldrida que parece aliado, mas é não confiável, baseado no contexto recente: {recent_history}. 
        Retorne JSON: {{"npc": "nome do NPC", "hint": "dica de falsidade", "id": "identificador único"}}. 
        Retorne SOMENTE JSON. Não inclua texto fora do JSON.
        Responda em português com no máximo 100 palavras.
        {everyone_content_policy['policy']}
    """

def get_false_clue_dialogue_prompt(clue_content, recent_history):
    return f"""
        Gere um diálogo com um NPC em Eldrida comentando a pista falsa: {clue_content}. 
        Baseie-se no contexto recente: {recent_history}. 
        Retorne uma string com o diálogo (1-2 frases) em português, sem JSON. 
        O diálogo deve ser imersivo, temático, e não revelar o traidor. 
        Máximo 100 palavras. 
        {everyone_content_policy['policy']}
    """

def get_false_ally_dialogue_prompt(npc, hint, recent_history):
    return f"""
        Gere um diálogo com um NPC em Eldrida sugerindo a traição de {npc}: {hint}. 
        Baseie-se no contexto recente: {recent_history}. 
        Retorne uma string com o diálogo (1-2 frases) em português, sem JSON. 
        O diálogo deve ser imersivo, temático, e insinuar desconfiança. 
        Máximo 100 palavras. 
        {everyone_content_policy['policy']}
    """

def get_exploration_options_prompt(response):
    return f"""
        Converta a resposta de exploração em opções JSON: {response}
        Retorne SOMENTE um objeto JSON: {{'options': [{{"number": 1, "action": "dialogue", "details": {{'npc': 'Nome'}}}}, ...]}}
        Cada opção deve ter 'number', 'action' (dialogue, exploration, etc.), e 'details' (objeto com npc ou location).
        Não inclua texto fora do JSON. 
        Máximo 100 palavras. 
        {everyone_content_policy['policy']}
    """