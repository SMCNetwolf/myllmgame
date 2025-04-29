import base64
import json
import datetime
import os
import re
from copy import deepcopy
from dotenv import dotenv_values
from together import Together
import prompts
from create_log import verbose, create_log


# Load API key from .env file
env_vars = dotenv_values('.env')
together_api_key = env_vars.get('TOGETHER_API_KEY')
if not together_api_key:
    raise ValueError("TOGETHER_API_KEY not found in .env file")
client = Together(api_key=together_api_key)

# Configuration
MODEL = "meta-llama/Llama-3-70b-chat-hf"
IMAGE_MODEL = "black-forest-labs/FLUX.1-schnell-Free"
DEFAULT_IMAGE_FILE_PATH = os.path.join('static', 'default_image.png')
IMAGE_FILE_PREFIX = os.path.join('static/image', 'output_image')  # No .png extension
WORLD_PATH = os.path.join('.', 'SeuMundo_L1.json')
SAVE_GAMES_PATH = 'game_saves'

def validate_world(world):
    """Validates the structure of the world JSON file.

    Args:
        world (dict): The loaded world JSON data.

    Raises:
        ValueError: If required keys or structure are missing.
    """
    required_keys = ['name', 'description', 'kingdoms']
    for key in required_keys:
        if key not in world:
            raise ValueError(f"Missing key {key} in world JSON")
    if 'Eldrida' not in world['kingdoms']:
        raise ValueError("Kingdom 'Eldrida' missing in world JSON")
    if 'towns' not in world['kingdoms']['Eldrida']:
        raise ValueError("Towns missing in Eldrida kingdom")
    if 'Luminaria' not in world['kingdoms']['Eldrida']['towns']:
        raise ValueError("Town 'Luminaria' missing in Eldrida towns")
    if 'npcs' not in world['kingdoms']['Eldrida']['towns']['Luminaria']:
        raise ValueError("NPCs missing in Luminaria town")
    if 'Eira Shadowglow' not in world['kingdoms']['Eldrida']['towns']['Luminaria']['npcs']:
        raise ValueError("NPC 'Eira Shadowglow' missing in Luminaria NPCs")

def load_world(filename):
    """Loads the world JSON file and validates its structure.

    Args:
        filename (str): Path to the JSON file.

    Returns:
        dict: The loaded and validated world data.

    Raises:
        FileNotFoundError: If the file does not exist.
        json.JSONDecodeError: If the file contains invalid JSON.
        ValueError: If the JSON structure is invalid.
    """
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            world = json.load(f)
        validate_world(world)
        if verbose:
            create_log(f"\n\nLoaded world {world['name']}\n\n")
        return world
    except FileNotFoundError:
        create_log(f"Error: File {filename} not found")
        raise
    except json.JSONDecodeError:
        create_log(f"Error: Invalid JSON in {filename}")
        raise

def get_world_info(game_state): #TODO: Verify if History and achievements are necessary here
    """Generates a formatted string with game state information.

    Args:
        game_state (dict): The current game state.

    Returns:
        str: Formatted string with world, kingdom, town, character, and inventory info.
    """
    

    return f"""
        World: \n{game_state['world']}\n
        Kingdom: \n{game_state['kingdom']}\n
        Town: \n{game_state['town']}\n
        Your Character: \n{game_state['character']}\n
        Your Inventory: \n{game_state['inventory']}\n
    """

def get_initial_game_state():
    """Creates a new initial game state dictionary.

    Returns:
        dict: A deep copy of the initial game state.
    """

    initial_history_text =  f"No mundo de Arkonix, as cidades são construídas sobre as costas \
        de enormes criaturas chamadas Leviatãs, que vagam pelo mundo como montanhas vivas. \
        Eldrida é um reino de florestas eternas, liderado pela rainha Lyra, protege a natureza \
        e seus habitantes. Sua capital, Luminária, construída sobre o Leviatã Estrela da Manhã, \
        é conhecida por suas ruas iluminadas por lanternas mágicas que refletem a luz dos olhos do Leviatã."
    
    # Load world data
    world = load_world(WORLD_PATH)

    initial_kingdom = world['kingdoms']['Eldrida']
    initial_town = initial_kingdom['towns']['Luminaria']
    initial_character = initial_town['npcs']['Eira Shadowglow']
    start_image_prompt = world['description']
  
    initial_inventory = {
        "calça de pano": 1,
        "armadura de couro": 1,
        "camisa de pano": 1,
        "lente de prata": 1,
        "livro de magia": 1,
        "livro de aventura": 1,
        "livro guia do local": 1,
        "gold": 5
    }

    initial_game_state = {
        "world": world['description'],
        "kingdom": initial_kingdom['description'],
        "town": initial_town['description'],
        "character": initial_character['description'],
        "inventory": initial_inventory,
        "achievements": "",
        "output_image": DEFAULT_IMAGE_FILE_PATH,
        "history": [{"role": "assistant", "content":initial_history_text}]
    }
    return initial_game_state #deepcopy(initial_game_state)

def format_chat_history(history):
    """Format chat history to include only user questions and assistant answers.

    Args:
        history (list): List of message dictionaries with 'role' and 'content'.

    Returns:
        str: Formatted string containing only user and assistant messages.
    """
    formatted_history = ""
    for entry in history:
        role = entry["role"]
        content = entry["content"].strip()
        if role in ("user", "assistant") and content and content != world['description']:
            formatted_history += f"{role.capitalize()}: {content}\n"
    return formatted_history

def is_safe(message):
    """Checks if a message is safe using LlamaGuard.

    Args:
        message (str): The message to check.

    Returns:
        bool: True if the message is safe, False otherwise.

    Raises:
        ValueError: If everyone_content_policy is not defined in prompts.
        Exception: If the API call fails.
    """
    try:
        # Assume everyone_content_policy is defined in prompts
        if not hasattr(prompts, 'get_is_safe_prompt') or not hasattr(prompts, 'everyone_content_policy'):
            raise ValueError("everyone_content_policy or get_is_safe_prompt not defined in prompts")
        prompt = prompts.get_is_safe_prompt(prompts.everyone_content_policy)
        response = client.completions.create(
            model="Meta-Llama/LlamaGuard-2-8b",
            prompt=prompt.format(message=message)
        )
        result = response.choices[0].text.strip()
        return result == 'safe'
    except Exception as e:
        create_log(f"Error in is_safe: {str(e)}")
        return False  # Default to unsafe on error

def summarize(template, prompt, verbose=False):
    """Summarizes text using the specified model.

    Args:
        template (str): The prompt template.
        prompt (str): The text to summarize.

    Returns:
        str: The summarized text.

    Raises:
        Exception: If the API call fails.
    """
    try:
        final_prompt = template + prompt
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": final_prompt}]
        )
        if verbose:
            create_log(f"\nSUMMARIZE - Summarized text: \n{response.choices[0].message.content}\n\n")
        return response.choices[0].message.content
    except Exception as e:
        create_log(f"Error in summarize: {str(e)}")
        return ""

def detect_inventory_changes(game_state, last_response, verbose=False):
    """Detects inventory changes based on the latest story response.

    Args:
        game_state (dict): The current game state.
        last_response (str): The latest story response.
        verbose (bool): If True, log the process. Defaults to False.

    Returns:
        list: List of item updates (dictionaries with 'name' and 'change_amount').
    """
    try:
        inventory = game_state['inventory']
        messages = [
            {"role": "system", "content": prompts.system_inventory_prompt},
            {"role": "user", "content": f'Current Inventory: {str(inventory)}'},
            {"role": "user", "content": f'Recent Story: {last_response}'}
        ]
        chat_completion = client.chat.completions.create(
            model=MODEL,
            temperature=0.0,
            messages=messages
        )
        response = chat_completion.choices[0].message.content
        if verbose:
            create_log(f'\nDETECT_INVENTORY_CHANGES: Response:\n{response}\n')
        try:
            result = json.loads(response)
            return result.get('itemUpdates', [])
        except json.JSONDecodeError:
            if verbose:
                create_log("DETECT_INVENTORY_CHANGES: Invalid JSON response")
            return []
    except Exception as e:
        if verbose:
            create_log(f"Error in detect_inventory_changes: {str(e)}")
        return []

def update_inventory(game_state, item_updates, verbose=False):
    """Updates the inventory in game_state based on item updates.

    Args:
        game_state (dict): The current game state.
        item_updates: List of dicts or single dict with 'name' and 'change_amount'.
        verbose (bool): If True, log the process. Defaults to False.

    Returns:
        None: Modifies game_state['inventory'] in place.
    """
    if 'inventory' not in game_state:
        if verbose:
            create_log('\nUPDATE_INVENTORY - Error: game_state missing inventory key\n')
        return
    inventory = game_state['inventory']
    if isinstance(item_updates, dict):
        item_updates = [item_updates]
    elif not isinstance(item_updates, list):
        if verbose:
            create_log(f'\nUPDATE_INVENTORY - Error: item_updates must be list or dict, got {type(item_updates)}\n')
        return
    if verbose:
        create_log(f'\nUPDATE_INVENTORY - Initial Inventory: {inventory}\n')
        create_log(f'\nUPDATE_INVENTORY - Item Updates: {item_updates}\n')
    if not item_updates:
        if verbose:
            create_log('\nUPDATE_INVENTORY - No updates provided\n')
        return
    for update in item_updates:
        if not isinstance(update, dict) or 'name' not in update or 'change_amount' not in update:
            if verbose:
                create_log(f'\nUPDATE_INVENTORY - Invalid update: {update}\n')
            continue
        name = update['name']
        change_amount = update['change_amount']
        if not isinstance(change_amount, int):
            if verbose:
                create_log(f'\nUPDATE_INVENTORY - Invalid change_amount: {update}\n')
            continue
        if change_amount == 0:
            continue
        elif change_amount > 0:
            inventory[name] = inventory.get(name, 0) + change_amount
            if verbose:
                create_log(f'\nUPDATE_INVENTORY - Added {change_amount} {name}\n')
        elif change_amount < 0 and name in inventory:
            inventory[name] += change_amount
            if verbose:
                create_log(f'\nUPDATE_INVENTORY - Removed {abs(change_amount)} {name}\n')
        if name in inventory and inventory[name] <= 0:
            del inventory[name]
            if verbose:
                create_log(f'\nUPDATE_INVENTORY - Removed {name} (quantity <= 0)\n')
    if verbose:
        create_log(f'\nUPDATE_INVENTORY - Final Inventory: {inventory}\n')
    update_game_state(game_state, inventory=inventory, verbose=verbose)

def update_game_state(game_state, verbose=False, **updates):
    """Updates specific fields in the game_state dictionary.

    Args:
        game_state (dict): The game state dictionary to update.
        verbose (bool): If True, log the update process. Defaults to False.
        **updates: Keyword arguments for fields to update (e.g., history, output_image).

    Returns:
        dict: The updated game_state dictionary.
    """
    if verbose:
        create_log(f'\nUPDATE_GAME_STATE - Initial game_state: {game_state}\n')
        create_log(f'\nUPDATE_GAME_STATE - Updates: {updates}\n')
    game_state.update(updates)
    if verbose:
        create_log(f'\nUPDATE_GAME_STATE - Final game_state: {game_state}\n')
    return game_state

def image_generator(prompt, verbose=False):
    """Generates an image based on a prompt and saves it.

    Args:
        prompt (str): The image generation prompt.
        verbose (bool): If True, log the process. Defaults to False.

    Returns:
        str: Path to the generated image file.
    """
    try:
        response = client.images.generate(
            prompt=prompt,
            model=IMAGE_MODEL,
            width=512,
            height=384,
            steps=1,
            n=1,
            response_format="b64_json"
        )
        image_data = base64.b64decode(response.data[0].b64_json)
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        image_file_path = f"{IMAGE_FILE_PREFIX}_{timestamp}.png"
        os.makedirs(os.path.dirname(image_file_path), exist_ok=True)
        with open(image_file_path, 'wb') as f:
            f.write(image_data)
        if verbose:
            create_log(f"\nIMAGE_GENERATOR: Generated {image_file_path}\n")
        return image_file_path
    except Exception as e:
        if verbose:
            create_log(f"Error in image_generator: {str(e)}")
        return DEFAULT_IMAGE_FILE_PATH

def run_action(message, game_state, verbose=False):
    """Processes a user action and updates the game state.

    Args:
        message (str): The user's action input.
        game_state (dict): The current game state.
        verbose (bool): If True, log the process. Defaults to False.

    Returns:
        dict: The updated game_state.
    """
    try:
        if verbose:
            create_log(f"\nRUN_ACTION - Initial game_state: \n{game_state}\n")
            create_log(f"\nRUN_ACTION - Initial history: \n{game_state['history']}\n")
        world_info = get_world_info(game_state)
        summ_history = ""
        str_history =  " ".join([str(message['content']) for message in game_state['history']]) 
        if len(str_history)>600:
            summ_history = summarize(prompts.summarize_prompt_template, str_history)
            if verbose:
                create_log(f"\nRUN_ACTION - Summarized history: \n{summ_history}\n")
        else:
            summ_history = str_history
            if verbose:
                create_log("RUN_ACTION - History not summarized")
        message_prompt = prompts.prompt_template + message
        local_messages = [
            {"role": "system", "content": prompts.system_prompt},
            {"role": "assistant", "content": world_info},
            {"role": "assistant", "content": summ_history},
            {"role": "user", "content": message_prompt}
        ]
        response = client.chat.completions.create(
            model=MODEL,
            messages=local_messages
        )
        result = response.choices[0].message.content
        generated_image_path = image_generator(result, verbose=verbose)
        local_messages.append({"role": "assistant", "content": result})
        item_updates = detect_inventory_changes(game_state, result, verbose=verbose)
        update_inventory(game_state, item_updates, verbose=verbose)
        updated_history = [{"role": "user", "content": message},{"role": "assistant", "content": result}]
        update_game_state(
            game_state,
            output_image=generated_image_path,
            history=updated_history,
            verbose=verbose
        )
        if verbose:
            create_log(f"\nRUN_ACTION - Question: {message}\n")
            create_log(f"\nRUN_ACTION - Response: {result}\n")
            create_log(f"\nRUN_ACTION - Final game_state: \n{game_state}\n")
        return result
    except Exception as e:
        if verbose:
            create_log(f"Error in run_action: {str(e)}")
        return "Error in run_action - Something went wrong."



def save_game(game_state, verbose=False):
    """Saves the game state and chatbot history to a JSON file.

    Args:
        history (list): The chatbot conversation history.
        game_state (dict): The current game state.

    Returns:
        None
    """
    try:
        os.makedirs('game_saves', exist_ok=True)
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        save_path = os.path.join('game_saves', f"{timestamp}.json")
        save_data = {
            'game_state': game_state
        }
        with open(save_path, 'w', encoding='utf-8') as f:
            json.dump(save_data, f, ensure_ascii=False, indent=4)
        if verbose:
            create_log(f"SAVE_GAME: Game saved to {save_path}")
    except Exception as e:
        create_log(f"SAVE_GAME: Error in save_game: {str(e)}")

def confirm_save(filename, game_state, verbose=False):
    """Saves the game with a user-specified filename.

    Args:
        filename (str): The desired filename (without .json).
        game_state (dict): The current game state.

    Returns:
        None
    """
    if not filename.strip():
        create_log("CONFIRM_SAVE: Error: Empty filename")
        return
    try:
        # Sanitize filename
        filename = re.sub(r'[^\w\-]', '', filename.strip())
        if not filename:
            create_log("CONFIRM_SAVE: Error: Invalid filename after sanitization")
            return
        os.makedirs('game_saves', exist_ok=True)
        save_path = os.path.join('game_saves', f"{filename}.json")
        save_data = {
            'game_state': game_state
        }
        with open(save_path, 'w', encoding='utf-8') as f:
            json.dump(save_data, f, ensure_ascii=False, indent=4)
        if verbose:
            create_log(f"CONFIRM_SAVE: Game saved to {save_path}")
    except Exception as e:
        create_log(f"CONFIRM_SAVE: Error in confirm_save: {str(e)}")

def retrieve_game_list(verbose=False):
    """Lists available game save files.

    Returns:
        dict: Dictionary with save file choices or empty if none exist.
    """
    try:
        if not os.path.exists('game_saves'):
            return {"choices": [], "value": None, "visible": False}
        save_files = [f for f in os.listdir('game_saves') if f.endswith('.json')]
        return {"choices": save_files, "value": None, "visible": bool(save_files)}
        if verbose:
            create_log(f"RETRIEVE_GAME_LIST: Found {len(save_files)} \nsave files: {save_files}")
    except Exception as e:
        create_log(f"RETRIEVE_GAME_LIST: Error in trying to list saved games: {str(e)}")
        return {"choices": [], "value": None, "visible": False}

def retrieve_game(selected_file, verbose=False):
    """Loads a saved game state.

    Args:
        selected_file (str): The name of the save file to load.

    Returns:
        game_state
    """
    if not selected_file:
        if verbose:
            create_log("CONFIRM_RETRIEVE: No file selected. Returning initial game state.")
        return get_initial_game_state()
    try:
        retrieve_path = os.path.join(SAVE_GAMES_PATH, selected_file)
        with open(retrieve_path, 'r', encoding='utf-8') as f:
            save_data = json.load(f)
        return (
            save_data.get('game_state')
        )
    except Exception as e:
        create_log(f"CONFIRM_RETRIEVE: Error {str(e)} Returning initial game state.")
        return get_initial_game_state()
