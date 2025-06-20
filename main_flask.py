import base64
import json
import datetime
import os
import re
import glob
import time
import traceback
import sqlite3
import random
import uuid
from flask import session
from together import Together
from create_log import create_log
from dotenv import load_dotenv
from google.cloud import storage

from config import (
    VERBOSE, GCS_BUCKET_NAME, TOGETHER_API_KEY, MODEL, IS_SAFE_MODEL, IMAGE_MODEL, 
    INITIAL_IMAGE_FILE_PATH, DEFAULT_IMAGE_FILE_PATH, DEFAULT_AUDIO_FILE_PATH, 
    IMAGE_FILE_PREFIX, WORLD_PATH, SAVE_GAMES_PATH, TEMP_SAVES_PATH, DB_PATH, MAX_SAVE,
    ERROR_IMAGE_FILE_PATH, bucket, SOUND_MAP
)

from prompts import (
    everyone_content_policy, system_inventory_prompt, get_npc_dialogue_prompt,
    command_interpreter_prompt, get_false_clue_prompt, get_trick_prompt, get_attack_prompt,
    get_is_safe_prompt, get_combat_resolution_prompt, get_check_clue_prompt, 
    get_exploration_prompt, get_game_objective_prompt,get_general_action_prompt,
    get_true_clue_prompt, get_true_ally_confirmation_prompt
)

# Initialize Together API
together_api_key = TOGETHER_API_KEY
if not together_api_key:
    raise ValueError("TOGETHER_API_KEY not found")
    create_log("\n\nMAIN_FLASK: TOGETHER_API_KEY not found\n\n", force_log=True)
client = Together(api_key=together_api_key)

# Initialize last_saved_history
last_saved_history = None

# Constants
MAX_TRIES = 3
MAX_FALSE_CLUE = 3
MAX_TRUE_CLUE = 2
MAX_FALSE_ALLY = 1
MAX_TRICK = 3
MAX_ATTACKS = 3
EVENT_CHANCE = 0.05  # 30% chance to trigger an event
SKILL = 50  # Base skill level (0-100)
INTELLIGENCE = 50  # Base intelligence level (0-100)
STRENGTH = 50  # Base strength level (0-100)

def generate_game_objective(int_verbose=False):
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": get_game_objective_prompt()}],
            max_tokens=500,
            temperature=0.7
        ).choices[0].message.content
        objective_data = json.loads(response)
        objective = objective_data['objective']
        true_clue = objective_data['true_clue']
        npcs = objective_data['npcs']
        welcome_message = objective_data['welcome_message']
        initial_map = objective_data['initial_map']
    except Exception as e:
        create_log(f"MAIN_FLASK: GENERATE_GAME_OBJECTIVE: Error generating objective: {str(e)}", force_log=True)
        objective_data = {
            'objective': 'Em Eldrida, o traidor Lyrien Darkscale busca roubar a relíquia secreta EnterWealther, uma fonte de poder ancestral. Ele planeja realizar um ritual no solstício de verão para invocar um poder maligno. Só Eira Shadowglow, uma habilidosa guerreira, pode ajudá-lo a parar. Encontre o sábio Thorne Silvermist, que pode fornecer informações valiosas sobre EnterWealther; o mercador Rylan Stonebrook, que pode fornecer suprimentos e armas; e a druida Elara Moonwhisper, que pode fornecer ajuda mágica.',
            'true_clue': {'content': 'Lyrien busca EnterWealther', 'id': 'clue1'},
            'npcs': [
                {'name': 'Lyrien Darkscale', 'status': 'Hostile', 'description': 'Mago sombrio com olhos penetrantes e aura misteriosa.'},
                {'name': 'Eira Shadowglow', 'status': 'Allied', 'description': 'Guerreira ágil com cabelos negros e olhar determinado.'},
                {'name': 'Thorne Silvermist', 'status': 'Neutral', 'description': 'Sábio eremita versado em segredos antigos.'},
                {'name': 'Rylan Stonebrook', 'status': 'Neutral', 'description': 'Mercador astuto com contatos no mercado.'},
                {'name': 'Elara Moonwhisper', 'status': 'Neutral', 'description': 'Druida mística ligada às forças da natureza.'}
            ],
            'welcome_message': 'Você chega em Eldrida e ouve rumores de traição em meio à celebração do solstício de verão.',
            'initial_map': {
                'Eldrida': {
                    'description': 'Uma cidade vibrante, cheia de pessoas se preparando para as festividades do solstício.',
                    'exits': ['Floresta de Eldrid', 'Colina do Panteão', 'Cavernas Profundas', 'Porto da Enseada']
                }
            }
        }
        objective = objective_data['objective']
        true_clue = objective_data['true_clue']
        npcs = objective_data['npcs']
        welcome_message = objective_data['welcome_message']
        initial_map = objective_data['initial_map']
    
    return {
        'objective': objective,
        'true_clue': true_clue,
        'npcs': npcs,
        'welcome_message': welcome_message,
        'initial_map': initial_map
    }

def validate_game_state(game_state):
    required_keys = [
        'history', 'output_image', 'ambient_sound', 'location', 'known_map', 'current_state', 'health', 'resources', 
        'clues', 'npc_status', 'combat_results', 'puzzle_results', 'character', 'active_puzzle', 
        'active_combat', 'skill', 'waiting_for_option', 'game_objective', 'true_clues', 'event_result'
    ]
    if not all(key in game_state for key in required_keys):
        create_log(f"\n\nMAIN_FLASK: VALIDATE_GAME_STATE: Missing required keys: {set(required_keys) - set(game_state.keys())}\n\n", force_log=True)
        return False
    if not isinstance(game_state['history'], list):
        create_log("\n\nMAIN_FLASK: VALIDATE_GAME_STATE: History is not a list\n\n", force_log=True)
        return False
    if not isinstance(game_state['resources'], dict) or not all(k in game_state['resources'] for k in ['wands', 'potions', 'energy']):
        create_log("\n\nMAIN_FLASK: VALIDATE_GAME_STATE: Invalid resources structure\n\n", force_log=True)
        return False
    return True

def get_initial_game_state(int_verbose=False):
    objective_data = generate_game_objective(int_verbose=int_verbose)
    npc_status = {
        npc['name']: {
            'name': npc['name'],
            'status': npc['status'],
            'supposed_status': 'Neutral',
            'description': npc['description']
        } for npc in objective_data['npcs']
    }
    initial_game_state = {
        'history': [{"role": "assistant", "content": objective_data['welcome_message']}],
        'output_image': INITIAL_IMAGE_FILE_PATH,
        'ambient_sound': DEFAULT_AUDIO_FILE_PATH,
        'location': {'name': 'Eldrida', 'exploring_location': None},
        'known_map': objective_data['initial_map'],
        'current_state': 2,
        'health': 10,
        'resources': {'wands': 2, 'potions': 2, 'energy': 5},
        'clues': [],
        'npc_status': npc_status,
        'combat_results': [],
        'puzzle_results': [],
        'character': 'Herói',
        'active_puzzle': None,
        'active_combat': None,
        'skill': SKILL,
        'waiting_for_option': False,
        'game_objective': objective_data['objective'],
        'true_clues': [objective_data['true_clue']],
        'event_result': "Nenhum evento ocorreu."
    }
    if int_verbose:
        create_log(f"MAIN_FLASK: GET_INITIAL_GAME_STATE: Loaded initial game state")
    return initial_game_state

def update_game_state(game_state, int_verbose=False, **updates):
    game_state.update(updates)
    if int_verbose:
        create_log(f'MAIN_FLASK: UPDATE_GAME_STATE - Updated game_state')
    return game_state

def save_temp_game_state(game_state, int_verbose=False):
    global last_saved_history
    if last_saved_history != game_state['history']:
        for attempt in range(3):
            try:
                os.makedirs('temp_saves', exist_ok=True)
                temp_save_path = 'temp_saves/last_session.json'
                with open(temp_save_path, 'w', encoding='utf-8') as f:
                    json.dump({'game_state': game_state}, f, ensure_ascii=False, indent=4)
                last_saved_history = game_state['history']
                if int_verbose:
                    create_log(f"MAIN_FLASK: SAVE_TEMP_GAME_STATE: Saved game state to {temp_save_path}")
                return
            except Exception as e:
                create_log(f"\n\nMAIN_FLASK: SAVE_TEMP_GAME_STATE: Attempt {attempt + 1} failed: {str(e)}\n\n", force_log=True)
                if attempt == 2:
                    create_log("\n\nMAIN_FLASK: SAVE_TEMP_GAME_STATE: All retries failed\n\n", force_log=True)
                    return
                time.sleep(1)

def clean_duplicate_history(game_state, int_verbose=False):
    seen = set()
    count = 0
    cleaned_history = []
    for entry in game_state['history']:
        entry_tuple = (entry['role'], entry['content'])
        if entry_tuple not in seen:
            seen.add(entry_tuple)
            cleaned_history.append(entry)
        else:
            count += 1
    game_state['history'] = cleaned_history
    if int_verbose and count > 0:
        create_log(f"MAIN_FLASK: CLEAN_HISTORY: Cleaned history, {count} duplicates removed")
    return game_state

def format_chat_history(history, game_state):
    character_name = game_state.get('character', session.get('username', 'Hero')).split()[0]
    formatted_messages = []
    for msg in history:
        if msg['role'] == 'user':
            role = character_name
        elif msg['role'] == 'assistant':
            role = 'Mestre do Jogo'
        formatted_messages.append(f"{role}: {msg['content']}")
    return "\n\n".join(formatted_messages)

def is_safe(message, int_verbose=False):
    create_log(f"MAIN_FLASK: IS_SAFE is temporarily disabled due to MODEL limitations", force_log=True)
    return True, "none"

def detect_inventory_changes(game_state, last_response, int_verbose=VERBOSE, action_type=None, item=None):
    try:
        inventory = game_state['resources']
        story_context = format_chat_history(game_state['history'], game_state)
        prompt = system_inventory_prompt.format(story=last_response, inventory=str(inventory)) + \
                 "\nRetorne SOMENTE um objeto JSON com a chave 'itemUpdates' contendo uma lista de atualizações. " + \
                 "Exemplo: {'itemUpdates': [{'item': 'poção', 'change': -1}]}. Se nenhuma mudança, retorne {'itemUpdates': []}."
        if int_verbose:
            create_log(f"MAIN_FLASK: DETECT_INVENTORY_CHANGES: Prompt:\n{prompt}\n")
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0
        )
        response_text = response.choices[0].message.content
        if int_verbose:
            create_log(f"MAIN_FLASK: DETECT_INVENTORY_CHANGES: Response:\n{response_text}\n")
        try:
            result = json.loads(response_text)
            if not isinstance(result.get('itemUpdates', []), list):
                create_log("\n\nMAIN_FLASK: DETECT_INVENTORY_CHANGES: Invalid itemUpdates format\n\n", force_log=True)
                return []
            return result.get('itemUpdates', [])
        except json.JSONDecodeError:
            create_log(f"\n\nMAIN_FLASK: DETECT_INVENTORY_CHANGES: Invalid JSON response: {response_text}\n\n", force_log=True)
            json_match = re.search(r'\{.*?\}(?=\s*$|\s*\Z)', response_text, re.DOTALL)
            if json_match:
                try:
                    result = json.loads(json_match.group(0))
                    if not isinstance(result.get('itemUpdates', []), list):
                        create_log("\n\nMAIN_FLASK: DETECT_INVENTORY_CHANGES: Invalid itemUpdates format in regex\n\n", force_log=True)
                        return []
                    return result.get('itemUpdates', [])
                except json.JSONDecodeError:
                    create_log(f"\n\nMAIN_FLASK: DETECT_INVENTORY_CHANGES: Regex failed for JSON: {json_match.group(0)}\n\n", force_log=True)
            if action_type == "use_item" and item in inventory:
                create_log(f"\n\nMAIN_FLASK: DETECT_INVENTORY_CHANGES: Falling back to default update for {item}\n\n", force_log=True)
                return [{"item": item, "change": -1}]
            return []
    except Exception as e:
        create_log(f"\n\nMAIN_FLASK: DETECT_INVENTORY_CHANGES: Unexpected error: {str(e)}\n\n", force_log=True)
        if action_type == "use_item" and item in inventory:
            create_log(f"\n\nMAIN_FLASK: DETECT_INVENTORY_CHANGES: Falling back to default update for {item}\n\n", force_log=True)
            return [{"item": item, "change": -1}]
        return []

def image_generator(prompt, int_verbose=False):
    try:
        response = client.images.generate(
            model=IMAGE_MODEL,
            prompt=prompt,
            width=512,
            height=384,
            steps=1,
            n=1,
            response_format="b64_json"
        )
        image_data = base64.b64decode(response.data[0].b64_json)
        os.makedirs(os.path.dirname(DEFAULT_IMAGE_FILE_PATH), exist_ok=True)
        
        with open(DEFAULT_IMAGE_FILE_PATH, 'wb') as f:
            f.write(image_data)
        
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        gcs_path = f"{DEFAULT_IMAGE_FILE_PATH.split('.png')[0]}_{timestamp}.png"
        try:
            blob = bucket.blob(gcs_path)
            blob.upload_from_filename(DEFAULT_IMAGE_FILE_PATH)
            if int_verbose:
                create_log(f"MAIN_FLASK: IMAGE_GENERATOR: Uploaded {DEFAULT_IMAGE_FILE_PATH} to gs://{os.environ.get('GCS_BUCKET_NAME')}/{gcs_path}")
        except Exception as e:
            create_log(f"\n\nMAIN_FLASK: IMAGE_GENERATOR: Error uploading {DEFAULT_IMAGE_FILE_PATH} to GCS: {str(e)}\n\n", force_log=True)
            raise
        
        if int_verbose:
            create_log(f"MAIN_FLASK: IMAGE_GENERATOR: Generated and saved {DEFAULT_IMAGE_FILE_PATH}")
        return DEFAULT_IMAGE_FILE_PATH
    except Exception as e:
        create_log(f"\n\nMAIN_FLASK: IMAGE_GENERATOR: Error generating image: {str(e)}\n\n", force_log=True)
        return ERROR_IMAGE_FILE_PATH

def generate_random_events(game_state, event_type, recent_history, int_verbose=False):
    temperature = 0.8
    current_state = game_state.get('current_state', 1)
    location = game_state.get('location', 'Eldrida')
    prompt_map = {
        "true_clue": get_true_clue_prompt,
        "false_clue": get_false_clue_prompt,
        "trick": get_trick_prompt,
        "attack": get_attack_prompt
    }
    if event_type not in prompt_map:
        create_log(f"MAIN_FLASK: Invalid event type: {event_type}", force_log=True)
        return None
            
    events = []
    
    if event_type == "false_clue":
        response = client.chat.completions.create(
            model=MODEL,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt_map[event_type](game_state['game_objective'],location, recent_history)}]
        ).choices[0].message.content
        if int_verbose:
            create_log(f"MAIN_FLASK: GENERATE_RANDOM_EVENTS: Raw false_clue response: {response}")
        try:
            clue_data = json.loads(response)
            events.append({"type": "false_clue", "content": clue_data['clue'], "id": clue_data['id']})
        except json.JSONDecodeError:
            create_log(f"\n\nMAIN_FLASK: GENERATE_RANDOM_EVENTS: Invalid JSON for false_clue: {response}\n\n", force_log=True)
            json_match = re.search(r'\{.*?\}\}(?=\s*$|\s*\Z)', response, re.DOTALL)
            if json_match:
                try:
                    clue_data = json.loads(json_match.group(0))
                    events.append({"type": "false_clue", "content": clue_data['clue'], "id": clue_data['id']})
                except json.JSONDecodeError:
                    create_log(f"\n\nMAIN_FLASK: GENERATE_RANDOM_EVENTS: Regex failed for false_clue: {json_match.group(0)}\n\n", force_log=True)
    
    elif event_type == "true_clue":
        response = client.chat.completions.create(
            model=MODEL,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt_map[event_type](game_state['game_objective'], location, recent_history)}]
        ).choices[0].message.content
        if int_verbose:
            create_log(f"MAIN_FLASK: GENERATE_RANDOM_EVENTS: Raw true_clue response: {response}")
        try:
            clue_data = json.loads(response)
            existing_ids = [clue['id'] for clue in game_state['true_clues']]
            if isinstance(clue_data, dict) and 'clue' in clue_data and 'id' in clue_data:
                if clue_data['id'] not in existing_ids:
                    events.append({"type": "true_clue", "content": clue_data['clue'], "id": clue_data['id']})
                else:
                    create_log(f"MAIN_FLASK: GENERATE_RANDOM_EVENTS: Duplicate true_clue id: {clue_data['id']}", force_log=True)
            elif isinstance(clue_data, list) and clue_data:
                for clue in clue_data:
                    if 'clue' in clue and 'id' in clue and clue['id'] not in existing_ids:
                        events.append({"type": "true_clue", "content": clue['clue'], "id": clue['id']})
                        break
                else:
                    create_log(f"\n\nMAIN_FLASK: GENERATE_RANDOM_EVENTS: No valid true_clue found in: {clue_data}\n\n", force_log=True)
            else:
                create_log(f"\n\nMAIN_FLASK: GENERATE_RANDOM_EVENTS: Invalid true_clue data: {clue_data}\n\n", force_log=True)
        except json.JSONDecodeError:
            create_log(f"\n\nMAIN_FLASK: GENERATE_RANDOM_EVENTS: Invalid JSON for true_clue: {response}\n\n", force_log=True)
            json_match = re.search(r'\{.*?\}\}(?=\s*$|\s*\Z)', response, re.DOTALL)
            if json_match:
                try:
                    clue_data = json.loads(json_match.group(0))
                    if isinstance(clue_data, dict) and 'clue' in clue_data and 'id' in clue_data:
                        existing_ids = [clue['id'] for clue in game_state['true_clues']]
                        if clue_data['id'] not in existing_ids:
                            events.append({"type": "true_clue", "content": clue_data['clue'], "id": clue_data['id']})
                        else:
                            create_log(f"MAIN_FLASK: GENERATE_RANDOM_EVENTS: Duplicate true_clue id: {clue_data['id']}", force_log=True)
                    else:
                        create_log(f"\n\nMAIN_FLASK: GENERATE_RANDOM_EVENTS: Invalid true_clue regex data: {clue_data}\n\n", force_log=True)
                except json.JSONDecodeError:
                    create_log(f"\n\nMAIN_FLASK: GENERATE_RANDOM_EVENTS: Regex failed for true_clue: {json_match.group(0)}\n\n", force_log=True)
    
    elif event_type == "trick":
        response = client.chat.completions.create(
            model=MODEL,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt_map[event_type](recent_history)}]
        ).choices[0].message.content
        if int_verbose:
            create_log(f"MAIN_FLASK: GENERATE_RANDOM_EVENTS: Raw trick response: {response}")
        try:
            trick_data = json.loads(response)
            events.append({"type": "trick", "content": trick_data['trick'], "solution": trick_data['solution'], "clues": trick_data['clues'], "tries": 0})
        except json.JSONDecodeError:
            create_log(f"\n\nMAIN_FLASK: GENERATE_RANDOM_EVENTS: Invalid JSON for trick: {response}\n\n", force_log=True)
            json_match = re.search(r'\{.*?\}\}(?=\s*$|\s*\Z)', response, re.DOTALL)
            if json_match:
                try:
                    trick_data = json.loads(json_match.group(0))
                    events.append({"type": "trick", "content": trick_data['trick'], "solution": trick_data['solution'], "clues": trick_data['clues'], "tries": 0})
                except json.JSONDecodeError:
                    create_log(f"\n\nMAIN_FLASK: GENERATE_RANDOM_EVENTS: Regex failed for trick: {json_match.group(0)}\n\n", force_log=True)
    
    elif event_type == "attack":
        combat_type = {
            1: "oral",
            2: "physical",
            3: "professional",
            4: "physical"
        }.get(current_state, "physical")
        response = client.chat.completions.create(
            model=MODEL,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt_map[event_type](combat_type, recent_history)}]
        ).choices[0].message.content
        try:
            attack_data = json.loads(response)
            events.append({"type": "attack", "content": attack_data['description'], "clue": attack_data['clue'], "tries": 0, "combat_type": combat_type})
        except json.JSONDecodeError:
            create_log(f"\n\nMAIN_FLASK: GENERATE_RANDOM_EVENTS: Invalid JSON for attack: {response}\n\n", force_log=True)
            json_match = re.search(r'\{.*?\}\}(?=\s*$|\s*\Z)', response, re.DOTALL)
            if json_match:
                try:
                    attack_data = json.loads(json_match.group(0))
                    events.append({"type": "attack", "content": attack_data['description'], "clue": attack_data['clue'], "tries": 0, "combat_type": combat_type})
                except json.JSONDecodeError:
                    create_log(f"\n\nMAIN_FLASK: GENERATE_RANDOM_EVENTS: Regex failed for attack: {json_match.group(0)}\n\n", force_log=True)
    
    if int_verbose:
        create_log(f"MAIN_FLASK: GENERATE_RANDOM_EVENTS: Generated event: {events[0] if events else 'None'} for state {current_state}")
    return events[0] if events else None

def update_inventory(game_state, item_updates, int_verbose=False):
    if 'resources' not in game_state:
        create_log('\n\nMAIN_FLASK: UPDATE_INVENTORY - Error: game_state missing resources key\n\n', force_log=True)
        return
    inventory = game_state['resources']
    if item_updates is None:
        create_log('\n\nMAIN_FLASK: UPDATE_INVENTORY - Error: item_updates is None\n\n', force_log=True)
        return
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
        if not isinstance(update, dict) or 'item' not in update or 'change' not in update:
            create_log(f'\n\nMAIN_FLASK: UPDATE_INVENTORY - Invalid update: {update}\n\n', force_log=True)
            continue
        item = update['item']
        change = update['change']
        if not isinstance(change, int):
            if int_verbose:
                create_log(f'\n\nMAIN_FLASK: UPDATE_INVENTORY - Invalid change: {update}\n\n')
            continue
        if change == 0:
            continue
        elif change > 0:
            inventory[item] = inventory.get(item, 0) + change
            if int_verbose:
                create_log(f'MAIN_FLASK: UPDATE_INVENTORY - Added {change} {item}')
        elif change < 0 and item in inventory:
            inventory[item] = max(0, inventory.get(item, 0) + change)
            if int_verbose:
                create_log(f'MAIN_FLASK: UPDATE_INVENTORY - Removed {abs(change)} {item}')
        if item in inventory and inventory[item] <= 0:
            del inventory[item]
            if int_verbose:
                create_log(f'MAIN_FLASK: UPDATE_INVENTORY - Removed {item} (quantity <= 0)')
    update_game_state(game_state, resources=inventory)

def handle_false_clue(game_state, event, int_verbose=False):
    clue = {"content": event['content'], "id": event['id'], "false": True}
    game_state['clues'].append(clue)
    game_state['recent_clue'] = {"id": event['id'], "content": event['content']}
    item_updates = [{"item": "mysterious_note", "change": 1}]
    update_inventory(game_state, item_updates, int_verbose)
    story_context = format_chat_history(game_state['history'][-4:], game_state)
    location = game_state.get('location', list(game_state['known_map'].keys())[0])
    prompt = f"""
        Gere um diálogo em português com um NPC em {location} comentando a pista falsa: {event['content']}. 
        Contexto recente: {story_context}. 
        Retorne apenas o diálogo (ex.: NPC: "Texto..." Você: "Texto..."), sem narrativa ou colchetes. 
        Máximo 3 trocas, 80 palavras. 
        {everyone_content_policy}
    """
    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=150,
        temperature=0.0
    ).choices[0].message.content
    is_safe_result, violations = is_safe(response, int_verbose)
    if not is_safe_result:
        create_log(f"MAIN_FLASK: HANDLE_FALSE_CLUE: Unsafe dialogue: {response}", force_log=True)
        return "Diálogo sobre pista não permitido.", "generic"
    
    clean_response = re.sub(r'\[.*?\]', '', response).strip()
    
    if int_verbose:
        create_log(f"MAIN_FLASK: HANDLE_FALSE_CLUE: Added clue: {clue}, Item: mysterious_note, Dialogue: {response}")
    return f"{event['content']}\n{response}", "generic"

def handle_combat(game_state, event, int_verbose=False):
    combat = game_state.get('active_combat', event)
    story_context = format_chat_history(game_state['history'][-4:], game_state)

    if int_verbose:
        create_log(f"MAIN_FLASK: HANDLE_COMBAT: Entered with combat: {combat}")

    if 'tries' not in combat:
        combat['tries'] = 1

    if combat['tries'] >= MAX_TRIES:
        game_state['combat_results'].append({"enemy": combat['content'], "won": False})
        game_state['health'] = max(0, game_state['health'] - 1)
        game_state['active_combat'] = None
        game_state['ambient_sound'] = SOUND_MAP.get("generic", DEFAULT_AUDIO_FILE_PATH)
        create_log(f"MAIN_FLASK: HANDLE_COMBAT: Combat lost after {MAX_TRIES} tries", force_log=True)
        return None, None

    if combat['tries'] > 0:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": get_attack_prompt(combat.get('combat_type', 'physical'), story_context)}],
            temperature=0.3
        ).choices[0].message.content
        if int_verbose:
            create_log(f"MAIN_FLASK: HANDLE_COMBAT: JSON(?) response for try {combat['tries'] + 1}: {response}")

        try:
            attack_data = json.loads(response)
            combat['clue'] = attack_data['clue']
            if int_verbose:
                create_log(f"MAIN_FLASK: HANDLE_COMBAT: JSON wellformed - Clue response for try {combat['tries'] + 1}: {attack_data['clue']}")
        except json.JSONDecodeError:
            create_log("\n\nMAIN_FLASK: HANDLE_COMBAT: Invalid JSON for attack clue: {response}\n\n", force_log=True)
            combat['clue'] = "Tente novamente com uma nova estratégia."

    game_state['active_combat'] = combat

    narrative = f"PERIGO!: {combat['content']} Dica: {combat['clue']} (Tentativa {combat['tries'] + 1}/{MAX_TRIES})"
    if int_verbose:
        create_log(f"MAIN_FLASK: HANDLE_COMBAT: Updated combat: {combat['content']}, Clue: {combat['clue']}, Try: {combat['tries'] + 1}/{MAX_TRIES}\nNarrative: {narrative}")
    
    return narrative, "combat"

def resolve_combat(game_state, action, int_verbose=False):
    combat = game_state.get('active_combat')
    if not combat:
        if int_verbose:
            create_log("MAIN_FLASK: RESOLVE_COMBAT: No active combat")
        return "Nenhum combate ativo."

    story_context = format_chat_history(game_state['history'][-4:], game_state)
    combat['tries'] += 1
    if int_verbose:
        create_log(f"MAIN_FLASK: RESOLVE_COMBAT: Updated combat tries to {combat['tries']}")

    if combat['tries'] < MAX_TRIES:
        handle_combat(game_state, combat, int_verbose)
    
    try:
        prompt = get_check_clue_prompt(action, combat['clue'])
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        ).choices[0].message.content
        try:
            clue_response = json.loads(response)
            clue_used = clue_response.get('used_clue', False)
            if int_verbose:
                create_log(f"MAIN_FLASK: RESOLVE_COMBAT: Valid JSON in clue response informs if clue was used: {clue_used}")
        except json.JSONDecodeError:
            create_log(f"MAIN_FLASK: RESOLVE_COMBAT: Invalid JSON in clue response: {response}", force_log=True)
            clue_used = False
    except Exception as e:
        create_log(f"MAIN_FLASK: RESOLVE_COMBAT: Error evaluating clue use: {str(e)}", force_log=True)
        clue_used = False

    percent_success_rate = 0.2
    base_win_prob = percent_success_rate * (
        (game_state['health'] / 10.0) * 0.5 + 
        (game_state.get('skill', SKILL) / 100.0) * 0.25 + 
        (INTELLIGENCE / 100.0) * 0.1 + 
        (STRENGTH / 100.0) * 0.1
    )
    clue_used_bonus = 0.12
    ally_bonus = 0.2 if game_state['current_state'] == 5 and any(
        game_state['npc_status'][npc]['supposed_status'] == 'Allied' for npc in game_state['npc_status']
    ) else 0.0
    win_prob = base_win_prob + clue_used_bonus + ally_bonus if clue_used else base_win_prob + ally_bonus
    win_prob = min(max(win_prob, 0.0), 1.0)   

    won = random.random() < win_prob
    if int_verbose:
        create_log(f"MAIN_FLASK: RESOLVE_COMBAT: Combat status: win probability: {win_prob}; won? {won}")

    old_health = game_state['health']
    old_skill = game_state.get('skill', SKILL)
    health_loss = 0 if won or combat.get('combat_type', 'physical') != "physical" else old_health * 0.1
    game_state['health'] = max(0, old_health - health_loss)
    game_state['skill'] = old_skill * 1.1

    result_status = "won" if won else "lost" if combat['tries'] >= MAX_TRIES else "ongoing"
    resultado = "vitória" if result_status == "won" else "derrota" if result_status == "lost" else "em andamento"

    if game_state['current_state'] == 5 and won and len(game_state['true_clues']) >= 2 and any(
        game_state['npc_status'][npc]['supposed_status'] == 'Allied' and 
        game_state['npc_status'][npc]['status'] == 'Allied' for npc in game_state['npc_status']
    ):
        resultado = "vitória final"
        game_state['current_state'] = None

    prompt = get_combat_resolution_prompt(
        combat['content'],
        action,
        combat['clue'],
        resultado,
        story_context,
        combat['combat_type']
    )
    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3
    ).choices[0].message.content

    is_safe_result, violations = is_safe(response, int_verbose)
    if not is_safe_result:
        create_log(f"MAIN_FLASK: RESOLVE_COMBAT: Unsafe response: {response}", force_log=True)
        response = (
            f"Sua ação '{action}' não surtiu o efeito desejado, e a batalha tomou um rumo inesperado."
            if result_status == "ongoing"
            else f"Sua ação '{action}' falhou, e você foi derrotado pelos inimigos."
            if result_status == "lost"
            else f"Você triunfou na batalha, mas a vitória teve um preço inesperado."
        )

    health_delta = round(old_health - game_state['health'], 1)
    skill_delta = round(game_state['skill'] - old_skill, 1)
    status_update = f"\nSua saúde é {game_state['health']:.1f} ({'-' if health_delta > 0 else ''}{health_delta:.1f}), sua habilidade é {game_state['skill']:.1f} (+{skill_delta:.1f})."

    if result_status == "ongoing":
        response = response.rstrip() + f"\nDica: {combat['clue']} (Tentativa {combat['tries'] + 1}/{MAX_TRIES})" + status_update
    else:
        response = response.rstrip() + "\nFim de combate!\n" + status_update

    if won or combat['tries'] >= MAX_TRIES:
        game_state['combat_results'].append({"enemy": combat['content'], "won": won})
        return response

def handle_puzzle(game_state, event, int_verbose=False):
    puzzle = game_state.get('active_puzzle', event)
    game_state['active_puzzle'] = puzzle
    if int_verbose:
        create_log(f"MAIN_FLASK: HANDLE_PUZZLE: Presented puzzle: {puzzle['content']}, Clue: {puzzle['clues'][0]}")
    
    return f"Quebra-cabeça: {puzzle['content']} Dica: {puzzle['clues'][0]}", "puzzle"

def resolve_puzzle(game_state, solution, int_verbose=False):
    puzzle = game_state.get('active_puzzle')
    if not puzzle:
        if int_verbose:
            create_log("MAIN_FLASK: RESOLVE_PUZZLE: No active puzzle")
        return "Nenhum quebra-cabeça ativo."
    
    puzzle['tries'] += 1
    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": f"Avalie se '{solution}' resolve o quebra-cabeça: {puzzle['content']}"}]
    ).choices[0].message.content
    solved = "resolvido" in response.lower()
    
    if solved or puzzle['tries'] >= MAX_TRIES:
        game_state['puzzle_results'].append({"riddle": puzzle['content'], "solved": solved})
        game_state['active_puzzle'] = None
        game_state['ambient_sound'] = SOUND_MAP.get("generic", DEFAULT_AUDIO_FILE_PATH)
        result = f"Quebra-cabeça: {puzzle['content']} {'Resolvido!' if solved else f'Falhou após {MAX_TRIES} tentativas.'}"
        if int_verbose:
            create_log(f"MAIN_FLASK: RESOLVE_PUZZLE: Puzzle resolved, ambient_sound reverted to {game_state['ambient_sound']}")
    else:
        result = f"Quebra-cabeça: {puzzle['content']} Dica: {puzzle['clues'][puzzle['tries']]}"
    
    if int_verbose:
        create_log(f"MAIN_FLASK: RESOLVE_PUZZLE: Puzzle {'resolvido' if solved else 'ongoing' if puzzle['tries'] < MAX_TRIES else 'falhou'}, solution: {solution}")
    return result

def run_action(message, game_state, int_verbose=False):
    try:
        # checks if user message is safe
        if not is_safe(message, int_verbose):
            create_log(f"\n\nMAIN_FLASK: RUN_ACTION: Unsafe message: {message}\n\n", force_log=True)
            return "Mensagem não permitida."
        
        # Variables sanitization / initialization block
        # CHANGE 1: Update location initialization to use dictionary
        if 'location' not in game_state or not game_state['location']:
            game_state['location'] = {'name': list(game_state['known_map'].keys())[0], 'exploring_location': None}
            create_log(f"MAIN_FLASK: RUN_ACTION: Set default location to {game_state['location']['name']}", force_log=True)
        # END CHANGE 1
        if 'waiting_for_option' not in game_state:
            game_state['waiting_for_option'] = False
            create_log("MAIN_FLASK: RUN_ACTION: Initialized waiting_for_option to False", force_log=True)
        if 'active_options' not in game_state:
            game_state['active_options'] = []
            create_log("MAIN_FLASK: RUN_ACTION: Initialized active_options to []", force_log=True)
        action_type, details, suggestion = "generic", {}, ""
        suggestion = ""
        handle_option_selection = False
        if int_verbose:
            create_log(f"MAIN_FLASK: RUN_ACTION: Input: {message}, waiting_for_option: {game_state.get('waiting_for_option', 'MISSING')}, active_options: {game_state.get('active_options', 'NONE')}")
        current_state = game_state.get('current_state', 1)
        story_context = format_chat_history(game_state['history'], game_state)
        recent_history = format_chat_history(game_state['history'][-4:], game_state)
        result = ""
        false_npc = False
        clue_count = len([c for c in game_state['clues'] if c.get('false', False)])
        combat_count = len(game_state['combat_results'])
        puzzle_count = len(game_state['puzzle_results'])
        ally_count = sum(1 for npc in game_state['npc_status'] if game_state['npc_status'][npc]['supposed_status'] == 'Suspeito')
        event_handlers = {
            "false_clue": handle_false_clue,
            "trick": handle_puzzle,
            "attack": handle_combat
        }
        event_type = None
        trigger_event = False
        event_result = ""
        sound_trigger = None
        skip_action = False
        generate_image = None
        
        # Sets allowed events in each state  
        if current_state == 2:
            allowed_events = ["false_clue", "trick", "attack"] if clue_count < MAX_FALSE_CLUE or puzzle_count < MAX_TRICK or combat_count < MAX_ATTACKS else []
        elif current_state == 3:
            allowed_events = ["trick", "attack"] if puzzle_count < MAX_TRICK or combat_count < MAX_ATTACKS else []
        elif current_state == 4:
            allowed_events = ["trick", "attack"] if puzzle_count < MAX_TRICK or combat_count < MAX_ATTACKS else []
        
        # Option selection first block - Gets the selected option if waiting for option
        if game_state['waiting_for_option'] and game_state['active_options']:
            # sanitize empty option selection
            if not message.strip():
                create_log("MAIN_FLASK: RUN_ACTION: Empty input while waiting_for_option", force_log=True)
                return f"Por favor, escolha uma opção válida ({', '.join(str(i + 1) for i in range(len(game_state['active_options'])))})."
            # prepares to handle selected option
            if message.strip().isdigit():
                option_index = int(message) - 1
                if 0 <= option_index < len(game_state['active_options']):
                    action_type, details = game_state['active_options'][option_index]
                    suggestion = ""
                    game_state['waiting_for_option'] = False
                    handle_option_selection = True
                    create_log(f"MAIN_FLASK: RUN_ACTION: Selected option {message}: {action_type}, {details}", force_log=True)
                # if selected number is out, force user to choose a valid option
                else:
                    create_log(f"MAIN_FLASK: RUN_ACTION: Invalid option: {', '.join(str(i + 1) for i in range(len(game_state['active_options'])))}", force_log=True)
                    return f"Opção inválida. Escolha uma opção válida ({', '.join(str(i + 1) for i in range(len(game_state['active_options'])))})."
            # if user input is not a number
            else:
                create_log(f"MAIN_FLASK: RUN_ACTION: Non-numeric input while waiting_for_option: {message}", force_log=True)
                return f"Por favor, escolha uma opção válida ({', '.join(str(i + 1) for i in range(len(game_state['active_options'])))}."

        # Interprets the user input if action type is generic or there's no action already running - Sets action_type, details, suggestion
        if action_type == "generic" and not handle_option_selection:
            if int_verbose:
                create_log(f"MAIN_FLASK: RUN_ACTION: entering interpret command because there's no action running")
            prompt = command_interpreter_prompt.format(
                story_context=story_context,
                action_type="",
                current_state=current_state,
                command=message,
                event_info=game_state['event_result']
            )
            if int_verbose:
                create_log(f"MAIN_FLASK: RUN_ACTION: Before command interprer: Action: {action_type}, Details: {details}, Suggestion: {suggestion}")
            response = client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
                temperature=0.0
            ).choices[0].message.content
            if int_verbose:
                create_log(f"MAIN_FLASK: RUN_ACTION: Command interpreter response: {response}")
            # sanitize response
            try:
                command_data = json.loads(response)
                command_data.setdefault("action_type", "generic")
                command_data.setdefault("details", {})
                command_data.setdefault("suggestion", "")
            except json.JSONDecodeError:
                create_log(f"MAIN_FLASK: RUN_ACTION: JSON parsing failed: {response}", force_log=True)
                json_match = re.search(r'\{.*?\}(?=\s*$|\s*\Z)', response, re.DOTALL)
                if json_match:
                    try:
                        command_data = json.loads(json_match.group(0))
                        command_data.setdefault("action_type", "generic")
                        command_data.setdefault("details", {})
                        command_data['suggestion'] = ""
                    except json.JSONDecodeError:
                        command_data = {"action_type": "generic", "response": "Comando não reconhecido, tente algo como 'falar com um NPC' ou 'explorar'."}
                else:
                    command_data = {"action_type": "generic", "details": {}, "suggestion": ""}
                    return "Comando não reconhecido, tente algo como 'falar com um NPC' ou 'explorar'."
            # load the variables
            action_type = command_data.get('action_type', 'generic')
            details = command_data.get('details', {})
            suggestion = command_data.get('suggestion', "")
        if int_verbose:
            create_log(f"MAIN_FLASK: RUN_ACTION: Interpreted User command: {action_type}, Details: {details}, Suggestion: {suggestion}")

        # Event handling block - It is here because events interrupt normal flow
        # roll the dice to choose an event (or nothing) to generate 
        if action_type == "exploration" and not game_state.get('waiting_for_option') and not handle_option_selection:
            dice = random.random()
            trigger_event = dice < EVENT_CHANCE
            if trigger_event:
                event_type = random.choice(allowed_events) 
                if int_verbose:
                    create_log(f"\n\nMAIN_FLASK RUN ACTION: Dices thrown. \nDice result: {dice}. EVENT_CHANCE = {EVENT_CHANCE} .\nSelected Event type is {event_type}. Was it triggerred? {trigger_event}. \n\n")        
        # Generate an event if triggered
        if trigger_event:
            event = generate_random_events(game_state, event_type, recent_history, int_verbose)
            # sanitize event
            if event is None or not isinstance(event, dict) or 'type' not in event or event['type'] not in event_handlers:
                create_log(f"MAIN_FLASK: RUN_ACTION: Invalid event: {event}", force_log=True)
                event_result = "Nenhum evento ocorre no momento."
            else:
                if 'event_info' in event:
                    create_log(f"MAIN_FLASK: RUN_ACTION: Unexpected key 'event_info' in event: {event}", force_log=True)
                    event.pop('event_info', None)
            # Flags in game state that multiple interactions event has started
            if event['type'] == "attack":
                game_state['active_combat'] = event
            elif event['type'] == "trick":
                game_state['active_puzzle'] = event
            # runs the correct event using event_handlers mapping dict
            handler_result = event_handlers[event['type']](game_state, event, int_verbose)  
            if isinstance(handler_result, tuple):
                game_state['event_result'], sound_trigger = handler_result
            else:
                game_state['event_result'] = handler_result
            if event['type'] in ["trick", "attack"]:
                skip_action = True
            if int_verbose:
                create_log(f"MAIN_FLASK: RUN_ACTION: Event {event['type']} triggered: {event_result}")

        # handle multiple interactions in combats or puzzles if they are already initiated
        if game_state.get('active_puzzle') or game_state.get('active_combat'):
            skip_action = True
            if action_type == "combat" and game_state.get('active_combat'):
                event_result = resolve_combat(game_state, message, int_verbose)
            elif action_type == "puzzle" and game_state.get('active_puzzle'):
                event_result = resolve_puzzle(game_state, message, int_verbose)

        # handle actions that are not already initiated by events
        if not skip_action:
            if action_type == "dialogue":
                if int_verbose:
                    create_log(f"MAIN_FLASK: RUN_ACTION: Dialogue start")
                # flag to do not add suggestion to the response
                suggestion = None
                sound_trigger = "dialogue"
                # Get the NPC from user command and location from game state
                npc = details.get('npc', random.choice(list(game_state['npc_status'].keys())))
                # CHANGE 2: Update location reference to use 'name'
                location = game_state['location']['name']
                # END CHANGE 2
                # handle invalid NPC redirecting user to choose a valid one
                if npc not in game_state['npc_status']:
                    npc_list_string = ", ".join(npc['name'] for npc in game_state['npc_status'].values())
                    result = f"Você pode falar com: {npc_list_string}."
                    create_log(f"MAIN_FLASK: RUN_ACTION: Invalid NPC -{npc}- selected. Redirected user to {npc_list_string}", force_log=True)
                    false_npc = True
                    sound_trigger = "generic"
                #handle valid NPC dialogues
                else:
                    # If NPC is true ally and not perceived as one, create a dialogue confirming the NPC as ally
                    if game_state['npc_status'][npc]['status'] == 'Allied' and game_state['npc_status'][npc]['supposed_status'] != "Allied":
                        recent_history = format_chat_history(game_state['history'][-2:], game_state)
                        prompt = get_true_ally_confirmation_prompt(npc, location, recent_history)
                        response = client.chat.completions.create(
                            model=MODEL,
                            messages=[{"role": "user", "content": prompt}],
                            max_tokens=150,
                            temperature=0.0
                        ).choices[0].message.content
                        is_safe_result, violations = is_safe(response, int_verbose)
                        if not is_safe_result:
                            create_log(f"MAIN_FLASK: RUN_ACTION: Unsafe ally dialogue: {response}", force_log=True)
                            result = "Diálogo com NPC não permitido."
                        else:
                            game_state['npc_status'][npc]['supposed_status'] = 'Allied'
                            result = f"{response}"
                            if int_verbose:
                                create_log(f"MAIN_FLASK: RUN_ACTION: Confirmed {npc} as Allied")
                    # If NPC is not a true ally, just create a dialogue incorporating recent clue, if there is one
                    else:
                        incorporate_clue = f"Incorpore a pista: {game_state['recent_clue']['content']}." if game_state.get('recent_clue') else ""
                        prompt = get_npc_dialogue_prompt(npc, location, story_context, incorporate_clue)
                        response = client.chat.completions.create(
                            model=MODEL,
                            messages=[{"role": "user", "content": prompt}],
                            max_tokens=150,
                            temperature=0.0
                        ).choices[0].message.content
                        is_safe_result, violations = is_safe(response, int_verbose)
                        if not is_safe_result:
                            result = "Resposta do NPC não permitida."
                        else:
                            result = f"{response}"
                            if int_verbose:
                                create_log(f"MAIN_FLASK: RUN_ACTION - Generated dialogue with non true ally NPC" )
                # Updates NPC status in game state
                if not false_npc:
                    if game_state['npc_status'][npc]['supposed_status'] not in ['Allied', 'Suspeito']:
                        game_state['npc_status'][npc]['supposed_status'] = 'Contactado'

            elif action_type == "exploration":
                # CHANGE 3: Update exploration to use 'exploring_location'
                location = details.get('location', game_state['location']['name'])
                game_state['location']['exploring_location'] = location
                if int_verbose:
                    create_log(f"MAIN_FLASK: RUN_ACTION: Set exploring_location to {location}")
                # END CHANGE 3
                clues = json.dumps(game_state['clues'])
                if int_verbose:
                    create_log(f"MAIN_FLASK: RUN_ACTION: Exploration block start at {location}, clue_count: {clue_count}, true_clue_count: {len(game_state['true_clues'])}")  
                # Option selection second block - handles the selection obtained above 
                if handle_option_selection:
                    # sanitize option selection
                    if not message.strip().isdigit() or not (1 <= int(message) <= 3):
                        result = f"Por favor, escolha uma opção válida (1, 2, 3)."
                        game_state['history'].append({'role': 'assistant', 'content': result})
                        save_temp_game_state(game_state, int_verbose)
                        return result
                    if not game_state.get('active_options') or len(game_state['active_options']) != 3:
                        create_log(f"MAIN_FLASK: RUN_ACTION: Invalid active_options: {game_state.get('active_options')}", force_log=True)
                        game_state['waiting_for_option'] = False
                        game_state['active_options'] = []
                        game_state.pop('exploration_success', None)
                        result = f"Você não achou nada interessante dessa vez."
                        game_state['history'].append({'role': 'assistant', 'content': result})
                        save_temp_game_state(game_state, int_verbose)
                        return result
                    option_index = int(message) - 1
                    # Handles success choice related to clues 
                    # CHANGE 4: Update exploration_success to use 'exploring_location'
                    if option_index == game_state['exploration_success']['index'] and game_state['location']['exploring_location'] == game_state['exploration_success']['exploring_location']:
                        reward_type = game_state['exploration_success']['reward_type']
                        if int_verbose:
                            create_log(
                                f"MAIN_FLASK: RUN_ACTION: Success option selected: index={option_index}, "
                                f"details={game_state['active_options'][option_index]}, "
                                f"exploration_success={game_state['exploration_success']}, "
                                f"current_exploring_location={game_state['location']['exploring_location']}, "
                                f"reward_type={reward_type}",
                            )
                        # Handle clues
                        if reward_type in ["true_clue", "false_clue"]:
                            event_type = reward_type
                            option_description = game_state['active_options'][option_index][1]['description']
                            recent_history_with_action = recent_history + f"\nAção escolhida: {option_description}"
                            event = generate_random_events(game_state, event_type, recent_history_with_action, int_verbose)
                            
                            if int_verbose:
                                create_log(
                                    f"MAIN_FLASK: RUN_ACTION: generate_random_events returned: {event}"
                                    f"event_type={event_type}, clues_before={game_state['clues']}"
                                )
                            
                            if event and 'content' in event and 'id' in event:
                                clue = { 'content': event['content'], 'id': event['id'], 'false': reward_type == "false_clue"}
                                game_state['clues'].append(clue)
                                if reward_type == "true_clue":
                                    game_state['true_clues'].append(clue)
                                game_state['recent_clue'] = {"id": clue['id'], "content": clue['content']}
                                result = f"Você encontrou uma pista: {clue['content']}."
                                if int_verbose:
                                    create_log(f"MAIN_FLASK: RUN_ACTION: Awarded {reward_type}: {clue['content']}, id: {clue['id']}")
                            else:
                                create_log(f"MAIN_FLASK: RUN_ACTION: Failed to generate {reward_type}: {event}", force_log=True)
                                result = f"Você explorou, mas não encontrou nada relevante."
                        else:
                            result = f"Você explorou, mas não encontrou nada relevante."
                    else:
                        result = f"Você explorou, mas não encontrou nada relevante."
                    # Appending to history and ensuring persistence
                    game_state['history'].append({'role': 'assistant','content': result})
                    game_state['waiting_for_option'] = False
                    game_state['active_options'] = []
                    game_state.pop('exploration_success', None)
                    save_temp_game_state(game_state, int_verbose)
                    sound_trigger = "exploration"
                    result += "\n\nO que você deseja fazer agora?"
                    return result      
                # create clue             
                if not game_state.get('waiting_for_option'):
                    # Determine clue type via dice roll
                    clue_count = len([c for c in game_state['clues'] if c.get('false', False)])
                    true_clue_count = len(game_state['true_clues'])
                    clue_probs = []                   
                    if current_state in [2, 4] and clue_count < MAX_FALSE_CLUE:
                        if true_clue_count >= MAX_TRUE_CLUE:
                            reward_type = "false_clue"
                            if int_verbose:
                                create_log(f"MAIN_FLASK: RUN_ACTION: Forcing false_clue: true_clue_count={true_clue_count} >= MAX_TRUE_CLUE={MAX_TRUE_CLUE}")
                        else:
                            true_clue_prob = 0.5
                            false_clue_prob = 0.5
                            clue_probs = [("true_clue", true_clue_prob), ("false_clue", false_clue_prob)]
                            reward_type = random.choices([r[0] for r in clue_probs], weights=[r[1] for r in clue_probs], k=1)[0]
                            if int_verbose:
                                create_log(f"MAIN_FLASK: RUN_ACTION: Calculated clue_probs: true_clue={true_clue_prob}, false_clue={false_clue_prob}, selected: {reward_type}")
                    else:
                        clue_probs = [("none", 1.0)]
                        reward_type = "none"
                        if int_verbose:
                            create_log(f"MAIN_FLASK: RUN_ACTION: Set reward_type to none: clue_count={clue_count}, MAX_FALSE_CLUE={MAX_FALSE_CLUE}, current_state={current_state}")
                    if int_verbose:
                        create_log(f"MAIN_FLASK: RUN_ACTION: Exploration reward type: {reward_type}")
                    # Generate exploration options
                    prompt = get_exploration_prompt(location, recent_history, clues, reward_type)
                    try:
                        response = client.chat.completions.create(
                            model=MODEL,
                            messages=[{"role": "user", "content": prompt}],
                            max_tokens=200,
                            temperature=0.0
                        ).choices[0].message.content
                        if int_verbose:
                            create_log(f"MAIN_FLASK: RUN_ACTION: Exploration response: {response}")
                        is_safe_result = is_safe(response, int_verbose)
                        if not is_safe_result:
                            create_log(f"MAIN_FLASK: RUN_ACTION: Unsafe exploration response: {response}", force_log=True)
                            return "Resposta de exploração não permitida."
                        
                        try:
                            exploration_data = json.loads(response)
                            if not isinstance(exploration_data, dict) or 'description' not in exploration_data or 'options' not in exploration_data:
                                raise ValueError("Invalid exploration data structure")
                            result = exploration_data['description']
                            options = exploration_data['options']
                            if not isinstance(options, list) or len(options) != 3:
                                raise ValueError(f"Expected 3 options, got {len(options) if isinstance(options, list) else 'non-list'}")
                            # Validate option structure
                            for opt in options:
                                if not all(key in opt for key in ['description', 'action_type', 'outcome', 'reward']):
                                    raise ValueError(f"Invalid option structure: {opt}")
                            # Find success index
                            success_index = next((i for i, opt in enumerate(options) if opt['outcome'] == "success"), None)
                            if success_index is None:
                                raise ValueError("No success option found")
                            # shuffle options
                            shuffled_options = options.copy()
                            random.shuffle(shuffled_options)
                            new_success_index = next((i for i, opt in enumerate(shuffled_options) if opt['outcome'] == "success"), None)
                            if new_success_index is None:
                                raise ValueError("Success option lost during shuffle")
                            options = shuffled_options
                            success_index = new_success_index
                            if int_verbose:
                                create_log(f"MAIN_FLASK: RUN_ACTION: Shuffled options, new success_index: {success_index}")
                            # Store clue type in exploration_success for later processing
                            game_state['active_options'] = [(opt['action_type'], opt) for opt in options]
                            # CHANGE 5: Update exploration_success to use 'exploring_location'
                            game_state['exploration_success'] = {
                                'index': success_index,
                                'reward_type': reward_type,
                                'reward': '',
                                'exploring_location': location
                            }
                            # END CHANGE 5
                            game_state['waiting_for_option'] = True
                            result += "\nEscolha uma opção: - Digite apenas o número -\n" + "\n".join(f"{i+1}. {opt['description']}" for i, opt in enumerate(options))
                            # Append options to history for display
                            game_state['history'].append({
                                'role': 'assistant',
                                'content': result
                            })
                            save_temp_game_state(game_state, int_verbose)  # Ensure state is saved
                            if int_verbose:
                                create_log(f"MAIN_FLASK: RUN_ACTION: Stored options: {options}, success_index: {success_index}, history appended")
                        except (json.JSONDecodeError, ValueError) as e:
                            create_log(f"MAIN_FLASK: RUN_ACTION: Failed to parse or validate exploration response: {response}, Error: {str(e)}", force_log=True)
                            # Fallback options
                            options = [
                                {"description": f"Examinar um baú em {location}.", "action_type": "exploration", "outcome": "success" if reward_type != "none" else "none", "reward": "potion" if reward_type == "item" else ""},
                                {"description": f"Procurar nas sombras de {location}.", "action_type": "exploration", "outcome": "none", "reward": ""},
                                {"description": f"Inspecionar um cartaz em {location}.", "action_type": "exploration", "outcome": "none", "reward": ""}
                            ]
                            success_index = 0 if reward_type != "none" else None
                            game_state['active_options'] = [(opt['action_type'], opt) for opt in options]
                            # CHANGE 6: Update fallback exploration_success to use 'exploring_location'
                            game_state['exploration_success'] = {
                                'index': success_index,
                                'reward_type': reward_type,
                                'reward': options[0].get('reward') if success_index is not None else "",
                                'exploring_location': location
                            }
                            # END CHANGE 6
                            game_state['waiting_for_option'] = True
                            result = f"Você explora {location}, observando detalhes ao seu redor.\nEscolha uma opção: - Digite apenas o número - \n" + "\n".join(f"{i+1}. {opt['description']}" for i, opt in enumerate(options))
                            # Append fallback options to history
                            game_state['history'].append({
                                'role': 'assistant',
                                'content': result
                            })
                            save_temp_game_state(game_state, int_verbose)  # Ensure state is saved
                            if int_verbose:
                                create_log(f"MAIN_FLASK: RUN_ACTION: Using fallback options: {options}, history appended")
                    except Exception as e:
                        create_log(f"MAIN_FLASK: RUN_ACTION: Unexpected error in exploration: {str(e)}", force_log=True)
                        return f"Erro ao explorar {location}. Tente novamente."
                    sound_trigger = "exploration"

            elif action_type == "use_item":
                if int_verbose:
                    create_log(f"MAIN_FLASK: RUN_ACTION: Use_item block start")
                item = details.get('item')
                if item and item in game_state['resources']:
                    item_updates = [{"item": item, "change": -1}]
                    update_inventory(game_state, item_updates, int_verbose)
                    result = f"Você usou {item}. Quantidade restante: {game_state['resources'].get(item, 0)}."
                    sound_trigger = "use_item"
                else:
                    result = f"Item {item} não encontrado ou inválido."

            elif action_type == "investigate_npc":
                if int_verbose:
                    create_log(f"MAIN_FLASK: RUN_ACTION: Investigate block start")
                npc = details.get('npc', random.choice(list(game_state['npc_status'].keys())))
                # CHANGE 7: Update location reference to use 'name'
                location = game_state['location']['name']
                # END CHANGE 7
                if npc not in game_state['npc_status']:
                    result = f"Você descobriu que {npc} não está presente em {location} ou não é importante."
                    create_log(f"MAIN_FLASK: RUN_ACTION: Invalid NPC {npc} selected", force_log=True)
                    sound_trigger = "generic"
                else:
                    if game_state['npc_status'][npc]['status'] == 'Allied':
                        result = f"Você investigou {npc} e está certo que é confiável."
                        sound_trigger = "dialogue"
                    else:
                        game_state['npc_status'][npc]['supposed_status'] = 'Suspeito'
                        item_updates = [{"item": "suspect_marked", "change": 1}]
                        update_inventory(game_state, item_updates, int_verbose)
                        result = f"Você anotou no seu inventário para não esquecer que {npc} é suspeito."
                        sound_trigger = "generic"

            elif action_type == "combat":
                if int_verbose:
                    create_log(f"MAIN_FLASK: RUN_ACTION: Combat block start")
                if not game_state.get('active_combat'):
                    if current_state == 5:
                        hostile_npcs = [npc for npc in game_state['npc_status'] if game_state['npc_status'][npc]['status'] == 'Hostile']
                        hostile_npc = hostile_npcs[0] if hostile_npcs else "o Traidor"
                        event = {"type": "attack", "content": f"{hostile_npc} confronta você!", "clue": "Ataque rápido!", "tries": 0, "combat_type": "physical"}
                        result, sound_trigger = handle_combat(game_state, event, int_verbose)
                    else:
                        event = generate_random_events(game_state, 'attack', recent_history, int_verbose)
                        if event:
                            result, sound_trigger = handle_combat(game_state, event, int_verbose)
                        else:
                            result = "Nenhum inimigo aparece no momento."
                else:
                    result = resolve_combat(game_state, message, int_verbose)
                    sound_trigger = "combat"

            elif action_type == "puzzle":
                if int_verbose:
                    create_log(f"MAIN_FLASK: RUN_ACTION: Puzzle block start")
                if not game_state.get('active_puzzle'):
                    event = generate_random_events(game_state, 'trick', recent_history, int_verbose)
                    if event:
                        result, sound_trigger = handle_puzzle(game_state, event, int_verbose)
                    else:
                        result = "Nenhum enigma surge no momento."
                else:
                    result = resolve_puzzle(game_state, message, int_verbose)
                    sound_trigger = "puzzle"

            else:  # generic action
                if int_verbose:
                    create_log(f"MAIN_FLASK: RUN_ACTION: Generic action block start")
                # CHANGE 8: Update location reference to use 'name'
                location = game_state['location']['name']
                # END CHANGE 8
                exits = game_state['known_map'].get(location, {}).get('exits', [])
                story_context_with_exits = story_context + f"\nSaídas disponíveis para sair de {location}: {', '.join(exits) if exits else 'nenhuma'}."
                incorporate_clue = f"Incorpore a pista: {game_state['recent_clue']['content']}." if game_state.get('recent_clue') else ""
                prompt = get_general_action_prompt(game_state['game_objective'], details, location, story_context_with_exits, incorporate_clue)
                response = client.chat.completions.create(
                    model=MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=250,
                    temperature=0.0
                ).choices[0].message.content
                is_safe_result = is_safe(response, int_verbose)
                if not is_safe_result:
                    result = "Resposta genérica não permitida."
                else:
                    result = f"{response}"
                    suggestion = None
                    if int_verbose:
                        create_log(f"MAIN_FLASK: RUN_ACTION: Generic action response generated. Exits:\n{exits}")

        # Final result assembly block
        final_result = event_result if event_result else result.strip()
        if not final_result:
            # CHANGE 9: Update default message to use 'name'
            final_result = f"Sua ação em {game_state['location']['name']} não revela novas pistas."
            # END CHANGE 9
        # incorporate suggestion in response
        if suggestion and not skip_action and not game_state['waiting_for_option'] and (event_type is None or event_type != "attack"):
            final_result += f"\n\nSugestão: {suggestion}"
        
        # State transition control block
        if not game_state.get('waiting_for_option'):
            if current_state == 2 and clue_count >= MAX_FALSE_CLUE and true_clue_count >= 2:
                game_state['current_state'] = 3
                if int_verbose:
                    create_log(f"MAIN_FLASK: RUN_ACTION: State 2 to {3}: Collected {clue_count} false clues, {true_clue_count} true clues")
                final_result += f"\nVocê coletou pistas suficientes.\nVocê evoluiu para o nível 3!"
            elif current_state == 3 and any(
                game_state['npc_status'][npc]['supposed_status'] == 'Allied' and \
                game_state['npc_status'][npc]['status'] == 'Allied' for npc in game_state['npc_status']
            ) and ally_count >= MAX_FALSE_ALLY:
                game_state['current_state'] = 4
                if int_verbose:
                    create_log(f"MAIN_FLASK: RUN_ACTION: State 3 to {4}: Allied found, {ally_count} allies")
                final_result += "\nCom um aliado confiável e suspeitos identificados, você evoluiu para o nível 4!"
            elif current_state == 4 and len(game_state['true_clues']) >= 2:
                game_state['current_state'] = 5
                if int_verbose:
                    create_log(f"MAIN_FLASK: RUN_ACTION: State {4} to {5}: Two true clues collected")
                final_result += "\nVocê revelou o traidor! Prepare-se para a batalha final.\nVocê evoluiu para o nível 5!"
        else:
            create_log(f"MAIN_FLASK: RUN_ACTION: Skipped state transitions due to waiting_for_option", force_log=True)
        
        # Image and sound block
        generate_image = action_type in ["dialogue", "exploration", "combat", "puzzle", "investigate_npc", "generic"] or event_type in ["false_clue", "trick", "attack"]
        generated_image = DEFAULT_IMAGE_FILE_PATH
        ambient_sound = SOUND_MAP.get(sound_trigger, DEFAULT_AUDIO_FILE_PATH) if sound_trigger else game_state['ambient_sound']
        if sound_trigger and sound_trigger not in SOUND_MAP:
            create_log(f"Unmapped sound_trigger: {sound_trigger}, using default", force_log=True)

        update_game_state(
            game_state,
            output_image=generated_image,
            history=game_state['history'] + [{'role': 'user', "content": message}, {'role': 'assistant', 'content': final_result}],
            ambient_sound=ambient_sound
        )
        save_temp_game_state(game_state, int_verbose)
        return final_result

    except Exception as e:
        error_details = f"\n\nFailed in main_action: {e}\n{traceback.format_exc()}\n\n"
        create_log(f"\n\nRUN_ACTION ERROR:{error_details} - {str(e)}\n\n", str(e), force_log=True)
        return f"Error unexpected em ação: {str(e)}"






