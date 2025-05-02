from create_log import verbose, create_log
import os
import logging
import json
from flask import Flask, render_template, request, session, redirect, url_for, flash, make_response
from flask_session import Session
from dotenv import load_dotenv
from main_flask import run_action, get_initial_game_state, format_chat_history, confirm_save, retrieve_game_list, retrieve_game
import time

# Load environment variables
load_dotenv()
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET")
if not app.secret_key:
    raise ValueError("SESSION_SECRET not found in .env file")

# Configure session settings (server-side)
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = 'flask_session'
app.config['SESSION_PERMANENT'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = 3600
app.config['SESSION_COOKIE_SECURE'] = False
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_NAME'] = 'rpg_session'
Session(app)

# Configure logging
logging.basicConfig(level=logging.DEBUG)

def get_relative_image_path(full_path):
    """Strip 'static/' from image path to get relative path for url_for."""
    if not full_path:
        return "default_image.png"
    return full_path.split('static/')[-1] if 'static/' in full_path else full_path

def validate_game_state(game_state):
    """Validate that game_state has required keys."""
    required_keys = ['world', 'kingdom', 'town', 'character', 'inventory', 'history', 'output_image']
    return isinstance(game_state, dict) and all(key in game_state for key in required_keys)

def save_temp_game_state(game_state, verbose=False):
    """Save game_state to a temporary file for recovery."""
    global last_saved_history
    if last_saved_history != game_state['history']:
        try:
            os.makedirs('temp_saves', exist_ok=True)
            temp_save_path = 'temp_saves/last_session.json'
            with open(temp_save_path, 'w', encoding='utf-8') as f:
                json.dump({'game_state': game_state}, f, ensure_ascii=False, indent=4)
            last_saved_history = game_state['history']
            if verbose:
                create_log(f"SAVE_TEMP_GAME_STATE: Saved game state to {temp_save_path}")
        except Exception as e:
            if verbose:
                create_log(f"SAVE_TEMP_GAME_STATE: Error saving temp game state: {str(e)}")

def load_temp_game_state(verbose=False):
    """Load game_state from temporary file if it exists."""
    temp_save_path = 'temp_saves/last_session.json'
    try:
        if os.path.exists(temp_save_path):
            with open(temp_save_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                game_state = data.get('game_state')
                if validate_game_state(game_state):
                    if verbose:
                        create_log(f"LOAD_TEMP_GAME_STATE: Loaded game state from {temp_save_path}")
                    return game_state
                else:
                    if verbose:
                        create_log(f"LOAD_TEMP_GAME_STATE: Invalid game state in {temp_save_path}")
        else:
            if verbose:
                create_log(f"LOAD_TEMP_GAME_STATE: No temp save file found at {temp_save_path}")
    except Exception as e:
        if verbose:
            create_log(f"LOAD_TEMP_GAME_STATE: Error loading temp game state: {str(e)}")
    return None

def clean_temp_saves(verbose=False):
    import glob
    import time
    temp_save_path = 'temp_saves/last_session.json'
    if os.path.exists(temp_save_path):
        if time.time() - os.path.getmtime(temp_save_path) > 86400:  # 24 hours
            os.remove(temp_save_path)
            if verbose:
                create_log("CLEAN_TEMP_SAVES: Removed old temp save")

last_saved_history = None

@app.route("/")
def index():
    """Render the index page and initialize game state."""
    session.permanent = True
    if verbose:
        create_log('APP ROUTE /: Entering index route')
        create_log(f'APP ROUTE /: Session ID: {session.get("_id", "Unknown")}')
        create_log(f'APP ROUTE /: Session contents: {dict(session)}')
        create_log(f'APP ROUTE /: Timestamp: {time.strftime("%Y-%m-%d %H:%M:%S")}')

    if 'game_state' not in session or not validate_game_state(session['game_state']):
        temp_game_state = load_temp_game_state(verbose=verbose)
        if temp_game_state:
            session['game_state'] = temp_game_state
            if verbose:
                create_log('APP ROUTE /: Restored game state from temp save')
        else:
            if verbose:
                create_log('APP ROUTE /: Game state was not in session or invalid. Initializing game state')
            session['game_state'] = get_initial_game_state()
        session.modified = True
        if verbose:
            create_log(f"APP ROUTE /: Game state initialized: {session['game_state']}")

    raw_image_path = session['game_state']['output_image']
    image_filename = get_relative_image_path(raw_image_path)
    if verbose:
        create_log(f"APP ROUTE /: Raw image path: {raw_image_path}")
        create_log(f"APP ROUTE /: Rendering index.html with image_filename: {image_filename}")
        create_log(f"APP ROUTE /: Image URL: {url_for('static', filename=image_filename)}")

    response = make_response(render_template("index.html"))
    response.headers['Cache-Control'] = 'no-store'
    return response

@app.route("/game", methods=["GET"])
def game():
    """Render the game page."""
    session.permanent = True
    if verbose:
        create_log(f"APP ROUTE /GAME: Entering game route")
        create_log(f"APP ROUTE /GAME: Session ID: {session.get('_id', 'Unknown')}")
        create_log(f"APP ROUTE /GAME: Session contents: {dict(session)}")
        create_log(f"APP ROUTE /GAME: Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    if 'game_state' not in session or not validate_game_state(session['game_state']):
        temp_game_state = load_temp_game_state(verbose=verbose)
        if temp_game_state:
            session['game_state'] = temp_game_state
            if verbose:
                create_log('APP ROUTE /GAME: Restored game state from temp save')
        else:
            if verbose:
                create_log("APP ROUTE /GAME: Game state not in session or invalid. Initializing game state")
            session['game_state'] = get_initial_game_state()
        session.modified = True

    raw_image_path = session['game_state']['output_image']
    image_filename = get_relative_image_path(raw_image_path)
    if verbose:
        create_log(f"APP ROUTE /GAME: Raw image path: {raw_image_path}")
        create_log(f"APP ROUTE /GAME: Rendering game.html with image_filename: {image_filename}")
        create_log(f"APP ROUTE /GAME: Image URL: {url_for('static', filename=image_filename)}")
        create_log(f"APP ROUTE /GAME: game state history is now: {session['game_state']['history']}")

    response = make_response(render_template("game.html",
                                            output="",
                                            output_image=image_filename,
                                            chat_history=format_chat_history(session['game_state']['history'], session['game_state'])))
    response.headers['Cache-Control'] = 'no-store'
    return response

@app.route("/command", methods=["POST"])
def process_command():
    """Process a user command and update game state."""
    session.permanent = True
    command = request.form.get("command")
    if verbose:
        create_log(f"APP ROUTE /COMMAND: entering command route:\ncommand is: {command}")
        create_log(f"APP ROUTE /COMMAND: Session ID: {session.get('_id', 'Unknown')}")
        create_log(f"APP ROUTE /COMMAND: Session cookie: {request.cookies.get('rpg_session', 'None')}")
        create_log(f"APP ROUTE /COMMAND: Session contents: {dict(session)}")
        create_log(f"APP ROUTE /COMMAND: Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    if 'game_state' not in session or not validate_game_state(session['game_state']):
        temp_game_state = load_temp_game_state(verbose=verbose)
        if temp_game_state:
            session['game_state'] = temp_game_state
            if verbose:
                create_log('APP ROUTE /COMMAND: Restored game state from temp save')
        else:
            if verbose:
                create_log("APP ROUTE /COMMAND: Game state not in session or invalid. Initializing game state")
            session['game_state'] = get_initial_game_state()
        session.modified = True

    output = run_action(command, session['game_state'], verbose=verbose)
    if verbose:
        create_log(f"APP ROUTE /COMMAND: run_action output: {output}")
    if not isinstance(output, str):
        create_log(f"APP ROUTE /COMMAND: Error: run_action returned non-string: {type(output)}")
        output = "Error: Invalid response from run_action"
    
    session.modified = True
    save_temp_game_state(session['game_state'], verbose=verbose)
    
    raw_image_path = session['game_state']['output_image']
    image_filename = get_relative_image_path(raw_image_path)
    if verbose:
        create_log(f"APP ROUTE /COMMAND: Raw image path: {raw_image_path}")
        create_log(f"APP ROUTE /COMMAND: Rendering game.html with image_filename: {image_filename}")
        create_log(f"APP ROUTE /COMMAND: Image URL: {url_for('static', filename=image_filename)}")
    
    response = make_response(render_template("game.html",
                                            output="",
                                            output_image=image_filename,
                                            chat_history=format_chat_history(session['game_state']['history'], session['game_state'])))
    response.headers['Cache-Control'] = 'no-store'
    return response

@app.route("/save_game", methods=["POST"])
def save():
    """Save the game state with a user-specified filename."""
    session.permanent = True
    if verbose:
        create_log(f"APP ROUTE /SAVE_GAME: Entering save game route")
        create_log(f"APP ROUTE /SAVE_GAME: Session ID: {session.get('_id', 'Unknown')}")
        create_log(f"APP ROUTE /SAVE_GAME: Session contents: {dict(session)}")
        create_log(f"APP ROUTE /SAVE_GAME: Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    if 'game_state' not in session or not validate_game_state(session['game_state']):
        temp_game_state = load_temp_game_state(verbose=verbose)
        if temp_game_state:
            session['game_state'] = temp_game_state
            if verbose:
                create_log('APP ROUTE /SAVE_GAME: Restored game state from temp save')
        else:
            if verbose:
                create_log("APP ROUTE /SAVE_GAME: No game state in session or invalid. Initializing game state")
            session['game_state'] = get_initial_game_state()
        session.modified = True
    
    filename = request.form.get("filename")
    if not filename or not filename.strip():
        flash("Please provide a valid filename.", "error")
        if verbose:
            create_log("APP ROUTE /SAVE_GAME: Empty filename provided")
        return redirect(url_for("game"))
    
    try:
        confirm_save(filename, session['game_state'], verbose=verbose)
        flash(f"Game saved as {filename}.json!", "success")
        if verbose:
            create_log(f"APP ROUTE /SAVE_GAME: Game saved successfully: {filename}")
        save_temp_game_state(session['game_state'], verbose=verbose)
    except ValueError as ve:
        flash(str(ve), "error")
        if verbose:
            create_log(f"APP ROUTE /SAVE_GAME: ValueError: {str(ve)}")
    except Exception as e:
        flash(f"Failed to save game: {str(e)}", "error")
        if verbose:
            create_log(f"APP ROUTE /SAVE_GAME: Error saving game: {str(e)}")
    
    session.modified = True
    return redirect(url_for("game"))

@app.route("/retrieve_game", methods=["GET", "POST"])
def load():
    """Load a saved game or display available saves."""
    session.permanent = True
    if verbose:
        create_log("APP ROUTE /RETRIEVE_GAME: Entering load game route")
        create_log(f"APP ROUTE /RETRIEVE_GAME: Session ID: {session.get('_id', 'Unknown')}")
        create_log(f"APP ROUTE /RETRIEVE_GAME: Session contents: {dict(session)}")
        create_log(f"APP ROUTE /RETRIEVE_GAME: Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    if request.method == "POST":
        selected_file = request.form.get("selected_file")
        if not selected_file:
            flash("Please select a save file.", "error")
            if verbose:
                create_log("APP ROUTE /RETRIEVE_GAME: No file selected")
            return redirect(url_for("load"))
        
        try:
            session.clear()  # Clear session before loading new game state
            if verbose:
                create_log("APP ROUTE /RETRIEVE_GAME: Session cleared before loading")
            session['game_state'] = retrieve_game(selected_file, verbose=verbose)
            if not validate_game_state(session['game_state']):
                raise ValueError("Loaded game state is invalid")
            flash("Game loaded successfully!", "success")
            if verbose:
                create_log(f"APP ROUTE /RETRIEVE_GAME: Loaded game: {selected_file}")
            
            raw_image_path = session['game_state']['output_image']
            image_filename = get_relative_image_path(raw_image_path)
            if verbose:
                create_log(f"APP ROUTE /RETRIEVE_GAME: Raw image path: {raw_image_path}")
                create_log(f"APP ROUTE /RETRIEVE_GAME: Rendering game.html with image_filename: {image_filename}")
                create_log(f"APP ROUTE /RETRIEVE_GAME: Image URL: {url_for('static', filename=image_filename)}")
            
            response = make_response(render_template("game.html",
                                                    output="Game loaded!",
                                                    output_image=image_filename,
                                                    chat_history=format_chat_history(session['game_state']['history'], session['game_state'])))
            response.headers['Cache-Control'] = 'no-store'
            return response
        except ValueError as ve:
            flash(str(ve), "error")
            if verbose:
                create_log(f"APP ROUTE /RETRIEVE_GAME: ValueError: {str(ve)}")
            return redirect(url_for("load"))
        except Exception as e:
            flash(f"Failed to load game: {str(e)}", "error")
            if verbose:
                create_log(f"APP ROUTE /RETRIEVE_GAME: Error loading game: {str(e)}")
            return redirect(url_for("load"))
    
    save_files = retrieve_game_list(verbose=verbose)
    if not save_files['choices']:
        flash("No saved games found.", "info")
        if verbose:
            create_log("APP ROUTE /RETRIEVE_GAME: No save files found")
    
    response = make_response(render_template("load_game.html", save_files=save_files))
    response.headers['Cache-Control'] = 'no-store'
    return response