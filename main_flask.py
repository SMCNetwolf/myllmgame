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
        Your Inventory: {game_state['inventory']}
    """

def get_initial_game_state():
    initial_game_state = {
    "world": world['description'],
    "kingdom": initial_kingdom['description'],
    "town": initial_town['description'],
    "character": initial_character['description'],
    "start": world['description'],
    "inventory": initial_inventory,
    "output_image" : default_image_file_path,
    "history": []
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

def summarize(template, prompt):
    # Build the prompt with embedded values
    final_prompt = template + prompt
    response = client.chat.completions.create(
        model=model, 
        messages=final_prompt)

    result = response.choices[0].message.content    

def detect_inventory_changes(game_state, last_response, verbose=False):

    global model, client

    inventory = game_state['inventory']

    messages = [
        {"role": "system", "content": prompts.system_inventory_prompt},
        {"role": "user", "content": f'Current Inventory: {str(inventory)}'},
        {"role": "user", "content": f'Recent Story: {last_response}'},
    ]

    chat_completion = client.chat.completions.create(
        model=model,
        temperature=0.0,
        messages=messages
        )

    response = chat_completion.choices[0].message.content

    if verbose:
        create_log(f'\nDETECT_INVENTORY_CHANGES: Is it a valid JSON?\n{response}\n')

    #Testing for valid JSON response
    try:
        result = json.loads(response)
        return result.get('itemUpdates', [])
    except json.JSONDecodeError:
        if verbose: create_log("DETECT_INVENTORY_CHANGES: \nInvalid JSON response for inventory updates.")
        return []

def update_inventory(game_state, item_updates, verbose=False):
    """
    Updates the inventory dictionary within game_state with item updates, using update_game_state.
    Args:
        game_state (dict): Dictionary containing game state, with 'inventory' key mapping item names to quantities.
        item_updates: List of dictionaries or a single dictionary with 'name' (str) and 'change_amount' (int).
        verbose (bool): If True, log the process. Defaults to False.
    Returns:
        None: Modifies game_state['inventory'] in place via update_game_state.    
    """
    
    if "inventory" not in game_state:
        if verbose:
            create_log('\nUPDATE_INVENTORY - Error: game_state missing inventory key\n')
        return None

    inventory = game_state["inventory"]  # Dictionary mapping items to quantities

    # Ensure item_updates is a list
    if isinstance(item_updates, dict):
        item_updates = [item_updates]  # Convert single dict to list
    elif not isinstance(item_updates, list):
        if verbose:
            create_log(f'\nUPDATE_INVENTORY - Error: item_updates must be a list or dict, got {type(item_updates)}\n')
        return None

    if verbose:
        create_log(f'\nEntering UPDATE_INVENTORY\n')
        create_log(f'\nUPDATE_INVENTORY - Initial Inventory: {inventory}\n')
        create_log(f'\nUPDATE_INVENTORY - Item Updates: {item_updates}\n')

    if not item_updates:
        if verbose:
            create_log('\nUPDATE_INVENTORY - No updates provided\n')
        return None
    
    for update in item_updates:
        if not isinstance(update, dict) or 'name' not in update or 'change_amount' not in update:
            if verbose:
                create_log(f'\nUPDATE_INVENTORY - Invalid update: {update}\n')
            continue

        name = update['name']
        change_amount = update['change_amount']
        
        if not isinstance(change_amount, int):
            if verbose:
                create_log(f'\nUPDATE_INVENTORY - Invalid change_amount in update: {update}\n')
            continue

        if change_amount == 0:
            continue
        elif change_amount > 0:
            if name not in inventory:
                inventory[name] = change_amount
            else:
                inventory[name] += change_amount
            if verbose:
                create_log(f'\nUPDATE_INVENTORY - Added {change_amount} {name} to inventory\n')
        elif change_amount < 0:
            if name in inventory:
                inventory[name] += change_amount
                if verbose:
                    create_log(f'\nUPDATE_INVENTORY - Removed {abs(change_amount)} {name} from inventory\n')
            else:
                if verbose:
                    create_log(f'\nUPDATE_INVENTORY - Cannot remove {name} (not in inventory)\n')
        
        if name in inventory and inventory[name] <= 0:
            del inventory[name]
            if verbose:
                create_log(f'\nUPDATE_INVENTORY - Item {name} removed because quantity went zero or negative: {inventory}\n')

    if verbose:
        create_log(f'\nUPDATE_INVENTORY - Final Inventory: {inventory}\n')

    # Update game_state['inventory'] using update_game_state
    update_game_state(game_state, inventory=inventory, verbose=verbose)
    
    return None

def inactive_update_inventory(inventory, item_updates): #TODO:  quando o inventario não é alterado dá erro

    if verbose:
        create_log(f'\nEntering UPDATE_INVENTORY\n')
        create_log(f'\nUPDATE_INVENTORY -Initial nventory: {inventory}\n')
        create_log(f'\nUPDATE_INVENTORY - Item Updates: {item_updates}\n')

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
        create_log(f'\nUPDATE_INVENTORY - Final Inventory: \n{inventory}\n')
    
    return update_msg #it is a string

def update_game_state(game_state, verbose=False, **updates):
    """
    Updates specific fields in the game_state dictionary in place.
    
    Example:
        update_game_state(game_state, history=["Explored cave"], output_image="new_scene.png")
    
    Args:
        game_state (dict): The game state dictionary to update.
        verbose (bool): If True, log the update process. Defaults to False.
        **updates: Keyword arguments for fields to update (e.g., history, output_image).
        world, 
        kingdom,
        town, 
        character,
        inventory, 
        output_image, 
        history
    
    Returns:
        dict: The updated game_state dictionary (same object, for convenience).
    """
    if verbose:
        create_log(f'\nEntering UPDATE_GAME_STATE\n')
        create_log(f'\nUPDATE_GAME_STATE - Initial game_state: {game_state}\n')
        create_log(f'\nUPDATE_GAME_STATE - Updates: {updates}\n')

    game_state.update(updates)

    if verbose:
        create_log(f'\nUPDATE_GAME_STATE - Final game_state: {game_state}\n')

    return game_state    

def image_generator(prompt, verbose=False):
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
        create_log(f"\nIMAGE_GENERATOR: Image {image_file_path} generated\n")

    return image_file_path

def run_action(message, game_state, verbose=verbose):
    global model, client

    system_prompt = prompts.system_prompt
    
    if verbose:
        create_log(f"Entering RUN ACTION")
        create_log(f"RUN ACTION -  inital game_state: \n{game_state}")
        create_log(f"RUN ACTION -  initial history: \n{history} \ntype: {type(history)}")
    
    # gets the world, Kingdom, Town and Character info from the game state
    world_info = get_world_info(game_state)

    if game_state[history]:
        summ_history =  summarize(prompts.summarize_prompt_template,game_state[history])
    else:
        if verbose: create_log("RUN ACTION - invalid history entry")
        summ_history = ""
    
    message_prompt = prompts.prompt_template + message

    local_messages = [
        {"role": "system", "content": system_prompt},
        {"role": "assistant", "content": world_info},
        {"role": "assistant", "content": summ_history},
        {"role": "user", "content": prompts.prompt_template + message}
    ]

    response = client.chat.completions.create(
        model=model, 
        messages=local_messages)

    result = response.choices[0].message.content

    generated_image_path = image_generator(result, verbose=verbose)
    # temporary stop image generation just for test
    #generated_image_path = "Test_output_image_2025-04-28_10-22-12"
    
    local_messages.append({"role": "assistant", "content": result})

    item_updates = detect_inventory_changes(game_state, result, verbose=verbose)

    update_inventory( game_state, item_updates, verbose=verbose )

    update_game_state(game_state, output_image=generated_image_path, history=local_messages, verbose=verbose)

    if verbose:
        create_log(f"\nRUN ACTION - Question:\n{message}\n")
        create_log(f"\nRUN ACTION - Response:\n{message}\n")
        create_log(f"RUN ACTION -  final game_state: \n{game_state}")
        create_log(f"RUN ACTION -  final history: \n{history} \ntype: {type(history)}")

    return game_state

def inactive_main_loop(message, history, game_state):
    return output, generated_image_path

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


