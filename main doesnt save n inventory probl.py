import gradio as gr
import base64
import json
import datetime

from PIL import Image
from io import BytesIO
from dotenv import dotenv_values
from together import Together

# Load API key from .env file
env_vars = dotenv_values('.env')
together_api_key = env_vars['TOGETHER_API_KEY']
client = Together(api_key=together_api_key)

model="meta-llama/Llama-3-70b-chat-hf"
image_model="black-forest-labs/FLUX.1-schnell-Free"
default_image_file_path='./default_image.png'
image_file_name="./image/output_image" # do not put the termination (.png)
world_path = './SeuMundo_L1.json'
is_start=True

# Salvar e recuperar o Jogo
def save_world(world, filename):
    with open(filename, 'w') as f:
        json.dump(world, f)

def load_world(filename):
    with open(filename, 'r') as f:
        return json.load(f)


def save_game(file_path, game_state):
    try:
        if file_path is None:
            return "Please select a file to save the game state."
        timed_file_path = f"{file_path}_{datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.json"
        save_world(game_state, timed_file_path)
        return f"Game state saved to {file_path} successfully!"
    except Exception as e:
        return f"Failed to save game: {e}"


def retrieve_game(file_path):
    try:
        if file_path is None:
            return [], "Please select a file to retrieve the game state.", default_image_file_path, initial_game_state
        game_state = load_world(file_path.name)
        history = [{"role": "system", "content": system_prompt}]
        output = "Game state retrieved successfully! You can continue your adventure."
        return history, output, default_image_file_path, game_state
    except Exception as e:
        return [], f"Failed to retrieve game: {e}", default_image_file_path, initial_game_state

# carregando o mundo
world = load_world('./SeuMundo_L1.json')
print(f"\n\nLoaded world {world['name']} \n\n")
initial_kingdom = world['kingdoms']['Eldrida']
initial_town = initial_kingdom['towns']["Luminaria"]
initial_character = initial_town['npcs']['Eira Shadowglow']
start = world['description']
start_image_prompt = world['description']
initial_inventory={
    "calça de pano": 1,
    "armadura de couro": 1,
    "camisa de pano": 1,
    "lente de prata": 1,
    "livro de magia": 1,
    "livro de aventura": 1,
    "livro guia do local": 1,
    "gold": 5
}
world_info = f"""
    World: {world['description']}
    Kingdom: {initial_kingdom['description']}
    Town: {initial_town['description']}
    Your Character:  {initial_character['description']}
"""
system_prompt = """
    Você é o mestre do jogo de RPG. \
    Sua função é escrever o que acontece na próxima etapa do jogo.

    Instruções: \

    Você deve escrever de uma a três frases para responder. \
    Sempre responda na segunda pessoa do presente. \
    Ex. (Você olha para a direita e vê...)
"""
system_inventory_prompt = """
    Você é um Assistente de Jogo de IA. \
    Seu trabalho é detectar mudanças no inventário de um jogador \
    com base na história mais recente e no estado atual do jogo. \
    Se um jogador pegar ou ganhar um item, adicione-o ao inventário \
    com uma change_amount positiva. \
    Se um jogador perder um item, remova-o do seu inventário com uma \
    change_amount negativa. \
    Apenas considere itens que claramente o jogador (você) perdeu. \
    Apenas considere itens que claramente o jogador ganhou. \
    Não faça outras atualizações de itens. \
    Se nenhum item foi alterado, retorne {"itemUpdates": []} \
    e nada mais.
    A resposta deve estar em JSON válido /
    Não adicione itens que já estejam no inventário /
    Dado um nome de jogador, inventário e história, retorne uma lista \
    de atualização JSON do inventário do jogador no formato a seguir:\

    {
        "itemUpdates": [
        {"name": <NOME DO ITEM>,
        "change_amount": <QUANTIDADE DE MUDANÇA>}...
        ]
    }
"""
everyone_content_policy = {
    "policy": """O1: Violence and Hate.
    Should not
    - Express hateful, derrogatory, or demeaning sentiments against people based on sensitive personal characteristics.
    - Use slurs based on personal characteristics
    - Write gruesome / graphic violence.
    Can
    - Write tame fantasy violence
    O2: Sexual Content.
    Should not
    - Write any somewhat sexual content that mentions sexual functions or sexual body parts.
    - Write any content that would be inappropriate for kids.
    Can
    - Write romantic content (including kissing, flirting etc...)
    O3: Self-Harm.
    Should not
    - Encourage people to harm themselves.
    - Romanticize or condone self-harm or suicide.
    - Write story depicting suicide.
    O4: Profanity.
    Should not
    - Write with any profane language that wouldn't be appropriate for kids.
    Can
    - Write with kid appropriate language
    O5: Regulated or Controlled Substances.
    Should not
    - Write stories that depicts, glorifies or encourages drug use."""
}
messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": world_info}
    ]
initial_game_state = {
    "world": world['description'],
    "kingdom": initial_kingdom['description'],
    "town": initial_town['description'],
    "character": initial_character['description'],
    "start": world['description'],
    "inventory": initial_inventory,
    "output_image" : default_image_file_path
}
game_state = initial_game_state


def is_safe(message):
    global client
    # Build the prompt with embedded values
    prompt = f"""[INST] Task: Check if there is unsafe content in 'user' messages in conversations according to our safety policy with the below categories.
    
    <BEGIN UNSAFE CONTENT CATEGORIES>
    {everyone_content_policy['policy']}
    <END UNSAFE CONTENT CATEGORIES>
    
    <BEGIN CONVERSATION>
    user: {message}
    
    Provide your safety assessment for user in the above conversation:
    - First line must read 'safe' or 'unsafe'.
    - If unsafe, a second line must include a comma-separated list of violated categories. [/INST]"""

    response = client.completions.create(
        model="Meta-Llama/LlamaGuard-2-8b",
        prompt=prompt,
    )
    result = response.choices[0].text
    return result.strip() == 'safe'


def get_game_state(inventory={}):  #TODO: verify world['start'] and all other things in gme state
    global world, kingdom, town, character, start, image_file_path

    game_state = {
        "world": world['description'],
        "kingdom": kingdom['description'],
        "town": town['description'],
        "character": character['description'],
        "start": start,
        "inventory": inventory,
        "output_image" : image_file_path
    }
    print(f"\n\nGame State:\n{game_state}\n\n")
    return game_state


def detect_inventory_changes(game_state, output):
    global system_inventory_prompt, model, client
    inventory = game_state['inventory']
    messages = [
        {"role": "system", "content": system_inventory_prompt},
        {"role": "user", "content": f'Current Inventory: {str(inventory)}'},
        {"role": "user", "content": f'Recent Story: {output}'},
        #{"role": "user", "content": 'Inventory Updates'}
    ]
    chat_completion = client.chat.completions.create(
        # response_format={"type": "json_object", "schema": InventoryUpdate.model_json_schema()},
        model=model,
        temperature=0.0,
        messages=messages
    )
    response = chat_completion.choices[0].message.content
    print(f'\nInventory changes:\n{response}\n')    
    result = json.loads(response)
    print(f'\nInventory changes:\n{response}\n') 
    return result['itemUpdates']


def update_inventory(inventory, item_updates): #TODO:  quando o inventario não é alterado dá erro
    update_msg = ''
    
    for update in item_updates:
        name = update['name']
        change_amount = update['change_amount']
        if change_amount == 0:
            continue
        elif change_amount > 0:
            if name not in inventory:
                inventory[name] = change_amount
            else:
                inventory[name] += change_amount
            update_msg += f'\nInventory: {name} +{change_amount}'
        elif name in inventory and change_amount < 0:
            inventory[name] += change_amount
            update_msg += f'\nInventory: {name} {change_amount}'
            
        if name in inventory and inventory[name] < 0:
            del inventory[name]
    print(f'\nInventory updated: {inventory}\n')        
    return update_msg #it is a string


def run_action(message, history, game_state): 
    global system_prompt, model, client, world_info, is_start
    
    if(message == 'start'):
        is_start = True
        return is_start, game_state['start']

    
    world_info = f"""
        World: {game_state['world']}
        Kingdom: {game_state['kingdom']}
        Town: {game_state['town']}
        Your Character:  {game_state['character']}
    """

    local_messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": world_info}
    ]

    for action in history:
        #messages.append({"role": "assistant", "content": action[0]})
        #messages.append({"role": "user", "content": action[1]})
        local_messages.append(action)
 
           
    local_messages.append({"role": "user", "content": message})
    model_output = client.chat.completions.create(
        model=model,
        messages=local_messages
    )
    
    result = model_output.choices[0].message.content
    print (f"\nResposta do modelo (Run Action):\n{result}\n")

    is_start = False


    return is_start, result # returns a tuple. A bool and a string


def image_generator(prompt):
    # creates an image and returns a file path for the image
    global client, image_model, image_file_name

    client = client

    response = client.images.generate(
        prompt=prompt,
        model=image_model,
        width=512,  # Smaller image width
        height=384, # Smaller image height
        steps=1,
        n=1,
        response_format="b64_json",
    )
    image_data = base64.b64decode(response.data[0].b64_json)
    image_file_path = f"{image_file_name}_{datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.png"

    # Save the image as a file
    with open(image_file_path, "wb") as f:
        f.write(image_data)
    
    return image_file_path


def main_loop(message, history): #TODO: create a limit to the size of history inside main_loop

    global game_state, is_start, initial_game_state, inventory

    if message.lower().strip() == 'start':
        is_start = True
        game_state = initial_game_state
        output = "Bem-vindo ao jogo! Sua aventura começa agora."
        generated_image_path = default_image_file_path
    else:
        is_start = False
        print(f"\nPergunta:\n{message}\n")
        _,output = run_action(message, history, game_state)
        generated_image_path = image_generator(output)
        

    _, output = run_action(message, history, game_state) # the underscore (_) is a placeholder for a value that is not used. the first value isignored and the 2nd is used


    #safe = is_safe(output)
    #if not safe:
    #    return 'Invalid Output'


    item_updates = detect_inventory_changes(game_state, output)
    update_msg = update_inventory( game_state['inventory'], item_updates )
    output += update_msg # it is a string
    print (f"\nOutput with inventory update:\n{output}\n")

    formatted_message = { "role": "user", "content": message }
    formatted_output = { "role": "assistant", "content": output }
    history.append(formatted_message)
    history.append(formatted_output)

    # Clear the input field by returning an empty string
    print(f"\nUpdatedHistory:\n{history}\n")    

    return history, generated_image_path, ""


def start_game(main_loop, image_path=default_image_file_path, share=False):
    
    with gr.Blocks (theme="soft") as demo:
        with gr.Row():
            with gr.Column(scale=4):
                # Chatbot component
                chatbot = gr.Chatbot(height=450, placeholder="Bem vindo a Arkonix, um reino onde as cidades são construídas sobre as costas de enormes criaturas chamadas Leviatãs, que vagam pelo mundo como montanhas vivas. Essas criaturas gigantes, com escamas grossas como montanhas e olhos que brilham como estrelas, são consideradas sagradas pelos habitantes de Arkonix, que aprenderam a viver em harmonia com elas. As cidades são construídas com madeira e pedra, e são conectadas por pontes e cordas, criando uma rede complexa de ruas e edifícios que se movem ao ritmo dos Leviatãs. Clique em 'Enter' para começar sua aventura.", type='messages')
                    # Gradio state for game state
                game_state = gr.State(initial_game_state)

            with gr.Column(scale=4):        
                # Image output
                output_image = gr.Image(value=image_path) #, label="Cena Atual")  # Use a imagem padrão
        
        # Input components
        with gr.Row():
            with gr.Column(scale=7):
                input_field = gr.Textbox(placeholder="O que você faz a seguir?", container=False)
            with gr.Column(scale=1):
                btn = gr.Button("Enter")
                save_btn = gr.Button("Save Game")
                retrieve_btn = gr.Button("Retrieve Game")
        
        # Button click event
        btn.click(
            fn=main_loop,    #lambda message, history: main_loop(message, history, image_path),
            inputs=[input_field, chatbot],
            outputs=[chatbot, output_image, input_field], # input_field],
            api_name="game_action"
        )

        save_btn.click(
            fn=save_game,
            inputs=[chatbot, game_state],
            outputs=[],
        )

        retrieve_btn.click(
            fn=retrieve_game,
            inputs=[],  # No inputs needed
            outputs=[chatbot, gr.Textbox(), output_image, game_state],  # Update all components
        )


    # Launch with options
    demo.launch(share=share, server_name="0.0.0.0")

history=[{'role': 'system', 'content':system_prompt}]

start_game(main_loop, default_image_file_path, share=False)

# Typical game state:
{
    'world': 'Em Arkonix, os Leviatãs.', 
    'kingdom': 'Eldrida é um reino .', 
    'town': 'Luminaria é uma cidade.', 
    'character': 'Eira é uma jovem maga de Eldrida.', 
    'start': 'Arkonix', 
    'inventory': {
        'calça de pano': 1, 
        'armadura de couro': 1, 
        'camisa de pano': 1, 
        'lente de prata': 1, 
        'livro de magia': 1, 
        'livro de aventura': 1, 
        'livro guia do local': 1, 
        'gold': 5
    }, 
    'output_image': './default_image.png'
}
