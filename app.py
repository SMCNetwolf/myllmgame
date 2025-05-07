from create_log import verbose, create_log
import os
import logging
import json
from flask import Flask, render_template, request, session, redirect, url_for, flash, make_response
from flask_bcrypt import Bcrypt
import sqlite3
from dotenv import load_dotenv
from main_flask import run_action, get_initial_game_state, save_temp_game_state, load_temp_game_state, format_chat_history, validate_game_state, confirm_save, retrieve_game_list, retrieve_game, clean_temp_saves, DEFAULT_IMAGE_FILE_PATH, DEFAULT_AUDIO_FILE_PATH, last_saved_history
import time

# Load environment variables
load_dotenv()
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET")
if not app.secret_key:
    raise ValueError("SESSION_SECRET not found in .env file")

# Initialize Bcrypt for password hashing
bcrypt = Bcrypt(app)

# Database setup
DB_PATH = 'users.db'

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS game_states (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            game_name TEXT NOT NULL,
            game_state TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            UNIQUE(user_id, game_name)
        )''')
        conn.commit()

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

def get_relative_image_path(full_path):
    if not full_path:
        return "default_image.png"
    return full_path.split('static/')[-1] if 'static/' in full_path else full_path

def get_relative_audio_path(full_path):
    if not full_path:
        return "default_audio.mp3"
    return full_path.split('static/')[-1] if 'static/' in full_path else full_path

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        if not username or not password:
            flash("Username and password are required.", "error")
            if verbose:
                create_log("REGISTER: Username and password are required")
            return render_template("register.html")
        
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        try:
            with get_db_connection() as conn:
                c = conn.cursor()
                c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed_password))
                conn.commit()
            flash("Registration successful! Please log in.", "success")
            if verbose:
                create_log(f"REGISTER: User {username} registered successfully")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("Username already exists.", "error")
            if verbose:
                create_log(f"REGISTER: Username {username} already exists")
        except Exception as e:
            flash(f"Registration failed: {str(e)}", "error")
            if verbose:
                create_log(f"REGISTER: Error: {str(e)}")
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
                if verbose:
                    create_log(f"LOGIN: Successful login - user: {username}")
                return redirect(url_for("index"))
            else:
                flash("Invalid username or password.", "error")
                if verbose:
                    create_log(f"LOGIN: Invalid login attempt for user: {username}")
    return render_template("login.html")

@app.route("/logout")
def logout():
    username = session.get('username', 'Unknown')  # Capture username before clearing session
    session.clear()
    flash("Logged out successfully.", "success")
    if verbose:
        create_log(f"LOGOUT: User {username} logged out")
    return redirect(url_for("login"))

@app.route("/")
def index():
    if 'user_id' not in session:
        if verbose:
            create_log("APP ROUTE /: User not logged in, redirecting to login")
        return redirect(url_for("login"))
    
    user_id = session['user_id']
    username = session.get('username', 'Unknown')
    session.permanent = True
    if verbose:
        create_log(f'APP ROUTE /: Session ID: {session.get("_id", "Unknown")}')
        create_log(f'APP ROUTE /: User ID: {user_id}')
        create_log(f'APP ROUTE /: User: {username}')
        create_log(f'APP ROUTE /: Timestamp: {time.strftime("%Y-%m-%d %H:%M:%S")}')

    response = make_response(render_template("index.html"))
    response.headers['Cache-Control'] = 'no-store'
    return response

@app.route("/game", methods=["GET"])
def game():
    if 'user_id' not in session:
        if verbose:
            create_log("APP ROUTE /GAME: User not logged in, redirecting to login")
        return redirect(url_for("login"))
    
    session.permanent = True
    user_id = session['user_id']
    username = session.get('username', 'Unknown')
    if verbose:
        create_log(f"APP ROUTE /GAME: User ID: {user_id}")
        create_log(f"APP ROUTE /GAME: User: {username}")
        create_log(f"APP ROUTE /GAME: Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    # Load latest game state from database (prefer autosave)
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT game_state FROM game_states WHERE user_id = ? AND game_name = 'autosave'", (user_id,))
        row = c.fetchone()
        if row:
            game_state = json.loads(row['game_state'])
            if validate_game_state(game_state, verbose=verbose):
                if verbose:
                    create_log("APP ROUTE /GAME: Loaded autosave game state from database")
            else:
                game_state = get_initial_game_state(verbose=verbose)
                if verbose:
                    create_log("APP ROUTE /GAME: Invalid autosave, initialized new")
        else:
            game_state = get_initial_game_state(verbose=verbose)
            if verbose:
                create_log("APP ROUTE /GAME: No autosave found, initialized new")

    raw_image_path = game_state['output_image']
    image_filename = get_relative_image_path(raw_image_path)
    ambient_sound = get_relative_audio_path(game_state['ambient_sound'])
    if verbose:
        '''
        create_log(f"APP ROUTE /GAME: Raw image path: {raw_image_path}")
        create_log(f"APP ROUTE /GAME: Ambient sound: {ambient_sound}")
        create_log(f"APP ROUTE /GAME: Image URL: {url_for('static', filename=image_filename)}")
        create_log(f"APP ROUTE /GAME: Ambient sound URL: {url_for('static', filename=ambient_sound)}")
        '''

    response = make_response(render_template("game.html",
                                            output="",
                                            output_image=image_filename,
                                            ambient_sound=ambient_sound,
                                            chat_history= format_chat_history([game_state['history'][-1]], game_state) if game_state['history'] else "" )) #format_chat_history(game_state['history'], game_state)  ))
    response.headers['Cache-Control'] = 'no-store'
    return response

@app.route("/command", methods=["POST"])
def process_command():
    if 'user_id' not in session:
        if verbose:
            create_log("APP ROUTE /COMMAND: User not logged in, redirecting to login")
        return redirect(url_for("login"))
    
    session.permanent = True
    user_id = session['user_id']
    username = session.get('username', 'Unknown')
    command = request.form.get("command")
    if verbose:
        create_log(f"APP ROUTE /COMMAND: User ID: {user_id}")
        create_log(f"APP ROUTE /COMMAND: User: {username}")
        create_log(f"APP ROUTE /COMMAND: Command: {command}")
        create_log(f"APP ROUTE /COMMAND: Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    # Load game state (prefer autosave)
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT game_state FROM game_states WHERE user_id = ? AND game_name = 'autosave'", (user_id,))
        row = c.fetchone()
        if row:
            game_state = json.loads(row['game_state'])
            if not validate_game_state(game_state, verbose=verbose):
                game_state = get_initial_game_state(verbose=verbose)
                if verbose:
                    create_log("APP ROUTE /COMMAND: Invalid autosave, initialized new")
        else:
            game_state = get_initial_game_state(verbose=verbose)
            if verbose:
                create_log("APP ROUTE /COMMAND: No autosave, initialized new")

    output = run_action(command, game_state, verbose=verbose)
    if not isinstance(output, str):
        create_log(f"APP ROUTE /COMMAND: Error: run_action returned non-string: {type(output)}")
        output = "Error: Invalid response from run_action"

    # Save updated game state as autosave (overwrite existing)
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO game_states (user_id, game_name, game_state, created_at) VALUES (?, ?, ?, ?)",
                  (user_id, "autosave", json.dumps(game_state), time.strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        if verbose:
            create_log("APP ROUTE /COMMAND: Overwrote autosave game state in database")

    save_temp_game_state(game_state, verbose=verbose)
    ambient_sound = get_relative_audio_path(game_state['ambient_sound'])
    raw_image_path = game_state['output_image']
    image_filename = get_relative_image_path(raw_image_path)
    if verbose:
        '''
        create_log(f"APP ROUTE /COMMAND: Raw image path: {raw_image_path}")
        create_log(f"APP ROUTE /COMMAND: Ambient sound: {ambient_sound}")
        create_log(f"APP ROUTE /COMMAND: Image URL: {url_for('static', filename=image_filename)}")
        create_log(f"APP ROUTE /COMMAND: Ambient sound URL: {url_for('static', filename=ambient_sound)}")
        '''

    response = make_response(render_template("game.html",
                                            output="",
                                            output_image=image_filename,
                                            ambient_sound=ambient_sound,
                                            chat_history= format_chat_history([game_state['history'][-1]], game_state) if game_state['history'] else "" )) #format_chat_history(game_state['history'], game_state)  ))
    response.headers['Cache-Control'] = 'no-store'
    return response

@app.route("/new_game", methods=["POST"])
def new_game():
    if 'user_id' not in session:
        if verbose:
            create_log("APP ROUTE /NEW_GAME: User not logged in, redirecting to login")
        return redirect(url_for("login"))
    
    session.permanent = True
    user_id = session['user_id']
    username = session.get('username', 'Unknown')
    if verbose:
        create_log(f"APP ROUTE /NEW_GAME: User ID: {user_id}")
        create_log(f"APP ROUTE /NEW_GAME: User: {username}")
        create_log(f"APP ROUTE /NEW_GAME: Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    clean_temp_saves(verbose=verbose, force=True)
    game_state = get_initial_game_state(verbose=verbose)

    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO game_states (user_id, game_name, game_state, created_at) VALUES (?, ?, ?, ?)",
                  (user_id, "autosave", json.dumps(game_state), time.strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        if verbose:
            create_log("APP ROUTE /NEW_GAME: Overwrote autosave with new game state in database")

    raw_image_path = game_state['output_image']
    image_filename = get_relative_image_path(raw_image_path)
    ambient_sound = get_relative_audio_path(game_state['ambient_sound'])
    if verbose:
        '''
        create_log(f"APP ROUTE /NEW_GAME: Raw image path: {raw_image_path}")
        create_log(f"APP ROUTE /NEW_GAME: Ambient sound: {ambient_sound}")
        create_log(f"APP ROUTE /NEW_GAME: Image URL: {url_for('static', filename=image_filename)}")
        create_log(f"APP ROUTE /NEW_GAME: Ambient sound URL: {url_for('static', filename=ambient_sound)}")
        '''

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
        if verbose:
            create_log("APP ROUTE /SAVE_GAME: User not logged in, redirecting to login")
        return redirect(url_for("login"))
    
    session.permanent = True
    user_id = session['user_id']
    username = session.get('username', 'Unknown')
    if verbose:
        create_log(f"APP ROUTE /SAVE_GAME: User ID: {user_id}")
        create_log(f"APP ROUTE /SAVE_GAME: User: {username}")
        create_log(f"APP ROUTE /SAVE_GAME: Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    filename = request.form.get("filename")
    if not filename or not filename.strip():
        flash("Please provide a valid filename.", "error")
        if verbose:
            create_log(f"APP ROUTE /SAVE_GAME: Invalid filename provided by user: {username}")
        return redirect(url_for("game"))

    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT game_state FROM game_states WHERE user_id = ? AND game_name = 'autosave'", (user_id,))
        row = c.fetchone()
        if row:
            game_state = json.loads(row['game_state'])
            if not validate_game_state(game_state, verbose=verbose):
                game_state = get_initial_game_state(verbose=verbose)
                if verbose:
                    create_log("APP ROUTE /SAVE_GAME: Invalid autosave, initialized new")
        else:
            game_state = get_initial_game_state(verbose=verbose)
            if verbose:
                create_log("APP ROUTE /SAVE_GAME: No autosave found, initialized new")

        try:
            confirm_save(filename, game_state, user_id=user_id, verbose=verbose)
            flash(f"Game saved as {filename}!", "success")
            if verbose:
                create_log(f"APP ROUTE /SAVE_GAME: Game saved as {filename} for user: {username}")
            save_temp_game_state(game_state, verbose=verbose)
        except ValueError as ve:
            flash(str(ve), "error")  # This will display "Cannot save game: Maximum of MAX_SAVE saved games allowed."
            if verbose:
                create_log(f"APP ROUTE /SAVE_GAME: ValueError for user {username}: {str(ve)}")
        except Exception as e:
            flash(f"Failed to save game: {str(e)}", "error")
            if verbose:
                create_log(f"APP ROUTE /SAVE_GAME: Error saving game for user {username}: {str(e)}")

    return redirect(url_for("game"))


@app.route("/retrieve_game", methods=["GET", "POST"])
def load():
    if verbose:
        create_log("APP ROUTE /RETRIEVE_GAME: Retrieving game")
    if 'user_id' not in session:
        if verbose:
            create_log("APP ROUTE /RETRIEVE_GAME: User not logged in, redirecting to login")
        return redirect(url_for("login"))
    
    session.permanent = True
    user_id = session['user_id']
    username = session.get('username', 'Unknown')
    if verbose:
        create_log(f"APP ROUTE /RETRIEVE_GAME: User ID: {user_id}")
        create_log(f"APP ROUTE /RETRIEVE_GAME: User: {username}")
        create_log(f"APP ROUTE /RETRIEVE_GAME: Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    if request.method == "POST":
        selected_file = request.form.get("selected_file")
        if not selected_file:
            flash("Please select a save file.", "error")
            if verbose:
                create_log(f"APP ROUTE /RETRIEVE_GAME: No save file selected by user: {username}")
            return redirect(url_for("load"))

        try:
            game_state = retrieve_game(selected_file, user_id=user_id, verbose=verbose)
            if not validate_game_state(game_state, verbose=verbose):
                raise ValueError("Loaded game state is invalid")
            flash("Game loaded successfully!", "success")
            if verbose:
                create_log(f"APP ROUTE /RETRIEVE_GAME: Game {selected_file} loaded for user: {username}")

            with get_db_connection() as conn:
                c = conn.cursor()
                c.execute("INSERT OR REPLACE INTO game_states (user_id, game_name, game_state, created_at) VALUES (?, ?, ?, ?)",
                          (user_id, "autosave", json.dumps(game_state), time.strftime('%Y-%m-%d %H:%M:%S')))
                conn.commit()
                if verbose:
                    create_log("APP ROUTE /RETRIEVE_GAME: Overwrote autosave with loaded game state")

            raw_image_path = game_state['output_image']
            image_filename = get_relative_image_path(raw_image_path)
            ambient_sound = get_relative_audio_path(game_state['ambient_sound'])
            if verbose:
                '''
                create_log(f"APP ROUTE /RETRIEVE_GAME: Raw image path: {raw_image_path}")
                create_log(f"APP ROUTE /RETRIEVE_GAME: Ambient sound: {ambient_sound}")
                create_log(f"APP ROUTE /RETRIEVE_GAME: Image URL: {url_for('static', filename=image_filename)}")
                create_log(f"APP ROUTE /RETRIEVE_GAME: Ambient sound URL: {url_for('static', filename=ambient_sound)}")
                '''

            response = make_response(render_template("game.html",
                                                    output="Game loaded!",
                                                    output_image=image_filename,
                                                    ambient_sound=ambient_sound,
                                                    chat_history= format_chat_history([game_state['history'][-1]], game_state) if game_state['history'] else "" )) #format_chat_history(game_state['history'], game_state)  ))
            response.headers['Cache-Control'] = 'no-store'
            return response
        except ValueError as ve:
            flash(str(ve), "error")
            if verbose:
                create_log(f"APP ROUTE /RETRIEVE_GAME: ValueError for user {username}: {str(ve)}")
            return redirect(url_for("load"))
        except Exception as e:
            flash(f"Failed to load game: {str(e)}", "error")
            if verbose:
                create_log(f"APP ROUTE /RETRIEVE_GAME: Error loading game for user {username}: {str(e)}")
            return redirect(url_for("load"))

    save_files = retrieve_game_list(user_id=user_id, verbose=verbose)
    if not save_files['choices']:
        flash("No saved games found.", "info")
        if verbose:
            create_log(f"APP ROUTE /RETRIEVE_GAME: No save files found for user: {username}")

    response = make_response(render_template("load_game.html", save_files=save_files))
    response.headers['Cache-Control'] = 'no-store'
    return response