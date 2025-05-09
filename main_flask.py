import base64
import json
import datetime
import os
import re
import glob
import time
import sqlite3
from flask import session
from together import Together
from copy import deepcopy
from create_log import create_log
from dotenv import load_dotenv
import prompts
from google.cloud import storage

from config import VERBOSE

# Load environment variables
load_dotenv()
together_api_key = os.environ.get('TOGETHER_API_KEY')
if not together_api_key:
    raise ValueError("TOGETHER_API_KEY not found in .env file")
    create_log("TOGETHER_API_KEY not found in .env file")
client = Together(api_key=together_api_key)

GCS_BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME")
if not GCS_BUCKET_NAME:
    create_log("GCS_BUCKET_NAME not found in .env file")
    raise ValueError("GCS_BUCKET_NAME not found in .env file")

# Initialize GCS client
storage_client = storage.Client()
bucket = storage_client.bucket(GCS_BUCKET_NAME)

# Configuration
MODEL = "meta-llama/Llama-3-70b-chat-hf"
IMAGE_MODEL = "black-forest-labs/FLUX.1-schnell-Free"
INITIAL_IMAGE_FILE_PATH = os.path.join('static', 'default_image.png')
DEFAULT_IMAGE_FILE_PATH = "static/image/output_image.png"
DEFAULT_AUDIO_FILE_PATH = os.path.join('static/audio', 'default_audio.mp3')
IMAGE_FILE_PREFIX = os.path.join('static/image', 'output_image')
WORLD_PATH = os.path.join('.', 'SeuMundo_L1.json')
SAVE_GAMES_PATH = 'game_saves'
DB_PATH = os.path.join('database', 'users.db')
MAX_SAVE = 5  # Maximum number of saved games per user

last_saved_history = None

def upload_db_to_gcs(verbose=False):
    """Upload database/users.db to GCS."""
    try:
        blob = bucket.blob("database/users.db")
        blob.upload_from_filename(DB_PATH)
        if VERBOSE:
            create_log(f"UPLOAD_DB_TO_GCS: Uploaded {DB_PATH} to gs://{GCS_BUCKET_NAME}/database/users.db")
    except Exception as e:
        create_log(f"UPLOAD_DB_TO_GCS: Error uploading database to GCS: {str(e)}")
        raise

def download_db_from_gcs(verbose=False):
    """Download users.db from GCS to database/users.db."""
    try:
        blob = bucket.blob("database/users.db")
        if blob.exists():
            os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
            blob.download_to_filename(DB_PATH)
            if VERBOSE:
                create_log(f"DOWNLOAD_DB_FROM_GCS: Downloaded gs://{GCS_BUCKET_NAME}/database/users.db to {DB_PATH}")
        else:
            if VERBOSE:
                create_log(f"DOWNLOAD_DB_FROM_GCS: No users.db found in GCS bucket {GCS_BUCKET_NAME}")
    except Exception as e:
        create_log(f"DOWNLOAD_DB_FROM_GCS: Error downloading database from GCS: {str(e)}")
        raise

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def validate_world(world):
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
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            world = json.load(f)
        validate_world(world)
        if VERBOSE:
            create_log(f"LOAD_WORLD: Loaded world {world['name']}")
        return world
    except FileNotFoundError:
        create_log(f"Error: File {filename} not found")
        raise
    except json.JSONDecodeError:
        create_log(f"Error: Invalid JSON in {filename}")
        raise

def get_world_info(game_state):
    return f"""
        World: \n{game_state['world']}\n
        Kingdom: \n{game_state['kingdom']}\n
        Town: \n{game_state['town']}\n
        NPCs: \n{game_state['npcs']}\n
        Your Character: \n{game_state['character']}\n
        Your Inventory: \n{game_state['inventory']}\n
    """

def validate_game_state(game_state, verbose=False):
    required_keys = ['world', 'kingdom', 'town', 'npcs', 'character', 'inventory', 'achievements', 'output_image', 'ambient_sound', 'history']
    for key in required_keys:
        if key not in game_state:
            if VERBOSE:
                create_log(f"VALIDATE_GAME_STATE: Missing key {key} in world JSON")
            return False
    if VERBOSE:
        create_log(f"VALIDATE_GAME_STATE: Game state is valid")
    return True

def get_initial_game_state(verbose=False):
    if VERBOSE:
        create_log("GET_INITIAL_GAME_STATE: Creating initial game state")
    
    initial_history_text = f"No mundo de Arkonix, as cidades são construídas sobre as costas \
        de enormes criaturas chamadas Leviatãs, que vagam pelo mundo como montanhas vivas. \
        Eldrida é um reino de florestas eternas, liderado pela rainha Lyra, protege a natureza \
        e seus habitantes. Sua capital, Luminária, construída sobre o Leviatã Estrela da Manhã, \
        é conhecida por suas ruas iluminadas por lanternas mágicas que refletem a luz dos olhos do Leviatã. \
        Você pode perguntar ao mestre do jogo qualquer coisa, por exemplo: O QUE TENHO AQUI COMIGO?"
    
    world = load_world(WORLD_PATH)
    initial_kingdom = world['kingdoms']['Eldrida']
    initial_town = initial_kingdom['towns']['Luminaria']
    initial_npcs = initial_town['npcs']
    initial_character = initial_town['npcs']['Eira Shadowglow']
    
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
        "npcs": initial_npcs,
        "character": initial_character['name'],
        "inventory": initial_inventory,
        "achievements": "",
        "output_image": INITIAL_IMAGE_FILE_PATH,
        "ambient_sound": DEFAULT_AUDIO_FILE_PATH,
        "history": [{"role": "assistant", "content": initial_history_text}]
    }
    if VERBOSE:
        create_log(f"GET_INITIAL_GAME_STATE: Successfully created initial game state")
    return initial_game_state

def load_temp_game_state(verbose=False):
    temp_save_path = 'temp_saves/last_session.json'
    try:
        if os.path.exists(temp_save_path):
            with open(temp_save_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                game_state = data.get('game_state')
                if validate_game_state(game_state):
                    if VERBOSE:
                        create_log(f"LOAD_TEMP_GAME_STATE: Loaded game state from {temp_save_path}")
                    return game_state
                else:
                    if VERBOSE:
                        create_log(f"LOAD_TEMP_GAME_STATE: Invalid game state in {temp_save_path}")
        else:
            if VERBOSE:
                create_log(f"LOAD_TEMP_GAME_STATE: No temp save file found at {temp_save_path}")
    except Exception as e:
        if VERBOSE:
            create_log(f"LOAD_TEMP_GAME_STATE: Error loading temp game state: {str(e)}")
    return None

def format_chat_history(history, game_state):
    character_name = game_state['character'].split()[0]
    formatted_messages = []
    for msg in history:
        if msg['role'] == 'user':
            role = character_name
        elif msg['role'] == 'assistant':
            role = 'Mestre do Jogo'
        formatted_messages.append(f"{role}: {msg['content']}")
    return "\n\n".join(formatted_messages)

def is_safe(message):
    try:
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
        return False

def summarize(template, prompt, verbose=False):
    try:
        final_prompt = template + prompt
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": final_prompt}]
        )
        if VERBOSE:
            create_log(f"\nSUMMARIZE - Summarized text: \n{response.choices[0].message.content}\n\n")
        return response.choices[0].message.content
    except Exception as e:
        create_log(f"Error in summarize: {str(e)}")
        return ""

def detect_inventory_changes(game_state, last_response, verbose=False):
    int_verbose = False #verbose
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
        if int_verbose:
            create_log(f'\nDETECT_INVENTORY_CHANGES: Response:\n{response}\n')
        try:
            result = json.loads(response)
            return result.get('itemUpdates', [])
        except json.JSONDecodeError:
            create_log("DETECT_INVENTORY_CHANGES: Invalid JSON response")
            return []
    except Exception as e:
        create_log(f"Error in detect_inventory_changes: {str(e)}")
        return []

def update_inventory(game_state, item_updates, verbose=False):
    int_verbose = False #verbose
    if 'inventory' not in game_state:
        if int_verbose:
            create_log('\nUPDATE_INVENTORY - Error: game_state missing inventory key\n')
        return
    inventory = game_state['inventory']
    if isinstance(item_updates, dict):
        item_updates = [item_updates]
    elif not isinstance(item_updates, list):
        if int_verbose:
            create_log(f'\nUPDATE_INVENTORY - Error: item_updates must be list or dict, got {type(item_updates)}\n')
        return
    if int_verbose:
        create_log(f'\nUPDATE_INVENTORY - Initial Inventory: {inventory}\n')
        create_log(f'\nUPDATE_INVENTORY - Item Updates: {item_updates}\n')
    if not item_updates:
        if int_verbose:
            create_log('\nUPDATE_INVENTORY - No updates provided\n')
        return
    for update in item_updates:
        if not isinstance(update, dict) or 'name' not in update or 'change_amount' not in update:
            if int_verbose:
                create_log(f'\nUPDATE_INVENTORY - Invalid update: {update}\n')
            continue
        name = update['name']
        change_amount = update['change_amount']
        if not isinstance(change_amount, int):
            if int_verbose:
                create_log(f'\nUPDATE_INVENTORY - Invalid change_amount: {update}\n')
            continue
        if change_amount == 0:
            continue
        elif change_amount > 0:
            inventory[name] = inventory.get(name, 0) + change_amount
            if int_verbose:
                create_log(f'\nUPDATE_INVENTORY - Added {change_amount} {name}\n')
        elif change_amount < 0 and name in inventory:
            inventory[name] += change_amount
            if int_verbose:
                create_log(f'\nUPDATE_INVENTORY - Removed {abs(change_amount)} {name}\n')
        if name in inventory and inventory[name] <= 0:
            del inventory[name]
            if int_verbose:
                create_log(f'\nUPDATE_INVENTORY - Removed {name} (quantity <= 0)\n')
    if int_verbose:
        create_log(f'\nUPDATE_INVENTORY - Final Inventory: {inventory}\n')
    update_game_state(game_state, inventory=inventory, verbose=VERBOSE)

def update_game_state(game_state, verbose=False, **updates):
    if VERBOSE:
        create_log(f'\nUPDATE_GAME_STATE - Updating game_state\n')
        #create_log(f'\nUPDATE_GAME_STATE - Initial game_state: {game_state}\n')
        #create_log(f'\nUPDATE_GAME_STATE - Updates: {updates}\n')
    game_state.update(updates)
    if VERBOSE:
        create_log(f'\nUPDATE_GAME_STATE - Updated game_state\n')
        #create_log(f'\nUPDATE_GAME_STATE - Final game_state: {game_state}\n')
    return game_state

def image_generator(prompt, verbose=False):
    """Generate an image, save locally as same_image.png, and upload to GCS with timestamp."""
    try:
        response = client.images.generate(
            prompt=prompt,
            model=IMAGE_MODEL,
            width=512, #former 512  384   256
            height=384, #former 384  288   192
            steps=1,
            n=1,
            response_format="b64_json"
        )
        image_data = base64.b64decode(response.data[0].b64_json)
        os.makedirs(os.path.dirname(DEFAULT_IMAGE_FILE_PATH), exist_ok=True)
        
        # Save image locally as same_image.png (overwrite)
        with open(DEFAULT_IMAGE_FILE_PATH, 'wb') as f:
            f.write(image_data)
        
        # Upload image to GCS with timestamp
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        gcs_path = f"{DEFAULT_IMAGE_FILE_PATH.split('.png')[0]}_{timestamp}.png"
        try:
            blob = bucket.blob(gcs_path)
            blob.upload_from_filename(DEFAULT_IMAGE_FILE_PATH)
            if VERBOSE:
                create_log(f"IMAGE_GENERATOR: Uploaded {DEFAULT_IMAGE_FILE_PATH} to gs://{os.environ.get('GCS_BUCKET_NAME')}/{gcs_path}")
        except Exception as e:
            create_log(f"IMAGE_GENERATOR: Error uploading {DEFAULT_IMAGE_FILE_PATH} to GCS: {str(e)}")
            raise
        
        if VERBOSE:
            create_log(f"IMAGE_GENERATOR: Generated and saved {DEFAULT_IMAGE_FILE_PATH}")
        return DEFAULT_IMAGE_FILE_PATH
    except Exception as e:
        if VERBOSE:
            create_log(f"IMAGE_GENERATOR: Error generating image: {str(e)}")
        return DEFAULT_IMAGE_FILE_PATH

def run_action(message, game_state, verbose=False):
    try:
        '''
        if VERBOSE:
            create_log(f"\nRUN_ACTION - Initial game_state: \n{game_state}\n")
            create_log(f"\nRUN_ACTION - Initial history: \n{game_state['history']}\n")
        '''
        world_info = get_world_info(game_state)
        summ_history = ""
        str_history = " ".join([str(message['content']) for message in game_state['history']])
        if len(str_history) > 600:
            summ_history = summarize(prompts.summarize_prompt_template, str_history)
            if VERBOSE:
                create_log(f"\nRUN_ACTION - Summarized history: \n{summ_history}\n")
        else:
            summ_history = str_history
            if VERBOSE:
                create_log("RUN_ACTION - History not summarized")
        message_prompt = prompts.prompt_template + f"n{summ_history}\n" + \
            f"*** Pergunta do usuário: \n{game_state['inventory']}\n" + \
            f"*** Pergunta do usuário: \n{message}\n\n"
        if VERBOSE:
            create_log(f"\nRUN_ACTION - Message prompt: \n{message_prompt}\n")
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
       #create_log(f"\nRUN_ACTION - Question: {message}\n")
        #create_log(f"\nRUN_ACTION - Assistant response: \n{result}\n")
        generated_image_path = image_generator(result, verbose=VERBOSE)
        local_messages.append({"role": "assistant", "content": result})
        item_updates = detect_inventory_changes(game_state, result, verbose=VERBOSE)
        update_inventory(game_state, item_updates, verbose=VERBOSE)
        updated_history = game_state['history'] + [{"role": "user", "content": message}, {"role": "assistant", "content": result}]
        update_game_state(
            game_state,
            output_image=generated_image_path,
            history=updated_history,
            verbose=VERBOSE
        )
        '''
        if VERBOSE:
            create_log(f"\nRUN_ACTION - Question: {message}\n")
            create_log(f"\nRUN_ACTION - Final game_state: \n{game_state}\n")
        '''
        return result
    except Exception as e:
        create_log(f"Error in run_action: {str(e)}")
        return "Error in run_action - Something went wrong."

def save_temp_game_state(game_state, verbose=False):
    global last_saved_history
    if last_saved_history != game_state['history']:
        try:
            os.makedirs('temp_saves', exist_ok=True)
            temp_save_path = 'temp_saves/last_session.json'
            with open(temp_save_path, 'w', encoding='utf-8') as f:
                json.dump({'game_state': game_state}, f, ensure_ascii=False, indent=4)
            last_saved_history = game_state['history']
            if VERBOSE:
                create_log(f"SAVE_TEMP_GAME_STATE: Saved game state to {temp_save_path}")
        except Exception as e:
            create_log(f"SAVE_TEMP_GAME_STATE: Error saving temp game state: {str(e)}")

def old_confirm_save(filename, game_state, user_id, verbose=False):
    if not filename or not filename.strip():
        if VERBOSE:
            create_log("CONFIRM_SAVE: Error: Empty filename")
        raise ValueError("Filename cannot be empty")
    
    filename = re.sub(r'[^\w\-]', '', filename.strip())
    if not filename:
        if VERBOSE:
            create_log("CONFIRM_SAVE: Error: Invalid filename after sanitization")
        raise ValueError("Invalid filename")
    
    if not os.path.exists(DB_PATH):
        if VERBOSE:
            create_log(f"CONFIRM_SAVE: Error: Database file {DB_PATH} does not exist")
        raise ValueError(f"Database file {DB_PATH} does not exist")

    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            # Count existing saves (excluding autosave)
            c.execute("SELECT COUNT(*) FROM game_states WHERE user_id = ? AND game_name != 'autosave'", (user_id,))
            save_count = c.fetchone()[0]
            
            # Check if save limit is reached
            if save_count >= MAX_SAVE:
                if VERBOSE:
                    create_log(f"CONFIRM_SAVE: Error: Maximum save limit ({MAX_SAVE}) reached for user {user_id}")
                raise ValueError(f"Cannot save game: Maximum of {MAX_SAVE} saved games allowed.")
            
            # Save the game (INSERT OR REPLACE to overwrite if the filename exists)
            c.execute("INSERT OR REPLACE INTO game_states (user_id, game_name, game_state, created_at) VALUES (?, ?, ?, ?)",
                      (user_id, filename, json.dumps(game_state), time.strftime('%Y-%m-%d %H:%M:%S')))
            conn.commit()
            if VERBOSE:
                create_log(f"CONFIRM_SAVE: Game saved (or overwritten) for user {user_id} as {filename}")
    except Exception as e:
        if VERBOSE:
            create_log(f"CONFIRM_SAVE: Error saving game: {str(e)}")
        raise  # Re-raise the exception to propagate it to the caller

def confirm_save(filename, game_state, user_id, verbose=False):
    if not filename or not filename.strip():
        if VERBOSE:
            create_log("CONFIRM_SAVE: Error: Empty filename")
        raise ValueError("Filename cannot be empty")
    
    filename = re.sub(r'[^\w\-]', '', filename.strip())
    if not filename:
        if VERBOSE:
            create_log("CONFIRM_SAVE: Error: Invalid filename after sanitization")
        raise ValueError("Invalid filename")
    
    if not os.path.exists(DB_PATH):
        if VERBOSE:
            create_log(f"CONFIRM_SAVE: Error: Database file {DB_PATH} does not exist")
        raise ValueError(f"Database file {DB_PATH} does not exist")
    
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM game_states WHERE user_id = ? AND game_name != 'autosave'", (user_id,))
            save_count = c.fetchone()[0]
            
            if save_count >= MAX_SAVE:
                if VERBOSE:
                    create_log(f"CONFIRM_SAVE: Error: Maximum save limit ({MAX_SAVE}) reached for user {user_id}")
                raise ValueError(f"Cannot save game: Maximum of {MAX_SAVE} saved games allowed.")
            
            c.execute("INSERT OR REPLACE INTO game_states (user_id, game_name, game_state, created_at) VALUES (?, ?, ?, ?)",
                      (user_id, filename, json.dumps(game_state), time.strftime('%Y-%m-%d %H:%M:%S')))
            conn.commit()
            if VERBOSE:
                create_log(f"CONFIRM_SAVE: Game saved (or overwritten) for user {user_id} as {filename}")
        
        # Upload database to GCS
        upload_db_to_gcs(verbose=VERBOSE)
        if VERBOSE:
            create_log("CONFIRM_SAVE: Database uploaded to GCS")
    except Exception as e:
        create_log(f"CONFIRM_SAVE: Error saving game: {str(e)}")
        raise

def retrieve_game_list(user_id, verbose=False):
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT game_name FROM game_states WHERE user_id = ?", (user_id,))
            save_files = [row['game_name'] for row in c.fetchall()]
            if VERBOSE:
                create_log(f"RETRIEVE_GAME_LIST: Found {len(save_files)} save files for user {user_id}: {save_files}")
            return {"choices": save_files, "value": None, "visible": bool(save_files)}
    except Exception as e:
        if VERBOSE:
            create_log(f"RETRIEVE_GAME_LIST: Error listing saved games: {str(e)}")
        return {"choices": [], "value": None, "visible": False}

def retrieve_game(selected_file, user_id, verbose=False):
    if not selected_file or not selected_file.strip():
        if VERBOSE:
            create_log("RETRIEVE_GAME: Error: No file selected")
        raise ValueError("No file selected")
    
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT game_state FROM game_states WHERE user_id = ? AND game_name = ?", (user_id, selected_file))
            row = c.fetchone()
            if not row:
                if VERBOSE:
                    create_log(f"RETRIEVE_GAME: Error: Game {selected_file} not found for user {user_id}")
                raise ValueError("Selected save file does not exist")
            
            game_state = json.loads(row['game_state'])
            if not validate_game_state(game_state, verbose=VERBOSE):
                if VERBOSE:
                    create_log("RETRIEVE_GAME: Error: Invalid game state")
                raise ValueError("Invalid save file: No game state found")
            
            if VERBOSE:
                create_log(f"RETRIEVE_GAME: Loaded game {selected_file} for user {user_id}")
            return game_state
    except Exception as e:
        if VERBOSE:
            create_log(f"RETRIEVE_GAME: Error loading game: {str(e)}")
        raise

def clean_temp_saves(verbose=False, force=False):
    temp_save_path = 'temp_saves/last_session.json'
    if os.path.exists(temp_save_path):
        if force or time.time() - os.path.getmtime(temp_save_path) > 86400:
            os.remove(temp_save_path)
            if VERBOSE:
                create_log("CLEAN_TEMP_SAVES: Removed temp save")
                