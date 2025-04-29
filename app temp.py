from create_log import verbose, create_log
import os
import logging
import sqlite3
from flask import Flask, render_template, request, session, redirect, url_for, flash, make_response, jsonify
from dotenv import load_dotenv
from datetime import datetime
from main_flask import run_action, get_initial_game_state, save_game, confirm_save, retrieve_game, confirm_retrieve, world
import prompts

# Load environment variables
load_dotenv()
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET")
if not app.secret_key:
    raise ValueError("SESSION_SECRET not found in .env file")

# Configure logging
logging.basicConfig(level=logging.DEBUG)

# Database setup
DATABASE = "rpggame.db"

def query_db(query, args=(), one=False):
    """Execute a database query and return results."""
    db = get_db()
    cur = db.execute(query, args)
    db.commit()
    rv = cur.fetchall()
    cur.close()
    close_db(db)
    return (rv[0] if rv else None) if one else rv

def insert_db(query, args=()):
    """Insert data into the database and return the last row ID."""
    db = get_db()
    cur = db.execute(query, args)
    db.commit()
    id = cur.lastrowid
    cur.close()
    close_db(db)
    return id

def update_db(query, args=()):
    """Update data in the database."""
    db = get_db()
    cur = db.execute(query, args)
    db.commit()
    cur.close()
    close_db(db)

def get_db():
    """Open a database connection."""
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    return db

def close_db(db):
    """Close a database connection."""
    if db is not None:
        db.close()

def init_db():
    """Initialize the database with schema.sql."""
    db = get_db()
    with app.open_resource("schema.sql", mode="r") as f:
        db.cursor().executescript(f.read())
    db.commit()
    close_db(db)

@app.cli.command("init-db")
def init_db_command():
    """Clear existing data and create new tables."""
    init_db()
    if verbose:
        create_log("Initialized the database.")

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

@app.route("/")
def index():
    """Render the index page and clear session history."""
    session['history'] = []
    session.pop('output', None)  # Clear any old output
    if verbose:
        create_log('entering index route')
        create_log(f"session['history'] is now: {session['history']}")
    response = make_response(render_template("index.html"))
    response.headers['Cache-Control'] = 'no-store'
    return response

@app.route("/game", methods=["GET"])
def game():
    """Initialize game state and render the game page."""
    session['history'] = [{"role": "system", "content": prompts.system_prompt}]
    session.pop('output', None)  # Clear any old output
    if verbose:
        create_log('entering game route')
        create_log(f"session['history'] is now: {session['history']}")
    if 'game_state' not in session:
        if verbose:
            create_log('game state not in session')
        session['game_state'] = get_initial_game_state()
    session['history'].append({"role": "assistant", "content": world['description']})
    if verbose:
        create_log(f'game_state in game route: \n{session["game_state"]}')
        create_log(f"session['history'] after modification: \n{session['history']}")
    response = make_response(render_template("game.html",
                                            output="Bem-vindo a Luminaria! Digite um comando para começar.",
                                            output_image=session['game_state']["output_image"],
                                            chat_history=format_chat_history(session['history'])))
    response.headers['Cache-Control'] = 'no-store'
    return response

@app.route("/command", methods=["POST"])
def process_command():
    """Process a user command and update game state."""
    command = request.form.get("command")
    if verbose:
        create_log(f"entering command route:\ncommand is: {command}")
    # Initialize session if missing
    if 'game_state' not in session:
        session['game_state'] = get_initial_game_state()
    if 'history' not in session or not session['history']:
        session['history'] = [
            {"role": "system", "content": prompts.system_prompt},
            {"role": "assistant", "content": world['description']}
        ]
    if verbose:
        create_log(f"process_command: history before run_action: {session['history']} and type: {type(session['history'])}")
    session.pop('output', None)  # Clear any old output
    output = run_action(command, session['game_state'], verbose=verbose)
    if verbose:
        create_log(f"run_action output: {output}")
    # Ensure output is a string
    if not isinstance(output, str):
        create_log(f"Error: run_action returned non-string: {type(output)}")
        output = "Error: Invalid response from run_action"
    session['history'] = session['game_state']['history']  # Sync history
    generated_image_path = session['game_state']['output_image']
    rendered_chat_history = format_chat_history(session['history'])
    if verbose:
        create_log(f"process_command: history after run_action: {session['history']}")
        create_log(f"process_command: rendered chat_history: {rendered_chat_history}")
        create_log(f"Rendering game.html with output: {output}")
    
    # Check if request is AJAX (from game.js)
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.accept_mimetypes.accept_json:
        return jsonify({
            'description': output,
            'image_url': url_for('static', filename=generated_image_path),
            'chat_history': rendered_chat_history,
            'current_location': session['game_state'].get('town', 'Luminaria')  # Fallback to town name
        })
    
    # Render HTML for direct form submissions
    response = make_response(render_template("game.html",
                                            output=output,
                                            output_image=generated_image_path,
                                            chat_history=rendered_chat_history))
    response.headers['Cache-Control'] = 'no-store'
    return response

@app.route("/save_game", methods=["POST"])
def save():
    """Save the game state with a user-specified filename."""
    filename = request.form.get("filename")
    try:
        confirm_save(filename, session['history'], session['game_state'])
        flash("Game saved successfully!", "success")
    except Exception as e:
        flash(f"Failed to save game: {str(e)}", "error")
    return redirect(url_for("game"))

@app.route("/retrieve_game", methods=["GET", "POST"])
def load():
    """Load a saved game or display available saves."""
    if verbose:
        create_log("Entering load game route")
    if request.method == "POST":
        selected_file = request.form.get("selected_file")
        session['history'], output_image, session['game_state'] = confirm_retrieve(selected_file)
        if verbose:
            create_log("game loaded")
        response = make_response(render_template("game.html",
                                                output="Game loaded!",
                                                output_image=output_image,
                                                chat_history=format_chat_history(session['history'])))
        response.headers['Cache-Control'] = 'no-store'
        return response
    if verbose:
        create_log("loading game")
    save_files = retrieve_game()
    response = make_response(render_template("load_game.html", save_files=save_files))
    response.headers['Cache-Control'] = 'no-store'
    return response