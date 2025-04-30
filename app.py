from create_log import verbose, create_log
import os
import logging
from flask import Flask, render_template, request, session, redirect, url_for, flash, make_response
from dotenv import load_dotenv
from main_flask import run_action, get_initial_game_state, format_chat_history, confirm_save, retrieve_game_list, retrieve_game

# Load environment variables
load_dotenv()
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET")
if not app.secret_key:
    raise ValueError("SESSION_SECRET not found in .env file")

# Configure permanent sessions
app.config['PERMANENT_SESSION_LIFETIME'] = 3600  # 1 hour

# Configure logging
logging.basicConfig(level=logging.DEBUG)

def get_relative_image_path(full_path):
    """Strip 'static/' from image path to get relative path for url_for."""
    if not full_path:
        return "default_image.png"  # Fallback
    return full_path.split('static/')[-1] if 'static/' in full_path else full_path

@app.route("/")
def index():
    """Render the index page and initialize game state."""
    session.permanent = True
    if verbose:
        create_log('APP ROUTE /: entering index route')

    if 'game_state' not in session:
        if verbose:
            create_log('APP ROUTE /: Game state was not in session. Initializing game state')
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

    if 'game_state' not in session:
        if verbose:
            create_log("APP ROUTE /GAME: Game state not in session. Initializing game state")
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
        create_log(f"APP ROUTE /COMMAND: Session contents: {dict(session)}")

    if 'game_state' not in session:
        if verbose:
            create_log("APP ROUTE /COMMAND: Game state not in session. Initializing game state")
        session['game_state'] = get_initial_game_state()
        session.modified = True

    output = run_action(command, session['game_state'], verbose=verbose)
    if verbose:
        create_log(f"APP ROUTE /COMMAND: run_action output: {output}")
    if not isinstance(output, str):
        create_log(f"APP ROUTE /COMMAND: Error: run_action returned non-string: {type(output)}")
        output = "Error: Invalid response from run_action"
    
    session.modified = True
    
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
    filename = request.form.get("filename")
    try:
        confirm_save(filename, session['game_state'], verbose=verbose)
        flash("Game saved successfully!", "success")
    except Exception as e:
        flash(f"Failed to save game: {str(e)}", "error")
    session.modified = True
    return redirect(url_for("game"))

@app.route("/retrieve_game", methods=["GET", "POST"])
def load():
    """Load a saved game or display available saves."""
    session.permanent = True
    if verbose:
        create_log("APP ROUTE /RETRIEVE_GAME: Entering load game route")
    if request.method == "POST":
        selected_file = request.form.get("selected_file")
        session['game_state'] = retrieve_game(selected_file, verbose=verbose)
        session.modified = True
        if verbose:
            create_log("APP ROUTE /RETRIEVE_GAME: game loaded")
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
    if verbose:
        create_log("APP ROUTE /RETRIEVE_GAME: loading game")
    save_files = retrieve_game_list(verbose=verbose)
    response = make_response(render_template("load_game.html", save_files=save_files))
    response.headers['Cache-Control'] = 'no-store'
    return response