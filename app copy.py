import os
import logging
import json
from flask import Flask, render_template, request, session, redirect, url_for, flash, make_response, jsonify
from flask_bcrypt import Bcrypt
import sqlite3
from dotenv import load_dotenv
import time
import datetime

from config import (
    VERBOSE, SESSION_SECRET, TOGETHER_API_KEY, DEFAULT_IMAGE_FILE_PATH, 
    DEFAULT_AUDIO_FILE_PATH, DB_PATH, MAX_SAVE
)
from main_flask import (
    run_action, get_initial_game_state, save_temp_game_state,
    format_chat_history, validate_game_state, last_saved_history
)
from create_log import create_log, clean_old_logs

from handle_db import (
    init_db, get_db_connection, upload_db_to_gcs, download_db_from_gcs,
    confirm_save, retrieve_game_list, retrieve_game, clean_temp_saves
)

app = Flask(__name__)

#TODO: demora na geração de imagem, salvar imagem com prompt junto talvez via tupla? DETECT_INVENTORY_CHANGES: Invalid JSON response

# Download database from GCS at startup
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

try:
    download_db_from_gcs()
except Exception as e:
    create_log(f"\n\nAPP: Failed to download database from GCS, proceeding with local database: {str(e)}\n\n")

# Load environment variables
app.secret_key = SESSION_SECRET

# Initialize Bcrypt for password hashing
bcrypt = Bcrypt(app)

# Clean old logs and initialize database at startup
clean_old_logs()
init_db()

# Configure session settings
app.config['SESSION_TYPE'] = 'filesystem'  # Can switch to 'redis' for production
app.config['SESSION_PERMANENT'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = 3600
app.config['SESSION_COOKIE_SECURE'] = False
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_NAME'] = 'rpg_session'

# Configure logging
logging.basicConfig(level=logging.DEBUG)

#TODO: check if these two functions are really needed
def get_relative_image_path(full_path):
    if not full_path:
        return "default_image.png"
    return full_path.split('static/')[-1] if 'static/' in full_path else full_path

def get_relative_audio_path(full_path):
    if not full_path:
        return "default_audio.mp3"
    return full_path.split('static/')[-1] if 'static/' in full_path else full_path

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        if not username or not password:
            flash("Username and password are required.", "error")
            if VERBOSE:
                create_log("ROUTE /REGISTER: Username and password are required")
            return render_template("register.html")
        
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        try:
            with get_db_connection() as conn:
                c = conn.cursor()
                c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed_password))
                conn.commit()
            flash("Registration successful! Please log in.", "success")
            if VERBOSE:
                create_log(f"\nROUTE /REGISTER: User {username} registered successfully\n")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("Username already exists.", "error")
            if VERBOSE:
                create_log(f"\nROUTE /REGISTER: Username {username} already exists\n")
        except Exception as e:
            flash(f"Registration failed: {str(e)}", "error")
            if VERBOSE:
                create_log(f"\n\nROUTE /REGISTER: Error: {str(e)}\n\n")
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM users WHERE username = ?", (username,))
            user = c.fetchone()
            if user and bcrypt.check_password_hash(user['password'], password):
                session['user_id'] = user['id']
                session['username'] = user['username']  # Store username in session
                session.permanent = True
                flash("Login successful!", "success")
                if VERBOSE:
                    create_log(f"\nROUTE /LOGIN: Successful login - user: {username}\n")
                return redirect(url_for("index"))
            else:
                flash("Invalid username or password.", "error")
                if VERBOSE:
                    create_log(f"\n\n\nROUTE /LOGIN: Invalid login attempt for user: {username}\n\n\n")
    return render_template("login.html")

@app.route("/logout")
def logout():
    username = session.get('username', 'Unknown')  # Capture username before clearing session
    session.clear()
    flash("Logged out successfully.", "success")
    if VERBOSE:
        create_log(f"\nROUTE /LOGOUT: User {username} logged out\n")
    return redirect(url_for("login"))

@app.route("/")
def index():
    if 'user_id' not in session:
        if VERBOSE:
            create_log(f"\nROUTE /: User not logged in, redirecting to login\n")
        return redirect(url_for("login"))
    
    user_id = session['user_id']
    username = session.get('username', 'Unknown')
    session.permanent = True
    if VERBOSE:
        create_log(f'ROUTE /: Session ID: {session.get("_id", "Unknown")} User:{user_id} - {username}')

    clean_old_logs()  # Check for cleanup on each index route to handle long-running apps
    response = make_response(render_template("index.html"))
    response.headers['Cache-Control'] = 'no-store'
    return response

@app.route("/game", methods=["GET"])
def game():
    if 'user_id' not in session:
        if VERBOSE:
            create_log(f"\nROUTE /GAME: User not logged in, redirecting to login\n")
        return redirect(url_for("login"))
    
    session.permanent = True
    user_id = session['user_id']
    username = session.get('username', 'Unknown')
    if VERBOSE:
        create_log(f"ROUTE /GAME: User: {user_id} - {username}")

    # Load latest game state from database (prefer autosave)
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT game_state FROM game_states WHERE user_id = ? AND game_name = 'autosave'", (user_id,))
        row = c.fetchone()
        if row:
            game_state = json.loads(row['game_state'])
            if validate_game_state(game_state):
                if VERBOSE:
                    create_log("ROUTE /GAME: Loaded autosave game state from database")
            else:
                game_state = get_initial_game_state()
                if VERBOSE:
                    create_log("\nROUTE /GAME: Invalid autosave, initialized new\n")
        else:
            game_state = get_initial_game_state()
            if VERBOSE:
                create_log("ROUTE /GAME: No autosave found, initialized new")

    raw_image_path = game_state['output_image']
    image_filename = get_relative_image_path(raw_image_path)
    ambient_sound = get_relative_audio_path(game_state['ambient_sound'])

    response = make_response(render_template("game.html",
                                            output="",
                                            output_image=image_filename,
                                            ambient_sound=ambient_sound,
                                            chat_history= format_chat_history([game_state['history'][-1]], game_state) if game_state['history'] else "" )) #format_chat_history(game_state['history'], game_state)  ))
    response.headers['Cache-Control'] = 'no-store'
    return response

#TODO: it seems that when entering /command from /game, initial game state is created again because it was not stored in the database
@app.route("/command", methods=["POST"])
def process_command():
    if 'user_id' not in session:
        if VERBOSE:
            create_log("ROUTE /COMMAND: User not logged in, redirecting to login")
        return redirect(url_for("login"))
    
    session.permanent = True
    user_id = session['user_id']
    username = session.get('username', 'Unknown')
    command = request.form.get("command")

    # Load game state (prefer autosave)
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT game_state FROM game_states WHERE user_id = ? AND game_name = 'autosave'", (user_id,))
        row = c.fetchone()
        if row:
            game_state = json.loads(row['game_state'])
            if not validate_game_state(game_state):
                game_state = get_initial_game_state()
                if VERBOSE:
                    create_log("ROUTE /COMMAND: Invalid autosave, initialized new")
        else:
            game_state = get_initial_game_state()
            if VERBOSE:
                create_log("ROUTE /COMMAND: No autosave, initialized new")

    output = run_action(command, game_state)
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    gcs_path = f"{DEFAULT_IMAGE_FILE_PATH.split('.png')[0]}_{timestamp}.png"
    if not isinstance(output, str):
        create_log(f"\n\nROUTE /COMMAND: Error: run_action returned non-string: {type(output)}\n\n", force_log=True)
        output = "Error: Invalid response from run_action"

    # Save updated game state as autosave (overwrite existing)
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO game_states (user_id, game_name, game_state, created_at) VALUES (?, ?, ?, ?)",
                  (user_id, "autosave", json.dumps(game_state), time.strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        if VERBOSE:
            create_log(f"ROUTE /COMMAND: Overwrote autosave game state in database")
    
    upload_db_to_gcs()
    save_temp_game_state(game_state)
    ambient_sound = get_relative_audio_path(game_state['ambient_sound'])
    raw_image_path = game_state['output_image']
    image_filename = get_relative_image_path(raw_image_path)

    chat_history= format_chat_history([game_state['history'][-1]], game_state) if game_state['history'] else ""  #format_chat_history(game_state['history'], game_state)  ))

    # Handle AJAX request
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        response_data = {
            'output': output,
            'output_image': url_for('static', filename=image_filename),
            'ambient_sound': url_for('static', filename=ambient_sound),
            'chat_history': chat_history
        }
        create_log(f"\nROUTE /COMMAND-AJAX: User {username} \nQuestion: {command}", force_log=True)
        create_log(f"ROUTE /COMMAND-AJAX: Generated image: {gcs_path}", force_log=True)
        create_log(f"ROUTE /COMMAND-AJAX: Completion: {chat_history}\n", force_log=True)
        return jsonify(response_data)

    # Fallback for non-AJAX requests
        
    response = make_response(render_template("game.html",
                                            output="",
                                            output_image=image_filename,
                                            ambient_sound=ambient_sound,
                                            chat_history= chat_history ))
    response.headers['Cache-Control'] = 'no-store'
    create_log(f"\nROUTE /COMMAND: User {username} \nQuestion: {command}", force_log=True)
    create_log(f"ROUTE /COMMAND: Generated image: {gcs_path}", force_log=True)
    create_log(f"ROUTE /COMMAND: Completion: {chat_history}\n", force_log=True)
    return response

@app.route("/new_game", methods=["POST"])
def new_game():
    if 'user_id' not in session:
        if VERBOSE:
            create_log("ROUTE /NEW_GAME: User not logged in, redirecting to login")
        return redirect(url_for("login"))
    
    session.permanent = True
    user_id = session['user_id']
    username = session.get('username', 'Unknown')
    if VERBOSE:
        create_log(f"ROUTE /NEW_GAME: User: {user_id} - {username}")

    clean_temp_saves(force=True)
    game_state = get_initial_game_state()

    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO game_states (user_id, game_name, game_state, created_at) VALUES (?, ?, ?, ?)",
                  (user_id, "autosave", json.dumps(game_state), time.strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        if VERBOSE:
            create_log("ROUTE /NEW_GAME: Overwrote autosave with new game state in database")

    raw_image_path = game_state['output_image']
    image_filename = get_relative_image_path(raw_image_path)
    ambient_sound = get_relative_audio_path(game_state['ambient_sound'])

    response = make_response(render_template("game.html",
                                            output="New game started!",
                                            output_image=image_filename,
                                            ambient_sound=ambient_sound,
                                            chat_history= format_chat_history([game_state['history'][-1]], game_state) if game_state['history'] else "" )) #format_chat_history(game_state['history'], game_state)  ))
    response.headers['Cache-Control'] = 'no-store'
    return response

@app.route("/save_game", methods=["POST"])
def save():
    if 'user_id' not in session:
        if VERBOSE:
            create_log("ROUTE /SAVE_GAME: User not logged in, redirecting to login")
        return redirect(url_for("login"))
    
    session.permanent = True
    user_id = session['user_id']
    username = session.get('username', 'Unknown')
    if VERBOSE:
        create_log(f"ROUTE /SAVE_GAME: User: {username} - {user_id}")

    filename = request.form.get("filename")
    if not filename or not filename.strip():
        flash("Please provide a valid filename.", "error")
        if VERBOSE:
            create_log(f"ROUTE /SAVE_GAME: Invalid filename provided by user: {username}")
        return redirect(url_for("game"))

    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT game_state FROM game_states WHERE user_id = ? AND game_name = 'autosave'", (user_id,))
        row = c.fetchone()
        if row:
            game_state = json.loads(row['game_state'])
            if not validate_game_state(game_state):
                game_state = get_initial_game_state()
                if VERBOSE:
                    create_log("ROUTE /SAVE_GAME: Invalid autosave, initialized new")
        else:
            game_state = get_initial_game_state()
            if VERBOSE:
                create_log("ROUTE /SAVE_GAME: No autosave found, initialized new")

        try:
            result = confirm_save(filename, game_state, user_id=user_id)
            if result["status"] == "max_saves_reached":
                # Store pending save data in session and redirect to overwrite selection
                session['pending_save_filename'] = filename
                session['pending_game_state'] = json.dumps(game_state)
                flash(result["message"], "info")
                if VERBOSE:
                    create_log(f"ROUTE /SAVE_GAME: Max saves reached, redirecting to overwrite for user: {username}")
                return redirect(url_for("overwrite_game"))
            flash(result["message"], "success")
            if VERBOSE:
                create_log(f"ROUTE /SAVE_GAME: Game saved as {filename} for user: {username}")
            save_temp_game_state(game_state)
            upload_db_to_gcs()
        except Exception as e:
            flash(f"Failed to save game: {str(e)}", "error")
            create_log(f"\n\nROUTE /SAVE_GAME: Error saving game for user {username}: {str(e)}\n\n", force_log=True)

    return redirect(url_for("game"))

@app.route("/retrieve_game", methods=["GET", "POST"])
def load():
    if 'user_id' not in session:
        if VERBOSE:
            create_log("ROUTE /RETRIEVE_GAME: User not logged in, redirecting to login")
        return redirect(url_for("login"))
    
    session.permanent = True
    user_id = session['user_id']
    username = session.get('username', 'Unknown')
    if VERBOSE:
        create_log(f"ROUTE /RETRIEVE_GAME: User: {user_id} - {username}")

    if request.method == "POST":
        selected_file = request.form.get("selected_file")
        if not selected_file:
            flash("Please select a save file.", "error")
            if VERBOSE:
                create_log(f"ROUTE /RETRIEVE_GAME: No save file selected by user: {username}")
            return redirect(url_for("load"))

        try:
            game_state = retrieve_game(selected_file, user_id=user_id)
            if not validate_game_state(game_state):
                create_log(f"\n\nROUTE /RETRIEVE_GAME: Loaded game state is invalid for user: {username}\n\n")
                raise ValueError("Loaded game state is invalid")
            flash("Game loaded successfully!", "success")
            if VERBOSE:
                create_log(f"ROUTE /RETRIEVE_GAME: Game {selected_file} loaded for user: {username}")

            with get_db_connection() as conn:
                c = conn.cursor()
                c.execute("INSERT OR REPLACE INTO game_states (user_id, game_name, game_state, created_at) VALUES (?, ?, ?, ?)",
                          (user_id, "autosave", json.dumps(game_state), time.strftime('%Y-%m-%d %H:%M:%S')))
                conn.commit()
                if VERBOSE:
                    create_log("\nROUTE /RETRIEVE_GAME: Overwrote autosave with loaded game state\n")

            raw_image_path = game_state['output_image']
            image_filename = get_relative_image_path(raw_image_path)
            ambient_sound = get_relative_audio_path(game_state['ambient_sound'])

            response = make_response(render_template("game.html",
                                                    output="Game loaded!",
                                                    output_image=image_filename,
                                                    ambient_sound=ambient_sound,
                                                    chat_history= format_chat_history([game_state['history'][-1]], game_state) if game_state['history'] else "" )) #format_chat_history(game_state['history'], game_state)  ))
            response.headers['Cache-Control'] = 'no-store'
            return response
        except ValueError as ve:
            flash(str(ve), "error")
            create_log(f"\n\nROUTE /RETRIEVE_GAME: ValueError for user {username}: {str(ve)}\n")
            return redirect(url_for("load"))
        except Exception as e:
            flash(f"Failed to load game: {str(e)}", "error")
            create_log(f"\n\nROUTE /RETRIEVE_GAME: Error loading game for user {username}: {str(e)}\n\n")
            return redirect(url_for("load"))

    save_files = retrieve_game_list(user_id=user_id)
    if not save_files['choices']:
        flash("No saved games found.", "info")
        if VERBOSE:
            create_log(f"ROUTE /RETRIEVE_GAME: No save files found for user: {username}")

    response = make_response(render_template("load_game.html", save_files=save_files))
    response.headers['Cache-Control'] = 'no-store'
    return response

@app.route("/overwrite_game", methods=["GET", "POST"])
def overwrite_game():
    if 'user_id' not in session:
        if VERBOSE:
            create_log("\nROUTE /OVERWRITE_GAME: User not logged in, redirecting to login\n")
        return redirect(url_for("login"))
    
    session.permanent = True
    user_id = session['user_id']
    username = session.get('username', 'Unknown')
    if VERBOSE:
        create_log(f"ROUTE /OVERWRITE_GAME: User: {user_id} - {username}")

    if request.method == "POST":
        selected_file = request.form.get("selected_file")
        new_filename = request.form.get("new_filename")
        
        if not new_filename and not selected_file:
            flash("Please provide a new filename or select a file to overwrite.", "error")
            if VERBOSE:
                create_log(f"ROUTE /OVERWRITE_GAME: No filename or file selected by user: {username}")
            return redirect(url_for("overwrite_game"))

        # Use new_filename if provided, else fallback to selected_file
        new_name = new_filename.strip() if new_filename and new_filename.strip() else selected_file
        if not new_name:
            flash("Invalid filename.", "error")
            return redirect(url_for("overwrite_game"))
        
        try:
            game_state = json.loads(session.get('pending_game_state'))
            if not validate_game_state(game_state):
                flash("Invalid game state.", "error")
                create_log(f"\nROUTE /OVERWRITE_GAME: Invalid pending game state for user: {username}\n")
                return redirect(url_for("game"))
            
            with get_db_connection() as conn:
                c = conn.cursor()
                c.execute("SELECT COUNT(*) FROM game_states WHERE user_id = ? AND game_name != 'autosave'", (user_id,))
                save_count = c.fetchone()[0]
                c.execute("SELECT COUNT(*) FROM game_states WHERE user_id = ? AND game_name = ?", (user_id, new_name))
                exists = c.fetchone()[0]
                
                # If renaming to a new name and max saves reached, check if overwriting an existing file
                if save_count >= MAX_SAVE and not exists and new_name != 'autosave':
                    if selected_file:
                        # Allow rename only if selected_file exists (i.e., replacing one save with another)
                        c.execute("SELECT COUNT(*) FROM game_states WHERE user_id = ? AND game_name = ?", (user_id, selected_file))
                        selected_exists = c.fetchone()[0]
                        if not selected_exists:
                            flash(f"Cannot rename: Selected file {selected_file} does not exist.", "error")
                            create_log(f"\nROUTE /OVERWRITE_GAME: Selected file {selected_file} does not exist for user: {username}\n")
                            return redirect(url_for("overwrite_game"))
                        # Delete the selected file to free up a slot
                        c.execute("DELETE FROM game_states WHERE user_id = ? AND game_name = ?", (user_id, selected_file))
                        conn.commit()
                    else:
                        flash(f"Cannot save: Maximum of {MAX_SAVE} saved games allowed. Please select an existing file to overwrite or rename.", "error")
                        create_log(f"ROUTE /OVERWRITE_GAME: Max saves reached, cannot save {new_name} for user: {username}")
                        return redirect(url_for("overwrite_game"))
                
                c.execute("INSERT OR REPLACE INTO game_states (user_id, game_name, game_state, created_at) VALUES (?, ?, ?, ?)",
                          (user_id, new_name, json.dumps(game_state), time.strftime('%Y-%m-%d %H:%M:%S')))
                conn.commit()
            
            flash(f"Game saved as {new_name}!", "success")
            if VERBOSE:
                create_log(f"ROUTE /OVERWRITE_GAME: Game saved as {new_name} for user: {username}")
            
            # Clear pending session data
            session.pop('pending_save_filename', None)
            session.pop('pending_game_state', None)
            save_temp_game_state(game_state)
            upload_db_to_gcs()
            return redirect(url_for("game"))
        except Exception as e:
            flash(f"Failed to save game: {str(e)}", "error")
            create_log(f"\n\nROUTE /OVERWRITE_GAME: Error saving game for user {username}: {str(e)}\n\n", force_log=True)
            return redirect(url_for("overwrite_game"))
    
    save_files = retrieve_game_list(user_id=user_id)
    if not save_files['choices']:
        flash("No saved games found to overwrite.", "info")
        if VERBOSE:
            create_log(f"\nROUTE /OVERWRITE_GAME: No save files found for user: {username}\n")
        return redirect(url_for("game"))

    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM game_states WHERE user_id = ? AND game_name != 'autosave'", (user_id,))
        save_count = c.fetchone()[0]

    response = make_response(render_template(
        "overwrite_game.html",
        save_files=save_files,
        pending_filename=session.get('pending_save_filename', ''),
        save_count=save_count,
        max_save=MAX_SAVE
    ))
    response.headers['Cache-Control'] = 'no-store'
    return response   