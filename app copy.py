from create_log import verbose, create_log
 

import os
import logging
import sqlite3
from flask import Flask, render_template, request, session, redirect, url_for

from dotenv import load_dotenv
from datetime import datetime

# Load main_flask code
from main_flask import main_loop, get_initial_game_state, save_game, confirm_save, retrieve_game, confirm_retrieve, world
import prompts

# Load environment variables
load_dotenv()
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET")

# Configure logging
logging.basicConfig(level=logging.DEBUG)

# Database setup (Moved database code here)
DATABASE = "rpggame.db"

def query_db(query, args=(), one=False):
    db = get_db()
    cur = db.execute(query, args)
    db.commit()
    rv = cur.fetchall()
    cur.close()
    close_db(db)
    return (rv[0] if rv else None) if one else rv

def insert_db(query, args=()):
    db = get_db()
    cur = db.execute(query, args)
    db.commit()
    id = cur.lastrowid
    cur.close()
    close_db(db)
    return id

def update_db(query, args=()):
    db = get_db()
    cur = db.execute(query, args)
    db.commit()
    cur.close()
    close_db(db)

def get_db():
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    return db

def close_db(db):
    if db is not None:
        db.close()

def init_db():
    db = get_db()
    with app.open_resource("schema.sql", mode="r") as f:
        db.cursor().executescript(f.read())
    db.commit()
    close_db(db)

@app.cli.command("init-db")
def init_db_command():
    """Clear the existing data and create new tables."""
    init_db()
    if verbose:
      create_log("Initialized the database.")


def format_chat_history(history):
    #Formats a text into a dictionary with the role and content
    formatted_history = ""
    for entry in history:
        role = entry["role"]
        content = entry["content"]
        formatted_history += f"{role.capitalize()}: {content}\n"
    return formatted_history

# the default directory for html files in Flask is /templates
@app.route("/")
def index():
   
    session['history'] = []
    if verbose:
        create_log('entering index route')
        create_log(f"session['history'] is now: {session['history']}")
    return render_template("index.html")

@app.route("/game", methods=["GET"])
def game():
    # Initialize history
    # Everytime the user goes to the index page, clear session data
    session['history'] = [{"role": "system", "content": prompts.system_prompt}] 
    if verbose:
        create_log('entering game route')
        create_log(f"session['history'] is now: {session['history']}")

    if 'game_state' not in session:
        if verbose:
            create_log('game state not in session')
        session['game_state'] = get_initial_game_state()
        
    #append world description to history
    if verbose: 
        create_log(f'game_state in game route: \n{session["game_state"]}')
        create_log(f"session['history'] before modification: \n{session['history']}")
    
    session['history'].append({"role": "assistant", "content": world['description']})

    if verbose: 
        create_log('session[\'history\'] modified:')
        create_log(session['history'])

    return render_template("game.html",
                           output=world['description'],
                           output_image=session['game_state']["output_image"])

@app.route("/command", methods=["POST"])
def process_command():
    
    command = request.form.get("command")
    if verbose:
        create_log(f"entering command route:\ncommand is: {command}")
    
    if 'history' not in session or 'game_state' not in session:
        session['history'] = []
        session['game_state'] = get_initial_game_state()

    if verbose:
        create_log(f"process_command: history is: {session['history']} and type: {type(session['history'])} and game_state is: {session['game_state']}")
    
    output, generated_image_path = main_loop(command, session['history'], session['game_state'])   

    session['history'].append({"role": "user", "content": command})
    session['history'].append({"role": "assistant", "content": output})
   
    return render_template("game.html",
                           output=output,
                           output_image=generated_image_path,
                           chat_history = format_chat_history(session['history'])
                           )

# Save Game Route
@app.route("/save_game", methods=["POST"])
def save():
    
    filename = request.form.get("filename")
    confirm_save(filename, session['history'], session['game_state'])
    return redirect(url_for("game"))


# Retrieve Game Route 
@app.route("/retrieve_game", methods=["GET", "POST"])
def load():
    global chatbot_history, game_state
    if verbose:
      create_log("Entering load game route")
    if request.method == "POST":
        selected_file = request.form.get("selected_file")
        session['history'], output_image, session['game_state'] = confirm_retrieve(selected_file)
        
        if verbose: create_log("game loaded")
        return render_template("game.html",
                               output="Game loaded!",
                               output_image=output_image,
                               chat_history = format_chat_history(session['history']))
    if verbose: create_log("loading game")
    save_files = retrieve_game()
    return render_template("load_game.html", save_files=save_files)
