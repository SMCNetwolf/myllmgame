import base64
import json
import datetime
import os
import re
import glob
import time
import sqlite3
import random
import uuid
from flask import session
from together import Together
from copy import deepcopy
from create_log import create_log
from dotenv import load_dotenv
from google.cloud import storage

from config import (
    VERBOSE, GCS_BUCKET_NAME, TOGETHER_API_KEY, MODEL, IS_SAFE_MODEL, IMAGE_MODEL, 
    INITIAL_IMAGE_FILE_PATH, DEFAULT_IMAGE_FILE_PATH, DEFAULT_AUDIO_FILE_PATH, 
    IMAGE_FILE_PREFIX, WORLD_PATH, SAVE_GAMES_PATH, TEMP_SAVES_PATH, DB_PATH, MAX_SAVE,
    ERROR_IMAGE_FILE_PATH, SOUND_MAP, bucket
)
from prompts import (
    everyone_content_policy, summarize_prompt_template, system_prompt, system_inventory_prompt,
    command_interpreter_prompt, get_false_clue_prompt, get_trick_prompt, get_attack_prompt,
    get_false_ally_prompt, get_is_safe_prompt, get_combat_resolution_prompt, get_check_clue_prompt
)


# Initialize Together API
together_api_key = TOGETHER_API_KEY
if not together_api_key:
    raise ValueError("TOGETHER_API_KEY not found ")
    create_log("\n\nMAIN_FLASK: TOGETHER_API_KEY not found\n\n", force_log=True)
client = Together(api_key=together_api_key)
    
# Initialize last_saved_history
last_saved_history = None

# Constants
MAX_TRIES = 3
MAX_FALSE_CLUE = 3
MAX_FALSE_ALLY = 3
MAX_TRICK = 3
MAX_ATTACKS = 3
EVENT_CHANCE = 0.3  # 30% chance to trigger an event
# Combat-related constants
SKILL = 50  # Base skill level (0-100)
INTELLIGENCE = 50  # Base intelligence level (0-100)
STRENGTH = 50  # Base strength level (0-100)

def validate_world():
    if not os.path.exists(WORLD_PATH):
        create_log(f"\n\nMAIN_FLASK: VALIDATE_WORLD: World file not found at {WORLD_PATH}\n\n", force_log=True)
        return False
    return True

def load_world():
    if validate_world():
        try:
            with open(WORLD_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            create_log(f"\n\nMAIN_FLASK: LOAD_WORLD: Error loading world: {str(e)}\n\n", force_log=True)
    return {}

def validate_game_state(game_state):
    required_keys = ['history', 'output_image', 'ambient_sound', 'current_state', 'health', 'resources', 'clues', 'npc_status', 'combat_results', 'puzzle_results', 'character', 'active_puzzle', 'active_combat']
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
    initial_game_state = {
        'history': [{"role": "assistant", "content": "Você acaba de chegar em Eldrida e a cidade está em polvorosa. Rumores se espalham sobre uma alta traição em vias de acontecer..."}],
        'output_image': INITIAL_IMAGE_FILE_PATH,
        'ambient_sound': DEFAULT_AUDIO_FILE_PATH,
        'location': 'Eldrida',
        'current_state': 1,
        'health': 10,
        'resources': {'wands': 2, 'potions': 2, 'energy': 5},
        'clues': [],
        'npc_status': {'Lyra': 'Neutral', 'Kael': 'Neutral'},
        'combat_results': [],
        'puzzle_results': [],
        'character': 'Herói',
        'active_puzzle': None,
        'active_combat': None,
        'skill': SKILL
    }
    if int_verbose:
        create_log(f"MAIN_FLASK: GET_INITIAL_GAME_STATE: Loaded initial game state")
    return initial_game_state

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

#temporarily disabled due to API limitations
''' 
def is_safe(message, int_verbose=False):
   try:
        prompt = f"{get_is_safe_prompt(everyone_content_policy)} {{{message}}}"
        response = client.completions.create(
            model=IS_SAFE_MODEL,
            prompt=prompt,
            max_tokens=50,
            temperature=0.0
        )
        raw_response = response.choices[0].text

        result = raw_response.strip('""" ').split()
        
        status = result[0].lower() if result else "safe"
        violations = result[1] if len(result) > 1 else "none"
        if status not in ["safe", "unsafe"]:
            create_log(f"MAIN_FLASK: IS_SAFE: Invalid status '{status}' in response: {raw_response}", force_log=True)
            status = "safe"
            violations = "none"
        if int_verbose:
            create_log(f"MAIN_FLASK: IS_SAFE: Status: {status}, Violations: {violations}, Prompt: {prompt}, Response: {raw_response}")
        return status == "safe", violations
    except Exception as e:
        create_log(f"\n\nMAIN_FLASK: Error in is_safe: {str(e)}\n\n", force_log=True)
        return True, str(e)
'''
def is_safe(message, int_verbose=False):
    create_log(f"MAIN_FLASK: IS_SAFE is temporarily disabled due to MODEL limitations", force_log=True)
    return True, "none"

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
            # Fallback for use_item actions
            if action_type == "use_item" and item in inventory:
                create_log(f"\n\nMAIN_FLASK: DETECT_INVENTORY_CHANGES: Falling back to default update for {item}\n\n", force_log=True)
                return [{"item": item, "change": -1}]
            return []
    except Exception as e:
        create_log(f"\n\nMAIN_FLASK: DETECT_INVENTORY_CHANGES: Unexpected error: {str(e)}\n\n", force_log=True)
        # Fallback for use_item actions
        if action_type == "use_item" and item in inventory:
            create_log(f"\n\nMAIN_FLASK: DETECT_INVENTORY_CHANGES: Falling back to default update for {item}\n\n", force_log=True)
            return [{"item": item, "change": -1}]
        return []

def update_game_state(game_state, **updates):
    """Update game state with provided key-value pairs."""
    game_state.update(updates)
    if VERBOSE:
        create_log(f'MAIN_FLASK: UPDATE_GAME_STATE - Updated game_state')
    return game_state

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

def generate_random_events(game_state, event_type, recent_history, int_verbose=False):
    """Generate a single event of the specified type using recent history."""
    temperature = 0.5
    current_state = game_state['current_state']
    events = []
    
    if event_type == "false_clue" and current_state in [1, 2]:
        response = client.chat.completions.create(
            model=MODEL,
            temperature=temperature,
            messages=[{"role": "user", "content": get_false_clue_prompt(recent_history)}]
        ).choices[0].message.content
        if int_verbose:
            create_log(f"MAIN_FLASK: GENERATE_RANDOM_EVENTS: Raw false_clue response: {response}")
        try:
            clue_data = json.loads(response)
            events.append({"type": "false_clue", "content": clue_data['clue'], "id": clue_data['id']})
        except json.JSONDecodeError:
            create_log(f"\n\nMAIN_FLASK: GENERATE_RANDOM_EVENTS: Invalid JSON for false_clue: {response}\n\n", force_log=True)
            json_match = re.search(r'\{.*?\}(?=\s*$|\s*\Z)', response, re.DOTALL)
            if json_match:
                try:
                    clue_data = json.loads(json_match.group(0))
                    events.append({"type": "false_clue", "content": clue_data['clue'], "id": clue_data['id']})
                except json.JSONDecodeError:
                    create_log(f"\n\nMAIN_FLASK: GENERATE_RANDOM_EVENTS: Regex failed for false_clue: {json_match.group(0)}\n\n", force_log=True)
    
    elif event_type == "trick" and current_state in [1, 2, 3, 4]:
        response = client.chat.completions.create(
            model=MODEL,
            temperature=temperature,
            messages=[{"role": "user", "content": get_trick_prompt(recent_history)}]
        ).choices[0].message.content
        if int_verbose:
            create_log(f"MAIN_FLASK: GENERATE_RANDOM_EVENTS: Raw trick response: {response}")
        try:
            trick_data = json.loads(response)
            events.append({"type": "trick", "content": trick_data['trick'], "solution": trick_data['solution'], "clues": trick_data['clues'], "tries": 0})
        except json.JSONDecodeError:
            create_log(f"\n\nMAIN_FLASK: GENERATE_RANDOM_EVENTS: Invalid JSON for trick: {response}\n\n", force_log=True)
            json_match = re.search(r'\{.*?\}(?=\s*$|\s*\Z)', response, re.DOTALL)
            if json_match:
                try:
                    trick_data = json.loads(json_match.group(0))
                    events.append({"type": "trick", "content": trick_data['trick'], "solution": trick_data['solution'], "clues": trick_data['clues'], "tries": 0})
                except json.JSONDecodeError:
                    create_log(f"\n\nMAIN_FLASK: GENERATE_RANDOM_EVENTS: Regex failed for trick: {json_match.group(0)}\n\n", force_log=True)
    
    elif event_type == "attack" and current_state in [1, 2, 3, 4]:
        combat_type = {
            1: "physical",
            2: "oral",
            3: "professional",
            4: "physical"
        }.get(current_state, "physical")
        response = client.chat.completions.create(
            model=MODEL,
            temperature=temperature,
            messages=[{"role": "user", "content": get_attack_prompt(combat_type, recent_history)}]
        ).choices[0].message.content
        try:
            attack_data = json.loads(response)
            events.append({"type": "attack", "content": attack_data['description'], "clue": attack_data['clue'], "tries": 0, "combat_type": combat_type})
        except json.JSONDecodeError:
            create_log(f"\n\nMAIN_FLASK: GENERATE_RANDOM_EVENTS: Invalid JSON for attack: {response}\n\n", force_log=True)
            json_match = re.search(r'\{.*?\}(?=\s*$|\s*\Z)', response, re.DOTALL)
            if json_match:
                try:
                    attack_data = json.loads(json_match.group(0))
                    events.append({"type": "attack", "content": attack_data['description'], "clue": attack_data['clue'], "tries": 0, "combat_type": combat_type})
                except json.JSONDecodeError:
                    create_log(f"\n\nMAIN_FLASK: GENERATE_RANDOM_EVENTS: Regex failed for attack: {json_match.group(0)}\n\n", force_log=True)
    
    elif event_type == "false_ally" and current_state == 3:
        response = client.chat.completions.create(
            model=MODEL,
            temperature=temperature,
            messages=[{"role": "user", "content": get_false_ally_prompt(recent_history)}]
        ).choices[0].message.content
        if int_verbose:
            create_log(f"MAIN_FLASK: GENERATE_RANDOM_EVENTS: Raw false_ally response: {response}")
        try:
            ally_data = json.loads(response)
            events.append({"type": "false_ally", "content": ally_data['npc'], "hint": ally_data['hint'], "id": ally_data['id']})
        except json.JSONDecodeError:
            create_log(f"\n\nMAIN_FLASK: GENERATE_RANDOM_EVENTS: Invalid JSON for false_ally: {response}\n\n", force_log=True)
            json_match = re.search(r'\{.*?\}(?=\s*$|\s*\Z)', response, re.DOTALL)
            if json_match:
                try:
                    ally_data = json.loads(json_match.group(0))
                    events.append({"type": "false_ally", "content": ally_data['npc'], "hint": ally_data['hint'], "id": ally_data['id']})
                except json.JSONDecodeError:
                    create_log(f"\n\nMAIN_FLASK: GENERATE_RANDOM_EVENTS: Regex failed for false_ally: {json_match.group(0)}\n\n", force_log=True)
    

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
            create_log(f'\n\nMAIN_FLASK: UPDATE_INVENTORY - Invalid update: {update}\n\n')
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
    """Handle a false_clue event, adding clue, awarding item, and generating dialogue."""
    clue = {"content": event['content'], "id": event['id'], "false": True}
    game_state['clues'].append(clue)
    game_state['recent_clue'] = {"id": event['id'], "content": event['content']}
    
    # Award mysterious_note
    item_updates = [{"item": "mysterious_note", "change": 1}]
    update_inventory(game_state, item_updates, int_verbose)
    
    # Generate immediate dialogue using recent context
    story_context = format_chat_history(game_state['history'][-4:], game_state)
    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": f"Gere um diálogo com um NPC em Eldrida comentando a pista falsa: {event['content']}. Contexto recente: {story_context}"}],
        max_tokens=100,
        temperature=0.0
    ).choices[0].message.content
    
    is_safe_result, violations = is_safe(response, int_verbose)
    if not is_safe_result:
        create_log(f"MAIN_FLASK: HANDLE_FALSE_CLUE: Unsafe dialogue: {response}", force_log=True)
        return "Diálogo sobre pista não permitido."
    
    if int_verbose:
        create_log(f"MAIN_FLASK: HANDLE_FALSE_CLUE: Added clue: {clue}, Item: mysterious_note, Dialogue: {response}")
    
    return f"{event['content']}\n{response}"

def handle_false_ally(game_state, event, int_verbose=False):
    """Handle a false_ally event, marking an NPC as suspect and generating dialogue."""
    npc = event['content']
    hint = event['hint']
    game_state['npc_status'][npc] = "Suspeito"
    game_state['recent_false_ally'] = {"npc": npc, "hint": hint, "id": event['id']}
    
    # Award suspect_token
    item_updates = [{"item": "suspect_token", "change": 1}]
    update_inventory(game_state, item_updates, int_verbose)
    
    # Generate immediate dialogue using recent context
    story_context = format_chat_history(game_state['history'][-4:], game_state)
    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": f"Gere um diálogo com um NPC em Eldrida comentando o suspeito {npc}: {hint}. Contexto recente: {story_context}"}],
        max_tokens=100,
        temperature=0.0
    ).choices[0].message.content
    
    is_safe_result, violations = is_safe(response, int_verbose)
    if not is_safe_result:
        create_log(f"MAIN_FLASK: HANDLE_FALSE_ALLY: Unsafe dialogue: {response}", force_log=True)
        return "Diálogo sobre suspeito não permitido."
    
    if int_verbose:
        create_log(f"MAIN_FLASK: HANDLE_FALSE_ALLY: Marked {npc} as suspect, Item: suspect_token, Dialogue: {response}")
    
    return f"Você marcou {npc} como suspeito: {hint}\n{response}"

def handle_combat(game_state, event, int_verbose=False):
    """Prepare a combat event, generating new clues for retries and rendering for new combats."""
    combat = game_state.get('active_combat', event)
    story_context = format_chat_history(game_state['history'][-4:], game_state)

    if int_verbose:
        create_log(f"MAIN_FLASK: HANDLE_COMBAT: Entered with combat: {combat}")

    # Check if combat is lost
    if combat['tries'] >= MAX_TRIES:
        game_state['combat_results'].append({"enemy": combat['content'], "won": False})
        game_state['health'] = max(0, game_state['health'] - 2)
        game_state['active_combat'] = None
        create_log(f"MAIN_FLASK: HANDLE_COMBAT: Combat lost after {MAX_TRIES} tries", force_log=True)
        return None, None  # Returns tuple for compatibility with callers expecting (response, sound_trigger)

    # Generate new clue for retries (tries > 0)
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

    # Return narrative including the clue for all tries
    narrative = f"PERIGO!: {combat['content']} Dica: {combat['clue']} (Tentativa {combat['tries'] + 1}/{MAX_TRIES})"
    if int_verbose:
        create_log(f"MAIN_FLASK: HANDLE_COMBAT: Updated combat: {combat['content']}, Clue: {combat['clue']}, Try: {combat['tries'] + 1}/{MAX_TRIES}")
    
    return narrative, "combat"

def resolve_combat(game_state, action, int_verbose=False):
    """Resolve a combat event with random success probability and immersive narrative output."""
    percent_success = 0.3  # Lowered from 0.5 to reduce win probability
    combat = game_state.get('active_combat')
    if not combat:
        if int_verbose:
            create_log("MAIN_FLASK: RESOLVE_COMBAT: No active combat")
        return "Nenhum combate ativo."

    story_context = format_chat_history(game_state['history'][-4:], game_state)
    combat['tries'] += 1
    if int_verbose:
        create_log(f"MAIN_FLASK: RESOLVE_COMBAT: Updated combate tries to {combat['tries']}")

    # Calculate base win probability (0 to 1)
    base_win_prob = percent_success * (game_state['health'] / 10.0) * 0.4 + (game_state.get('skill', SKILL) / 100.0) * 0.3 + (INTELLIGENCE / 100.0) * 0.2 + (STRENGTH / 100.0) * 0.1

    # Evaluate if clue was used
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

    win_prob = base_win_prob + 0.2 if clue_used else base_win_prob  # 20% boost if clue is used
    win_prob = min(max(win_prob, 0.0), 1.0)  # Clamp between 0 and 1

    # Determine success
    won = random.random() < win_prob
    if int_verbose:
        create_log(f"MAIN_FLASK: RESOLVE_COMBAT: Combat status: win probability: {win_prob}; won? {won}")

    # Update stats
    old_health = game_state['health']
    old_skill = game_state.get('skill', SKILL)
    game_state['skill'] = old_skill * 1.1  # Increase skill by 10%
    game_state['health'] = max(0, old_health * 0.9)  # Decrease health by 10%
    cost = {"health": 2 if not won else 1} if combat.get('combat_type', 'physical') == "physical" else {"energy": 2 if not won else 1}

    # Apply cost
    for key, value in cost.items():
        if key == "health":
            game_state['health'] = max(0, game_state['health'] - value)
        else:
            game_state['resources'][key] = max(0, game_state['resources'].get(key, 0) - value)

    # Determine result status
    result_status = "won" if won else "lost" if combat['tries'] >= MAX_TRIES else "ongoing"
    resultado = "vitória" if result_status == "won" else "derrota" if result_status == "lost" else "em andamento"

    # Generate narrative response
    prompt = get_combat_resolution_prompt(
        combat['content'],
        action,
        combat['clue'],
        resultado,
        old_health,
        game_state['health'],
        old_skill,
        game_state['skill'],
        story_context,
        combat['tries'],  # Ensure correct try number is passed
        MAX_TRIES
    )
    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3
    ).choices[0].message.content

    # Safety check
    is_safe_result, violations = is_safe(response, int_verbose)
    if not is_safe_result:
        create_log(f"MAIN_FLASK: RESOLVE_COMBAT: Unsafe response: {response}", force_log=True)
        response = (
            f"Sua ação não surtiu o efeito desejado, e a batalha tomou um rumo inesperado. Tente uma nova estratégia."
            if result_status == "ongoing"
            else "Sua ação não surtiu o efeito desejado, e a batalha terminou em derrota."
            if result_status == "lost"
            else "Você triunfou na batalha, mas a vitória teve um preço inesperado."
        )

    # Append clue and try number to response for ongoing combats
    tent_count_not_in_response = False if f"(Tentativa {combat['tries']}/{MAX_TRIES})" in response else True
    if int_verbose:
        create_log(f"tent_count_not_in_response: ")
    if result_status == "ongoing" and tent_count_not_in_response:
        response += f"\nDica: {combat['clue']} (Tentativa {combat['tries']}/{MAX_TRIES})"

    # Resolve combat
    if won or combat['tries'] >= MAX_TRIES:
        game_state['combat_results'].append({"enemy": combat['content'], "won": won})
        game_state['active_combat'] = None
    else:
        # Prepare next attempt by updating clue
        handle_combat(game_state, combat, int_verbose)  # Updates game_state['active_combat'] with new clue

    if int_verbose:
        create_log(f"MAIN_FLASK: RESOLVE_COMBAT: Combat {result_status}, action: {action}, Win prob: {win_prob:.2f}, Clue used: {clue_used}, New skill: {game_state['skill']:.1f}, New health: {game_state['health']:.1f}, Response: {response}")

    return response

def handle_puzzle(game_state, event, int_verbose=False):
    """Handle a puzzle event, ensuring no auto-resolution."""
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
        result = f"Quebra-cabeça: {puzzle['content']} {'Resolvido!' if solved else f'Falhou após {MAX_TRIES} tentativas.'}"
    else:
        result = f"Quebra-cabeça: {puzzle['content']} Dica: {puzzle['clues'][puzzle['tries']]}"
    
    if int_verbose:
        create_log(f"MAIN_FLASK: RESOLVE_PUZZLE: Puzzle {'resolvido' if solved else 'ongoing' if puzzle['tries'] < MAX_TRIES else 'falhou'}, solution: {solution}")
    return result

def save_temp_game_state(game_state, int_verbose=False):
    global last_saved_history
    if last_saved_history != game_state['history']:
        for attempt in range(3):  # Retry up to 3 times
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
                time.sleep(1)  # Wait before retrying

def run_action(message, game_state, int_verbose=False):
    """Process a player command and update game state."""
    try:
        # Safety check
        if not is_safe(message, int_verbose)[0]:
            create_log(f"\n\nMAIN_FLASK: RUN_ACTION: Unsafe message: {message}\n\n", force_log=True)
            return "Mensagem não permitida."

        # Check for option selection
        if message.strip().isdigit() and game_state.get('active_options'):
            option_index = int(message) - 1
            if 0 <= option_index < len(game_state['active_options']):
                action_type, details = game_state['active_options'][option_index]
                game_state['active_options'] = None
                create_log(f"MAIN_FLASK: RUN_ACTION: Selected option {message}: {action_type}, {details}", force_log=True)
            else:
                return "Opção inválida. Escolha um número válido."
        else:
            action_type, details, suggestion = None, {}, ""

        current_state = game_state['current_state']
        story_context = format_chat_history(game_state['history'], game_state)
        recent_history = format_chat_history(game_state['history'][-4:], game_state)

        # Interpret command if not an option
        if action_type is None:
            prompt = command_interpreter_prompt.format(
                story_context=story_context,
                event_info="",
                command=message,
            )
            response = client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=100,
                temperature=0.0
            ).choices[0].message.content
            if int_verbose:
                create_log(f"MAIN_FLASK: RUN_ACTION: Command interpreter response: {response}")
            try:
                command_data = json.loads(response)
                command_data.setdefault("action_type", "generic")
                command_data.setdefault("details", {})
                command_data.setdefault("suggestion", "")
            except json.JSONDecodeError:
                create_log(f"MAIN_FLASK: RUN_ACTION: JSON parsing failed: {response}", force_log=True)
                json_match = re.search(r'\{.*?\}(?=\s*$|\s*\Z)', response, re.DOTALL)
                if json_match:
                    command_data = json.loads(json_match.group(0))
                    command_data.setdefault("action_type", "generic")
                    command_data.setdefault("details", {})
                    command_data.setdefault("suggestion", "")
                else:
                    command_data = {"action_type": "generic", "details": {}, "suggestion": ""}
                    return "Comando não reconhecido, tente algo como 'falar com Lyra' ou 'explorar taverna'."
            action_type = command_data["action_type"]
            details = command_data["details"]
            suggestion = command_data["suggestion"]

        result = ""
        clue_count = len([c for c in game_state['clues'] if c.get('false')])
        combat_count = len(game_state['combat_results'])
        puzzle_count = len(game_state['puzzle_results'])
        ally_count = len([n for n, s in game_state['npc_status'].items() if s == "Suspeito"])

        # Event triggering logic
        event_handlers = {
            "false_clue": handle_false_clue,
            "trick": handle_puzzle,
            "attack": handle_combat,
            "false_ally": handle_false_ally
        }
        event_type = None
        trigger_event = False
        allowed_events = []
        if current_state == 1:
            allowed_events = ["false_clue", "trick", "attack"] if clue_count < MAX_FALSE_CLUE or puzzle_count < MAX_TRICK or combat_count < MAX_ATTACKS else []
        elif current_state == 2:
            allowed_events = ["false_clue", "trick", "attack"] if clue_count < MAX_FALSE_CLUE or puzzle_count < MAX_TRICK or combat_count < MAX_ATTACKS else []
        elif current_state == 3:
            allowed_events = ["trick", "attack", "false_ally"] if puzzle_count < MAX_TRICK or combat_count < MAX_ATTACKS or ally_count < MAX_FALSE_ALLY else []
        elif current_state == 4:
            allowed_events = ["trick", "attack"] if puzzle_count < MAX_TRICK or combat_count < MAX_ATTACKS else []
        if allowed_events and action_type == "exploration":
            event_type = random.choice(allowed_events)
            trigger_event = True


        #*****************************************************
        #DEBUG: forcing creation of attack event
        if game_state.get('active_combat') is None:
            trigger_event = True
            action_type = "exploration"
            event_type = "attack"
        else:
            trigger_event = False
            action_type = "combat"
        #*****************************************************


        event_result = ""
        sound_trigger = None
        skip_action = False


        if trigger_event:
            event = generate_random_events(game_state, event_type, recent_history, int_verbose)
            if int_verbose:
                create_log(f"MAIN_FLASK: RUN_ACTION: Event generated: {event}")
            if not event or not isinstance(event, dict) or 'type' not in event or event['type'] not in event_handlers:
                create_log(f"MAIN_FLASK: RUN_ACTION: Invalid event: {event}", force_log=True)
                event_result = "Nenhum evento ocorre no momento."
            else:
                # Set active_combat or active_puzzle before handler
                if event['type'] == "attack":
                    game_state['active_combat'] = event
                elif event['type'] == "trick":
                    game_state['active_puzzle'] = event
                handler_result = event_handlers[event['type']](game_state, event, int_verbose)
                if isinstance(handler_result, tuple):
                    event_result, sound_trigger = handler_result
                else:
                    event_result = handler_result
                if event['type'] in ["trick", "attack"]:
                    skip_action = True
                if int_verbose:
                    create_log(f"MAIN_FLASK: RUN_ACTION: Event {event['type']} triggered: {event_result}")


        if game_state.get('active_puzzle') or game_state.get('active_combat'):
            skip_action = True
            if action_type == "combat" and game_state.get('active_combat'):
                event_result = resolve_combat(game_state, message, int_verbose)
                if int_verbose:
                    create_log(f"MAIN_FLASK: RUN_ACTION: Combat result from resolve_combat: {event_result}")
            elif action_type == "puzzle" and game_state.get('active_puzzle'):
                event_result = resolve_puzzle(game_state, message, int_verbose)
    
        if not skip_action:

            if action_type == "dialogue":
                npc = details.get('npc', 'Lyra')
                prompt = f"Gere um diálogo com {npc}. Contexto: {story_context}\nEventos recentes: {event_result}"
                if game_state.get('recent_clue'):
                    prompt += f"\nIncorpore a pista recente: {game_state['recent_clue']['content']}"
                if game_state.get('recent_false_ally'):
                    prompt += f"\nIncorpore o suspeito: {game_state['recent_false_ally']['npc']} - {game_state['recent_false_ally']['hint']}"
                response = client.chat.completions.create(
                    model=MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=100,
                    temperature=0.0
                ).choices[0].message.content
                is_safe_result, violations = is_safe(response, int_verbose)
                if not is_safe_result:
                    return "Resposta do NPC não permitida."
                result = f"{response}"
                sound_trigger = "conversation"
                game_state['npc_status'][npc] = "Contactado"

            elif action_type == "exploration":
                location = details.get('location', 'Taverna')
                prompt = f"Explore {location} em busca de pistas. Contexto: {story_context}\nEventos recentes: {event_result}"
                if game_state.get('recent_clue'):
                    prompt += f"\nIncorpore a pista recente: {game_state['recent_clue']['content']}"
                if game_state.get('recent_false_ally'):
                    prompt += f"\nIncorpore o suspeito: {game_state['recent_false_ally']['npc']} - {game_state['recent_false_ally']['hint']}"
                response = client.chat.completions.create(
                    model=MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=150,
                    temperature=0.0
                ).choices[0].message.content
                is_safe_result, violations = is_safe(response, int_verbose)
                if not is_safe_result:
                    return "Resposta de exploração não permitida."
                result = f"{response}"
                sound_trigger = "tavern" if location.lower() == "taverna" else "city_streets"
                # JSON options
                options_prompt = get_exploration_options_prompt(response)
                options_response = client.chat.completions.create(
                    model=MODEL,
                    messages=[{"role": "user", "content": options_prompt}],
                    max_tokens=100,
                    temperature=0.0
                ).choices[0].message.content
                try:
                    options_data = json.loads(options_response)
                    valid_actions = ["dialogue", "exploration", "combat", "puzzle", "use_item", "false_ally", "generic"]
                    game_state['active_options'] = [
                        (opt['action'], opt['details'])
                        for opt in options_data.get('options', [])
                        if opt.get('action') in valid_actions
                    ]
                    if game_state['active_options']:
                        result += "\nEscolha uma opção digitando o número correspondente."
                    else:
                        create_log(f"MAIN_FLASK: RUN_ACTION: No valid options generated, using fallback", force_log=True)
                        game_state['active_options'] = [
                            ("exploration", {"location": "Taverna"}),
                            ("dialogue", {"npc": "Lyra"})
                        ]
                        result += "\nEscolha uma opção: 1. Explorar a Taverna 2. Falar com Lyra"
                except json.JSONDecodeError:
                    create_log(f"MAIN_FLASK: RUN_ACTION: Invalid JSON for exploration options: {options_response}", force_log=True)
                    game_state['active_options'] = [
                        ("exploration", {"location": "Taverna"}),
                        ("dialogue", {"npc": "Lyra"})
                    ]
                    result += "\nEscolha uma opção: 1. Explorar a Taverna 2. Falar com Lyra"

            elif action_type == "use_item":
                item = details.get('item')
                if item and item in game_state['resources']:
                    item_updates = [{"item": item, "change": -1}]
                    update_inventory(game_state, item_updates, int_verbose)
                    result = f"Você usou {item}. Quantidade restante: {game_state['resources'].get(item, 0)}."
                else:
                    result = f"Item {item} não encontrado ou inválido."

            elif action_type == "combat":
                if not game_state.get('active_combat'):
                    event = generate_random_events(game_state, "attack", recent_history, int_verbose)
                    if event:
                        result, sound_trigger = handle_combat(game_state, event, int_verbose)
                    else:
                        result = "Nenhum inimigo aparece no momento."
                else:
                    result = resolve_combat(game_state, message, int_verbose)
                    sound_trigger = "combat"

            elif action_type == "puzzle":
                if not game_state.get('active_puzzle'):
                    event = generate_random_events(game_state, "trick", recent_history, int_verbose)
                    if event:
                        result, sound_trigger = handle_puzzle(game_state, event, int_verbose)
                    else:
                        result = "Nenhum enigma surge no momento."
                else:
                    result = resolve_puzzle(game_state, message, int_verbose)
                    sound_trigger = "puzzle"

            elif action_type == "false_ally":
                npc = details.get('npc', 'Kael')
                game_state['npc_status'][npc] = "Suspeito"
                item_updates = [{"item": "suspect_token", "change": 1}]
                update_inventory(game_state, item_updates, int_verbose)
                result = f"Você marcou {npc} como suspeito. Obteve: suspect_token."

            else:  # generic
                prompt = f"Responda ao comando em Eldrida. Contexto: {story_context}\nComando: {message}\nEventos recentes: {event_result}"
                if game_state.get('recent_clue'):
                    prompt += f"\nIncorpore a pista recente: {game_state['recent_clue']['content']}"
                if game_state.get('recent_false_ally'):
                    prompt += f"\nIncorpore o suspeito: {game_state['recent_false_ally']['npc']} - {game_state['recent_false_ally']['hint']}"
                response = client.chat.completions.create(
                    model=MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=100,
                    temperature=0.0
                ).choices[0].message.content
                is_safe_result, violations = is_safe(response, int_verbose)
                if not is_safe_result:
                    return "Resposta genérica não permitida."
                result = f"{response}"

        # Combine results
        final_result = event_result if event_result else result.strip()
        if not final_result:
            final_result = "Your actions in Eldrida yield no new leads about the traitor."
        # Suppress suggestion for false_clue/false_ally
        if suggestion and not skip_action and event_type not in ["false_clue", "false_ally"]:
            final_result += f"\nSugestão: {suggestion}"

        # State transitions
        if current_state == 1 and any("traidor" in c['content'].lower() for c in game_state['clues']):
            game_state['current_state'] = 2
            final_result += "\nVocê descobriu pistas do traidor. Vá à taverna coletar mais."
        elif current_state == 2 and clue_count >= MAX_FALSE_CLUE:
            game_state['current_state'] = 3
            final_result += "\nVocê coletou pistas suficientes. Investigue os suspeitos."
        elif current_state == 3 and ally_count >= MAX_FALSE_ALLY:
            game_state['current_state'] = 4
            final_result += "\nVocê identificou suspeitos. Confronte o traidor."

        # Inventory and image updates
        generate_image = action_type in ["dialogue", "exploration", "combat", "puzzle"] or event_type in ["false_clue", "trick", "attack", "false_ally"]
        generated_image_path = image_generator(final_result, int_verbose) if generate_image else None

        # Update game state
        updated_history = game_state['history'] + [{"role": "user", "content": message}, {"role": "assistant", "content": final_result}]
        update_game_state(
            game_state,
            output_image=generated_image_path if generated_image_path else ERROR_IMAGE_FILE_PATH,
            history=updated_history,
            #TODO: maybe this is wrong. sound_trigger is a string, not a path.
            ambient_sound = SOUND_MAP.get(sound_trigger, game_state['ambient_sound']) if sound_trigger else game_state['ambient_sound']
        )
        save_temp_game_state(game_state, int_verbose)
        return final_result

    except Exception as e:
        create_log(f"\n\nMAIN_FLASK: Error in run_action: {str(e)}\n\n", force_log=True)
        return "Erro em run_action - Algo deu errado."








