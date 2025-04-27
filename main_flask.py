import base64
import json
import datetime
from create_log import verbose, create_log 

 
import copy

from dotenv import dotenv_values
from together import Together

import prompts

# Load API key from .env file
env_vars = dotenv_values('.env')
together_api_key = env_vars['TOGETHER_API_KEY']
client = Together(api_key=together_api_key)

model="meta-llama/Llama-3-70b-chat-hf"
image_model="black-forest-labs/FLUX.1-schnell-Free"
default_image_file_path='static/default_image.png'
image_file_name="image/output_image" # do not put the termination (.png)
world_path = './SeuMundo_L1.json'

def load_world(filename):
    with open(filename, 'r') as f:
        return json.load(f)

world = load_world('./SeuMundo_L1.json')
#if verbose:    create_log(f"\n\nLoaded world {world['name']} \n\n")

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

def get_world_info(game_state):
    return f"""
        World: {game_state['world']}
        Kingdom: {game_state['kingdom']}
        Town: {game_state['town']}
        Your Character:  {game_state['character']}
    """

system_inventory_prompt = prompts.system_inventory_prompt

def get_initial_game_state():
    initial_game_state = {
    "world": world['description'],
    "kingdom": initial_kingdom['description'],
    "town": initial_town['description'],
    "character": initial_character['description'],
    "start": world['description'],
    "inventory": initial_inventory,
    "output_image" : default_image_file_path
    }
    return copy.deepcopy(initial_game_state)

def is_safe(message):
    global client
    # Build the prompt with embedded values
    prompt = prompts.get_is_safe_prompt(everyone_content_policy)

    response = client.completions.create(
        model="Meta-Llama/LlamaGuard-2-8b",
        prompt=prompt,
    )
    result = response.choices[0].text
    return result.strip() == 'safe'

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
    if verbose:
        create_log(f'\nInventory changes:\n{response}\n')
    try:
        result = json.loads(response)
        return result.get('itemUpdates', [])
    except json.JSONDecodeError:

        if verbose: create_log("Invalid JSON response for inventory updates.")
        return []

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
    if verbose:
        create_log(f'\nInventory updated: \n{inventory}\n')
    return update_msg #it is a string

def run_action(message, history, game_state):
    global model

    system_prompt = prompts.system_prompt
    if verbose:
        create_log(f"run_action. game_state: \n{game_state}")
        create_log(f"run_action. history: \n{history} \ntype: {type(history)}")
    world_info = get_world_info(game_state)
    local_messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": world_info}
    ]

    for entry in history:
        if isinstance(entry, dict):
            local_messages.append(entry)
        else:
            if verbose: create_log("invalid history entry")


    local_messages.append({"role": "user", "content": message})
    response = client.chat.completions.create(
        model=model, 
        messages=local_messages)
    result = response.choices[0].message.content
    if verbose:
        create_log(f"\nRun Action function (LLM completion):\n{result}\n")
    return result

def image_generator(prompt):
    # creates an image and returns a file path for the image
    global client, image_model, image_file_name

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
    import os
    os.makedirs('image', exist_ok=True)

    with open(image_file_path, "wb") as f:
        f.write(image_data)
    
    if verbose:
        create_log(f"\nFunction image_generator. Image {image_file_path} generated\n")

    return image_file_path

def save_game(chatbot, game_state):
   
    import os
    os.makedirs('game_saves', exist_ok=True) # Ensure saves directory exists
    
    # Serialize the game state and chatbot history
    save_data = {
        'chatbot_history': chatbot,
        'game_state': game_state #TODO: transform the data to json,
    }
    # Save file
    save_path = os.path.join('game_saves', f"{datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.json")
    with open(save_path, 'w', encoding='utf-8') as f:
        json.dump(save_data, f, ensure_ascii=False, indent=4)

def retrieve_game():
    import os
    if not os.path.exists('game_saves'):
        return {"choices": [], "value": None, "visible": False}
    
    save_files = [f for f in os.listdir('game_saves') if f.endswith('.json')]

    
    return save_files

def confirm_save(filename, chatbot, game_state):
    if not filename.strip():
        return  # Show error about empty filename
    
    import os

    os.makedirs('game_saves', exist_ok=True)
    
    # Prepare save data
    save_data = {
        'chatbot_history': chatbot,
        'game_state': game_state
    }
    
    # Save file
    save_path = os.path.join('game_saves', f"{filename}.json")
    with open(save_path, 'w', encoding='utf-8') as f:
        json.dump(save_data, f, ensure_ascii=False, indent=4)

def confirm_retrieve(selected_file):
    if not selected_file:
        return [], default_image_file_path, get_initial_game_state()
    import os
    # Construct full path
    save_path = os.path.join('game_saves', selected_file)
    
    # Load save data
    try:

        with open(save_path, 'r', encoding='utf-8') as f:
            save_data = json.load(f)
        
        # Return loaded data
        return (
            save_data.get('chatbot_history', []),  # chatbot history 
            default_image_file_path,  # reset image
            save_data.get('game_state', get_initial_game_state())  # game state
        )
    except Exception as e:
        if verbose: create_log(f"Error loading save file: {e}")
        return [], default_image_file_path, get_initial_game_state()

def main_loop(message, history, game_state):

    if verbose:
        create_log(f"main_loop. history: \n{history}, \ntype: {type(history)}\n")
        create_log(f"main_loop. game_state: {game_state}")
    
    output = run_action(message, history, game_state)
    
    history.append({"role": "user", "content": message})
    generated_image_path = image_generator(output)
    
    game_state["output_image"] = generated_image_path
    if verbose:
        create_log(f"\nPergunta:\n{message}\n")
        create_log(f"\nImage {game_state['output_image']} generated\n")
        create_log(f"\npre action inventory:\n{game_state['inventory']}\n")
        
    item_updates = detect_inventory_changes(game_state, output)
    update_msg = update_inventory( game_state['inventory'], item_updates )
    output += update_msg # it is a string

    if verbose:
        create_log (f"\nOutput with inventory update:\n{output}\n")

    if verbose:
        create_log(f"\nUpdatedHistory:\n{history}\n")
