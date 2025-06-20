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

#TODO: System prompt (and all others) should be generalizable mainly command_interpreter_prompt
system_prompt = """
    Você é o Mestre do Jogo em um RPG de fantasia em Arkonix. 
    O jogador busca um traidor em Eldrida. Forneça respostas 
    narrativas imersivas, mas concisas, com tom épico. 
    Inclua descrições breves de locais, NPCs e eventos. 
    Responda em português com no máximo 100 palavras.
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
    - "action_type": ("dialogue", "exploration", "combat", "puzzle", "use_item", "investigate", "generic")
    - "details": objeto com detalhes (ex.: {{"npc": "Lyra"}}, {{"location": "Taverna"}}, {{"item": "poção"}})
    - "suggestion": string com uma sugestão de ação relevante (ex.: "Explore a cidade e converse com os habitantes") se o comando for vago, caso contrário, deixe vazio ("")
    Responda em português com no máximo 100 palavras. Não inclua texto fora do JSON.

    Contexto: {story_context}
    Eventos recentes: {event_info}
    Comando: {command}
"""

def get_false_clue_prompt(location, recent_history):
    return f"""
        Crie uma pista falsa para um RPG de fantasia em {location}, Eldrida. 
        Baseie-se no contexto recente: {recent_history}. 
        Retorne SOMENTE um objeto JSON: {{"clue": "pista falsa", "id": "id único"}}. 
        Não inclua texto fora do JSON. 
        A pista deve ser em português puro, sem caracteres estrangeiros (ex.: Cyrillic, kanji) ou nomes próprios com caracteres especiais. 
        Use palavras comuns e evite jargões. 
        Máximo 50 palavras.
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

def get_attack_prompt(combat_type, recent_history):
    combat_description = {
        "oral": "um confronto verbal onde o jogador deve persuadir ou convencer o oponente com argumentos ou evidências",
        "professional": "uma competição de habilidades onde o jogador deve demonstrar maior competência ou estratégia",
        "physical": "um combate físico onde o jogador enfrenta o oponente em uma luta"
    }.get(combat_type, "um combate físico")
    return f"""
        Gere uma situação do tipo {combat_description}, baseada no contexto recente: {recent_history}. 
        Descreva brevemente o oponente e contexto (1-2 frases).
        Gere uma pista para facilitar a vitória (ex.: evidência para oral, tática para profissional, fraqueza para físico). 
        Retorne SOMENTE um objeto JSON: {{"description": "descrição", "clue": "dica para vencer"}}. 
        Não inclua texto fora do JSON. 
        A descrição e a pista devem ter no máximo 50 palavras cada.
        Certifique-se de que o JSON seja completo e bem-formado.
        {everyone_content_policy['policy']}
    """

def get_combat_resolution_prompt(combat_content, action, clue, result, story_context, combat_type):
    combat_instruction = {
        "oral": "Descreva um debate verbal onde o jogador usa argumentos ou evidências para persuadir o oponente. Para vitórias, destaque a persuasão bem-sucedida. Para derrotas, indique que os argumentos não convenceram.",
        "professional": "Descreva uma competição de habilidades onde o jogador demonstra competência. Para vitórias, destaque a superioridade do jogador. Para derrotas, indique que o oponente foi mais habilidoso.",
        "physical": "Descreva uma luta física com ação intensa. Para vitórias, destaque o triunfo em combate. Para derrotas, indique que o jogador foi superado fisicamente. Se o resultado for 'vitória final', inclua o aliado ajudando a vencer."
    }.get(combat_type, "Descreva uma luta física")
    return f"""
        Crie uma resposta narrativa imersiva para a resolução de um evento. 
        Tipo: {combat_type}. {combat_instruction}
        Evento: {combat_content}
        Ação do jogador: {action}
        Resultado: {result}
        Contexto recente: {story_context}
        Baseie a narrativa PRINCIPALMENTE na ação do jogador fornecida: '{action}'. 
        Use o contexto recente APENAS para ambientação (e.g., localização, tom da história), sem incorporar ações anteriores do histórico.
        Para eventos em andamento, indique que o jogador pode tentar novamente, sem mencionar tentativas específicas.
        Para vitórias ou derrotas, foque na ação mais recente do jogador, destacando seu impacto no resultado.
        Evite mencionar saúde, habilidade ou a dica fornecida.
        Retorne uma string com o diálogo (2-5 frases) em português, sem JSON.
        Máximo 100 palavras.
        {everyone_content_policy['policy']}
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

def get_exploration_options_prompt(exploration_result, recent_history):
    return f"""
        Com base na exploração: '{exploration_result}' e contexto recente: '{recent_history}', 
        gere opções de ações para o jogador em Eldrida. 
        Inclua até 4 opções, com pelo menos uma de cada: diálogo (falar com NPC), exploração (visitar local), usar item, e investigar (marcar NPC como suspeito). 
        Retorne SOMENTE um objeto JSON: {{"options": [{{"action": "tipo", "details": {{"npc": "nome" | "location": "lugar" | "item": "item" | "npc": "nome"}}}}, ...]}}. 
        Não inclua texto fora do JSON.
        {everyone_content_policy['policy']}
    """

def get_exploration_prompt(location, recent_history, clues):
    return f"""
        Crie uma narrativa imersiva para uma ação de exploração em {location} em Eldrida, no contexto de um RPG de fantasia. 
        Baseie-se no contexto recente: {recent_history}. 
        Pistas atuais: {clues}. 
        Retorne SOMENTE um objeto JSON: {{"description": "narrativa (1-2 frases)", "item": "item encontrado (mysterious_note, coin, potion) ou vazio", "clue": "pista encontrada ou vazio"}}.
        Não inclua texto fora do JSON. 
        A narrativa deve ser temática e incluir pistas ou itens se relevante. 
        Máximo 100 palavras. 
        {everyone_content_policy['policy']}
    """

def old_get_game_objective_prompt():
    return f"""
        Crie um objetivo de jogo para um RPG de fantasia em Eldrida. 
        O objetivo deve envolver um traidor (ex.: Lyrien Darkscale), uma relíquia secreta (ex.: EnterWealther), e um aliado confiável (ex.:Eira Shadowglow). 
        Inclua pelo menos mais três NPCs com papel auxiliar na trama.
        Estruture como uma narrativa épica (200-300 palavras) com um plano do traidor (ex.: usar a relíquia no solstício). 
        Retorne SOMENTE um objeto JSON: {{"objective": "texto do objetivo"}}. 
        Não inclua texto fora do JSON. 
        Use português puro, sem caracteres especiais ou jargões.
        {everyone_content_policy['policy']}
    """

def get_game_objective_prompt():
    return f"""
        Crie um objetivo de jogo para um RPG de fantasia em Eldrida. Estruture a resposta SOMENTE como um objeto JSON com os campos abaixo. Use português puro, sem caracteres especiais ou jargões.
        Retorne SOMENTE um objeto JSON. Não inclua texto fora do JSON.
        - "objective": Narrativa épica (150-200 palavras) sobre um traidor (ex.: Lyrien Darkscale), uma relíquia secreta (ex.: EnterWealther), e um aliado confiável (ex.: Eira Shadowglow). Inclua um plano do traidor (ex.: ritual no solstício) e mencione três NPCs auxiliares com papéis na trama (ex.: sábio, mercador, druida).
        - "true_clue": Objeto com "content" (uma pista sobre o traidor, ex.: "Lyrien busca EnterWealther") e "id" (string única, ex.: "clue1").
        - "npcs": Lista de objetos, cada um com "name" (ex.: Lyrien Darkscale), "status" (Hostile, Allied, Neutral), e "description" (10-15 palavras descrevendo o NPC sem spoilers, ex.: "Lyrien: Mago sombrio com olhos penetrantes."). Inclua o traidor, o aliado, e os três NPCs auxiliares.
        - "welcome_message": Mensagem inicial (20-30 palavras) introduzindo Eldrida e um rumor vago de traição, sem spoilers (ex.: "Você chega em Eldrida e ouve rumores de traição...").
        - "initial_map": Objeto com uma localização inicial "Eldrida" contendo "description" (ex.: "Uma cidade vibrante") e "exits" (lista de 3-4 saídas, ex.: ["Floresta", "Castelo"]).

        Exemplo de formato:
        {{
            "objective": "texto",
            "true_clue": {{"content": "pista", "id": "clue1"}},
            "npcs": [{{"name": "Nome", "status": "Neutral", "description": "texto"}}],
            "welcome_message": "texto",
            "initial_map": {{"Eldrida": {{"description": "texto", "exits": ["lugar1", "lugar2"]}}}}
        }}

        {everyone_content_policy['policy']}
    """

def get_true_clue_prompt(objective, is_first=False):
    instruction = "Extraia a primeira pista verdadeira do objetivo, indicando a existência da relíquia secreta (ex.: 'O traidor apossou-se de uma relíquia secreta')." if is_first else "Gere uma segunda pista verdadeira, revelando o plano do traidor (ex.: 'O traidor planeja usar a relíquia no solstício')."
    return f"""
        {instruction}
        Objetivo: {objective}
        Retorne SOMENTE um objeto JSON: {{"clue": "pista verdadeira", "id": "id único"}}. 
        Não inclua texto fora do JSON. 
        A pista deve ter no máximo 50 palavras, em português puro, sem caracteres especiais.
        Certifique-se de que o JSON seja completo e bem-formado.
        {everyone_content_policy['policy']}
    """

def get_true_ally_confirmation_prompt(npc, story_context):
    return f"""
        Crie um diálogo em português confirmando {npc} como aliada confiável em Eldrida. 
        Contexto: {story_context}. 
        Mostre Eira revelando sua oposição ao traidor (ex.: 'Eu sei do plano de Lyrien e quero pará-lo'). 
        Retorne apenas o diálogo (ex.: Eira: "Texto..." Você: "Texto..."), sem narrativa ou colchetes. 
        Máximo 3 trocas, 80 palavras. 
        {everyone_content_policy['policy']}
    """















