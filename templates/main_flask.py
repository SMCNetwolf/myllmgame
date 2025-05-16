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

from config import (
    VERBOSE, GCS_BUCKET_NAME, TOGETHER_API_KEY, MODEL, IS_SAFE_MODEL, IMAGE_MODEL, 
    INITIAL_IMAGE_FILE_PATH, DEFAULT_IMAGE_FILE_PATH, DEFAULT_AUDIO_FILE_PATH, 
    IMAGE_FILE_PREFIX, WORLD_PATH, SAVE_GAMES_PATH, TEMP_SAVES_PATH, DB_PATH, MAX_SAVE,
    ERROR_IMAGE_FILE_PATH, bucket
)

# Initialize Together API
together_api_key = TOGETHER_API_KEY
if not together_api_key:
    raise ValueError("TOGETHER_API_KEY not found ")
    create_log("\n\nMAIN_FLASK: TOGETHER_API_KEY not found\n\n", force_log=True)
client = Together(api_key=together_api_key)
    
# Initialize last_saved_history
last_saved_history = None

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
        create_log(f"MAIN_FLASK: LOAD_WORLD: Loaded world {world['name']}")
        return world
    except FileNotFoundError:
        create_log(f"\n\nMAIN_FLASK: Error: File {filename} not found\n\n", force_log=True)
        raise
    except json.JSONDecodeError:
        create_log(f"\n\nMAIN_FLASK: Error: Invalid JSON in {filename}\n\n", force_log=True)
        raise
    except ValueError as e:
        create_log(f"\n\nMAIN_FLASK: Error: {str(e)}\n\n", force_log=True)
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

def validate_game_state(game_state, int_verbose=False):
    required_keys = ['world', 'kingdom', 'town', 'npcs', 'character', 'inventory', 'achievements', 'output_image', 'ambient_sound', 'history']
    for key in required_keys:
        if key not in game_state:
            create_log(f"\n\nMAIN_FLASK: VALIDATE_GAME_STATE: Missing key {key} in world JSON\n\n", force_log=True)
            return False
    if int_verbose:
        create_log(f"MAIN_FLASK: VALIDATE_GAME_STATE: Game state is valid")
    return True

def get_initial_game_state(int_verbose=False):
    
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
    if int_verbose:
        create_log(f"MAIN_FLASK: GET_INITIAL_GAME_STATE: Successfully created initial game state\n")
    return initial_game_state

def clean_duplicate_history(game_state, int_verbose=False):
    # Clean history to remove duplicates while preserving order
    seen = set()
    count=0
    cleaned_history = []
    for entry in game_state['history']:
        entry_tuple = (entry['role'], entry['content'])
        if entry_tuple not in seen:
            seen.add(entry_tuple)
            cleaned_history.append(entry)
        else:
            count+=1
    game_state['history'] = cleaned_history
    if int_verbose and count > 0:
        create_log(f"MAIN_FLASK: CLEAN_HISTORY : Cleaned history, {count} duplicates removed")
    return game_state

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
            model=IS_SAFE_MODEL,
            prompt=prompt.format(message=message)
        )
        result = response.choices[0].text.strip()
        return result == 'safe'
    except Exception as e:
        create_log(f"\n\nMAIN_FLASK: Error in is_safe: {str(e)}\n\n", force_log=True)
        return False

def summarize(template, prompt, int_verbose=False):
    try:
        final_prompt = template + prompt
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": final_prompt}]
        )
        if int_verbose:
            create_log(f"\nMAIN_FLASK: SUMMARIZE - Summarized text: \n{response.choices[0].message.content}\n")
        return response.choices[0].message.content
    except Exception as e:
        create_log(f"\n\nMAIN_FLASK: Error in summarize: {str(e)}\n\n", force_log=True)
        return ""

def detect_inventory_changes(game_state, last_response, int_verbose=False):
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
            create_log(f'\nMAIN_FLASK: DETECT_INVENTORY_CHANGES: Response:\n{response}\n')
        try:
            result = json.loads(response)
            return result.get('itemUpdates', [])
        except json.JSONDecodeError:
            create_log("\n\nMAIN_FLASK: DETECT_INVENTORY_CHANGES: Invalid JSON response\n\n", force_log=True)
            return []
    except Exception as e:
        create_log(f"\n\nMAIN_FLASK: DETECT_INVENTORY_CHANGES: Error in detect_inventory_changes: {str(e)}\n\n", force_log=True)
        return []

def update_inventory(game_state, item_updates, int_verbose=False):
    if 'inventory' not in game_state:
        create_log('\n\nMAIN_FLASK: UPDATE_INVENTORY - Error: game_state missing inventory key\n\n', force_log=True)
        return
    inventory = game_state['inventory']
    if isinstance(item_updates, dict):
        item_updates = [item_updates]
    elif not isinstance(item_updates, list):
        create_log(f'\n\nMAIN_FLASK: UPDATE_INVENTORY - Error: item_updates must be list or dict, got {type(item_updates)}\n\n', force_log=True)
        return
    if int_verbose:
        create_log(f'\nMAIN_FLASK: UPDATE_INVENTORY - Initial Inventory: {inventory}\n')
        create_log(f'\nMAIN_FLASK: UPDATE_INVENTORY - Item Updates: {item_updates}\n')
    if not item_updates:
        if int_verbose:
            create_log('\nUPDATE_INVENTORY - No updates provided\n')
        return
    for update in item_updates:
        if not isinstance(update, dict) or 'name' not in update or 'change_amount' not in update:
            create_log(f'\n\nMAIN_FLASK: UPDATE_INVENTORY - Invalid update: {update}\n\n')
            continue
        name = update['name']
        change_amount = update['change_amount']
        if not isinstance(change_amount, int):
            if int_verbose:
                create_log(f'\n\nMAIN_FLASK: UPDATE_INVENTORY - Invalid change_amount: {update}\n\n')
            continue
        if change_amount == 0:
            continue
        elif change_amount > 0:
            inventory[name] = inventory.get(name, 0) + change_amount
            if int_verbose:
                create_log(f'MAIN_FLASK: UPDATE_INVENTORY - Added {change_amount} {name}')
        elif change_amount < 0 and name in inventory:
            inventory[name] += change_amount
            if int_verbose:
                create_log(f'MAIN_FLASK: UPDATE_INVENTORY - Removed {abs(change_amount)} {name}')
        if name in inventory and inventory[name] <= 0:
            del inventory[name]
            if int_verbose:
                create_log(f'MAIN_FLASK: UPDATE_INVENTORY - Removed {name} (quantity <= 0)')
    if int_verbose:
        create_log(f'MAIN_FLASK: UPDATE_INVENTORY - Final Inventory: {inventory}\n')
    update_game_state(game_state, inventory=inventory)

def update_game_state(game_state, **updates):
    game_state.update(updates)
    if VERBOSE:
        create_log(f'MAIN_FLASK: UPDATE_GAME_STATE - Updated game_state')
        #create_log(f'\nMAIN_FLASK: UPDATE_GAME_STATE - Final game_state:\n{game_state}\n')
    return game_state

def image_generator(prompt, int_verbose=False):
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
            create_log(f"MAIN_FLASK: IMAGE_GENERATOR: Uploaded {DEFAULT_IMAGE_FILE_PATH} to gs://{os.environ.get('GCS_BUCKET_NAME')}/{gcs_path}", force_log=True)
        except Exception as e:
            create_log(f"\n\nMAIN_FLASK: IMAGE_GENERATOR: Error uploading {DEFAULT_IMAGE_FILE_PATH} to GCS: {str(e)}\n\n", force_log=True)
            raise
        
        if int_verbose:
            create_log(f"MAIN_FLASK: IMAGE_GENERATOR: Generated and saved {DEFAULT_IMAGE_FILE_PATH}")
        return DEFAULT_IMAGE_FILE_PATH
    except Exception as e:
        create_log(f"\n\nMAIN_FLASK: IMAGE_GENERATOR: Error generating image: {str(e)}\n\n", force_log=True)
        return ERROR_IMAGE_FILE_PATH

def run_action(message, game_state, int_verbose=False):
    try:
        world_info = get_world_info(game_state)
        summ_history = ""
        str_history = " ".join([str(message['content']) for message in game_state['history']])
        if len(str_history) > 6000: # 6000 char is about a thousand words
            summ_history = summarize(prompts.summarize_prompt_template, str_history,int_verbose=int_verbose)
            if int_verbose:
                create_log(f"MAIN_FLASK: RUN_ACTION - Summarized history: \n{summ_history}\n")
        else:
            summ_history = str_history
            if int_verbose:
                create_log(f"MAIN_FLASK: RUN_ACTION - History not summarized")
        message_prompt = prompts.prompt_template + f"\n{summ_history}\n" + \
            f"\n*** Inventário do usuário: \n{game_state['inventory']}\n" + \
            f"\n*** Pergunta do usuário: \n{message}\n\n"
        if int_verbose:
            create_log(f"MAIN_FLASK: RUN_ACTION - Message prompt: \n{message_prompt}\n")
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
        generated_image_path = image_generator(result, int_verbose=int_verbose)
        local_messages.append({"role": "assistant", "content": result})
        item_updates = detect_inventory_changes(game_state, result, int_verbose=int_verbose)
        update_inventory(game_state, item_updates, int_verbose=int_verbose)
        updated_history = game_state['history'] + [{"role": "user", "content": message}, {"role": "assistant", "content": result}]
        update_game_state(
            game_state,
            output_image=generated_image_path,
            history=updated_history,
        )
        return result
    except Exception as e:
        create_log(f"\n\nMAIN_FLASK: Error in run_action: {str(e)}\n\n", force_log=True)
        return "Error in run_action - Something went wrong."

def save_temp_game_state(game_state, int_verbose=False):
    global last_saved_history
    if last_saved_history != game_state['history']:
        try:
            os.makedirs('temp_saves', exist_ok=True)
            temp_save_path = 'temp_saves/last_session.json'
            with open(temp_save_path, 'w', encoding='utf-8') as f:
                json.dump({'game_state': game_state}, f, ensure_ascii=False, indent=4)
            last_saved_history = game_state['history']
            if int_verbose:
                create_log(f"MAIN_FLASK: SAVE_TEMP_GAME_STATE: Saved game state to {temp_save_path}")
        except Exception as e:
            create_log(f"\n\nMAIN_FLASK: SAVE_TEMP_GAME_STATE: Error saving temp game state: {str(e)}\n\n", force_log=True)
              