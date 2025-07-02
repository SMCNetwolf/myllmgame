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

#TODO: For later. System prompt is not being used now
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
    Interprete o comando do jogador no contexto de um RPG. Retorne SOMENTE um objeto JSON com:
    - "action_type": ("dialogue", "exploration", "combat", "puzzle", "use_item", "investigate_npc", "generic")
    - "details": objeto com detalhes (ex.: {{"npc": "Lyra Westminster"}}, {{"location": "Taverna"}}, {{"item": "poção"}})
    - "suggestion": string com uma sugestão de ação relevante (ex.: "Explore a cidade e converse com os habitantes") se "action_type" for "generic", caso contrário, deixe vazio ("")
    Primeiro, verifique se o comando é um número (1, 2, 3) e se o contexto recente contém opções numeradas (ex.: "1. Abordar Thorold..."). 
    Se for um número, selecione a opção correspondente do contexto mais recente:
    - Se a opção contém "falar", "perguntar", "abordar", ou "conversar", use "dialogue" e inclua "npc" em "details" (use o NPC mencionado ou o mais recente no contexto, ex.: "Thorold").
    - Se a opção contém "procurar", "investigar", "examinar", "observar", use "exploration" e inclua "location" em "details" (use a localização atual ou mencionada no contexto).
    - Caso contrário, use "generic" com uma sugestão relevante.
    NPCs válidos: {npc_list}
    Se o comando menciona um NPC (ex.: "falar com Eira") ou continua um diálogo (ex.: perguntas ou respostas sem NPC explícito), use "dialogue" e inclua o NPC em "details" usando o nome completo correspondente (ex.: "Eira" -> "Eira Shadowglow"). 
    Se o comando não mencionar um NPC, mas seguir um diálogo recente, use o NPC mais recente do contexto.
    Se o comando contém "procurar", "investigar", "examinar", "observar", , "ir para", use "exploration" e inclua "location" em "details" (use a localização atual ou mencionada no contexto).
    Se o comando for uma pergunta vaga sobre possíveis ações ou interlocutores (ex.: "o que posso fazer", "onde posso ir", "com quem posso falar"), retorne "action_type" como "generic" com "details" vazio e uma "suggestion" listando NPCs ou locais relevantes (ex.: "Converse com Eira Shadowglow ou visite o Templo da Estrela")    
    Se o comando for ambíguo, default para "generic". Não assuma intenções baseadas apenas no contexto.
    Sugestões para "generic" devem recomendar diálogo com um NPC relevante ao objetivo do jogo.
    Baseie-se no contexto e histórico para sugerir ações relevantes aos objetivos do jogo.
    Não inclua texto fora do JSON.  
    Responda em português com no máximo 100 palavras.
    Contexto: {story_context}
    Eventos recentes: {event_info}
    Comando do jogador: {command}
"""

def get_true_clue_prompt(objective, location, recent_history):
    location_str = f"{location['exploring_location']} em {location['name']}" if location.get('exploring_location') else location['name']
    return f"""
        Extraia do objetivo do jogo a seguir uma pista verdadeira para ajudar o jogador.
        Incorpore o local ({location}) e o contexto recente diretamente nas pistas.
        Exemplo: [{{"clue": "Laylus foi visto na taverna de {location_str}.", "id": "clue_001"}}]

        Contexto recente:
        {recent_history}
        
        Objetivo do jogo: 
        {objective}

        Retorne SOMENTE um objeto JSON: {{"clue": "pista", "id": "id unico"}}
        IDs devem ser unicos e diferentes de qualquer ID no contexto recente.
        Pista: max. 40 palavras, em português puro, sem caracteres especiais.
        JSON completo e bem-formado, sem texto fora do JSON.
        {everyone_content_policy['policy']}
    """

def get_false_clue_prompt(objective, location, recent_history):
    return f"""
        Crie uma pista falsa para um RPG de fantasia em {location}, baseada no contexto recente. 
        Faça a pista parecer plausivel, mas contradiga o objetivo do jogo.
        Exemplo: {{"clue": "Ouvi dizer que Lyrien esta escondido na floresta ao norte.", "id": "clue_001"}}

        Contexto recente:
        {recent_history}
        
        Objetivo do jogo: 
        {objective}

        Retorne SOMENTE um objeto JSON: {{"clue": "pista falsa", "id": "id unico"}}.
        ID deve ser unico e diferente de qualquer ID no contexto recente.
        Pista: max. 40 palavras, em português puro, sem caracteres especiais.
        JSON completo e bem-formado, sem texto fora do JSON.
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

def get_exploration_prompt(location, recent_history, clues, reward_type="none"):
    return f"""
        Crie uma narrativa imersiva para uma ação de exploração em {location} em Eldrida, RPG de fantasia. 
        Contexto: {recent_history}. 
        Pistas: {clues}. 
        Gere EXATAMENTE três opções de exploração específicas para {location}. 
        EXATAMENTE uma opção deve ser bem-sucedida, com {f'uma pista verdadeira' if reward_type == 'true_clue' else f'uma pista falsa' if reward_type == 'false_clue' else f'um item (coin ou potion)' if reward_type == 'item' else 'nenhum resultado'}.
        As outras duas opções devem ter resultado nulo (sem item ou pista). 
        Retorne SOMENTE um objeto JSON:
        - "description": narrativa (1-2 frases, máx. 50 palavras)
        - "options": lista de 3 objetos, cada um com:
          - "description": descrição da opção (1 frase, máx. 30 palavras)
          - "action_type": "exploration"
          - "outcome": "success" para a opção bem-sucedida, "none" para outras
          - "reward": "" para todas as opções
        Exemplo:
        {{
            "description": "Você explora {location}, sentindo uma aura misteriosa.",
            "options": [
                {{"description": "Examinar mesa da taverna.", "action_type": "exploration", "outcome": "success", "reward": ""}},
                {{"description": "Olhar atrás do quadro.", "action_type": "exploration", "outcome": "none", "reward": ""}},
                {{"description": "Procurar no baú.", "action_type": "exploration", "outcome": "none", "reward": ""}}
            ]
        }}
        Não inclua texto fora do JSON. Máximo 100 palavras. 
        {everyone_content_policy['policy']}
    """

def get_game_objective_prompt(world):
    return f"""
        Crie um objetivo de jogo para um RPG de fantasia no mundo descrito. 
        Use português puro, sem caracteres especiais ou jargões.
        Estruture a resposta SOMENTE como um objeto JSON com os campos abaixo. 
        Retorne SOMENTE um objeto JSON. Não inclua texto fora do JSON. Certifique-se de que o JSON seja completo e bem-formado.
        - "objective": Narrativa épica (150-200 palavras) sobre um traidor que pretende tomar o poder, usando uma relíquia secreta que aumenta sua capacidade.
        A narrativa deve conter o traidor, um plano malígno (ex.: usar a relíquia durante o ritual do solstício), um aliado confiável do jogador, que o ajudará a vencer e 
        três NPCs auxiliares com papéis na trama (ex.: sábio, mercador, druida). Inclua também a trama e os recursos que o jogador precisará adquirir para poder vencer a batalha final.
        - "true_clue": Objeto com "content" (uma pista sobre o traidor, ex.: "Lyrien busca Cetro EnterWealther") e "id" (string única, ex.: "clue1").
        - "npcs": Lista de objetos, cada um com "name" (ex.: Lyrien Darkscale), "status" (Hostile, Allied, Neutral), e "description" (10-15 palavras descrevendo o NPC sem spoilers, 
        ex.: "Mago sombrio com olhos penetrantes."). Certifique-se de incluir o traidor, o aliado, e os três NPCs auxiliares. 
        Se NPCs forem fornecidos no Mundo, escolha os que usará a partir dali. Caso contrário, crie-os. 
        - "welcome_message": Mensagem inicial (20-30 palavras) introduzindo a cidade e o reino atuais e um rumor vago de traição, sem spoilers (ex.: "Você chega na cidade de Luminaria, no reino de Eldrida e ouve rumores de traição...").
        - "initial_map": Objeto com a localização inicial obtida do Mundo a seguir, ex."Luminaria" contendo "description" (ex.: "Uma cidade vibrante") e "exits" (lista de 3-4 saídas, ex.: ["Ventaria", "Kragnir", "Tharros"]).

        Exemplo de formato:
        {{
            "objective": "texto",
            "true_clue": {{"content": "pista", "id": "clue1"}},
            "npcs": [{{"name": "Nome", "status": "Neutral", "description": "texto"}}],
            "welcome_message": "texto",
            "initial_map": {{"Luminaria": {{"description": "texto", "exits": ["Ventaria", "Kragnir", "Tharros"]}}}}
        }}
        
        Mundo:{world}

        {everyone_content_policy['policy']}
    """

def get_true_ally_confirmation_prompt(npc, location, story_context):
    return f"""
        Crie um diálogo em português com {npc} em {location} confirmando que é aliado confiável. 
        Contexto: {story_context}. 
        Mostre {npc} revelando sua oposição ao vilão (ex.: 'Eu sei do plano do traidor e quero pará-lo'). 
        Retorne apenas o diálogo (ex.: Eira: "Texto..." Você: "Texto..."), sem narrativa ou colchetes. 
        Máximo 3 trocas, 80 palavras. 
        {everyone_content_policy['policy']}
    """

def get_npc_dialogue_prompt(objective, npc, location, story_context, clue):
    return f"""
        Gere um diálogo com {npc} em {location}.
        Contexto: {story_context}
        Objetivo: {objective}
        {clue}
        Instruções:
        - Evite repetir falas anteriores do diálogo, especialmente do histórico recente.
        - Construa respostas que avancem a narrativa e se conectem ao contexto.
        - Leve em consideração o objetivo do jogo, sem dar muitas dicas ou antecipar eventos a partir dele. Apenas o suficiente para manter o interesse do jogador e avançar a narrativa.
        - Retorne apenas o diálogo (ex.: {npc}: "Texto..." Você: "Texto..."), sem narrativa ou colchetes.
        - Máximo 3 trocas, 80 palavras.
        {everyone_content_policy['policy']}
    """        

def get_general_action_prompt(objective, message, location, story_context, clue, npc_list):
    return f"""
        Responda ao comando a seguir com uma narrativa imersiva em {location}. Não inclua uma lista de opções.
        Objetivo: {objective}
        Tenha em mente o objetivo do jogo, mas não dê dicas sobre o papel dos NPCs na trama. O jogador deve ir descobrindo o que fazer, com leve direcionamento, para manter seu interesse.
        Contexto: {story_context}
        NPCs válidos: {npc_list}
        Comando: {message}
        {clue}
        Para comandos perguntando sobre destinos, (ex.: 'onde posso ir'), crie locais interessantes dentro da cidade (ex.: tavernas, becos, praças, mercado, templo) como o foco principal, mas liste também as saídas disponíveis de {location} (fornecidas no contexto).
        Para comandos pedindo auxílo genérico para interação com NPCs (ex.:"com quem posso falar", "quem posso encontrar"), sugira dialogar com NPCs válidos (ex.: "Converse com os Eira Shadowglow ou com a Rainha Lyra sobre o plano do traidor").

        Máximo 100 palavras.
        {everyone_content_policy['policy']}
    """


