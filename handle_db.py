import os
import json
import time
from google.cloud import storage
import bcrypt
from config import bucket
import sqlite3

from config import DB_PATH, GCS_BUCKET_NAME, VERBOSE, MAX_SAVE, TEMP_SAVES_PATH
from main_flask import validate_game_state
from create_log import create_log

def init_db():
    try:
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
            create_log("HANDLE_DB: INIT_DB: Database initialized successfully")
    except Exception as e:
        create_log(f"\n\nHANDLE_DB: INIT_DB: Error initializing database: {e}\n\n")
        raise  # Re-raise the exception to stop the app if initialization fails

def upload_db_to_gcs(int_verbose=False):
    """Upload database/users.db to GCS."""
    if bucket: # Check if bucket is initialized
        try:
            blob = bucket.blob(DB_PATH)
            blob.upload_from_filename(DB_PATH)
            if int_verbose:
                create_log(f"HANDLE_DB: UPLOAD_DB_TO_GCS: Uploaded {DB_PATH} to gs://{GCS_BUCKET_NAME}/{DB_PATH}")
        except Exception as e:
            create_log(f"\n\nHANDLE_DB: UPLOAD_DB_TO_GCS: Error uploading database to GCS: {str(e)}\n\n", force_log=True)
            #TODO: Decide whether to raise or handle the error

def download_db_from_gcs():
    """Download users.db from GCS to database/users.db."""
    if bucket:
        try:
            blob = bucket.blob(DB_PATH)
            if blob.exists():
                os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
                blob.download_to_filename(DB_PATH)
                print(f"HANDLE_DB: DOWNLOAD_DB_FROM_GCS: Downloaded gs://{GCS_BUCKET_NAME}/{DB_PATH} to {DB_PATH}")
                if VERBOSE:
                    create_log(f"HANDLE_DB: DOWNLOAD_DB_FROM_GCS: Downloaded gs://{GCS_BUCKET_NAME}/{DB_PATH} to {DB_PATH}")
            else:
                if VERBOSE:
                    create_log(f"\n\nHANDLE_DB: DOWNLOAD_DB_FROM_GCS: No users.db found in GCS bucket {GCS_BUCKET_NAME}\n\n")
        except Exception as e:
            create_log(f"\n\nHANDLE_DB: DOWNLOAD_DB_FROM_GCS: Error downloading database from GCS: {str(e)}\n\n", force_log=True)
            #TODO: Decide whether to raise or handle the error

def get_db_connection(int_verbose=False):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    if int_verbose:
        create_log(f"HANDLE_DB: GET_DB_CONNECTION: Connected to database {DB_PATH}")
    return conn

def confirm_save(filename, game_state, user_id):
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM game_states WHERE user_id = ? AND game_name != 'autosave'", (user_id,))
        save_count = c.fetchone()[0]
        
       
        if save_count >= MAX_SAVE and filename != 'autosave':
            # Instead of raising an error, return a signal to prompt overwrite
            return {"status": "max_saves_reached", "message": f"Maximum of {MAX_SAVE} saved games allowed."}
        
        c.execute("INSERT OR REPLACE INTO game_states (user_id, game_name, game_state, created_at) VALUES (?, ?, ?, ?)",
                  (user_id, filename, json.dumps(game_state), time.strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
    return {"status": "success", "message": f"Game saved as {filename}"}

def retrieve_game_list(user_id):
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT game_name FROM game_states WHERE user_id = ? AND game_name != 'autosave'", (user_id,))
            rows = c.fetchall()
            choices = [row['game_name'] for row in rows]
            #create_log(f"RETRIEVE_GAME_LIST: Found {len(rows)} rows for user_id={user_id}: {choices}")
            return {'choices': choices, 'visible': len(choices) > 0}
    except Exception as e:
        create_log(f"\n\nHANDLE_DB: RETRIEVE_GAME_LIST: Error for user_id={user_id}: {str(e)}\n\n", force_log=True)
        return {'choices': [], 'visible': False}
        
def retrieve_game(selected_file, user_id, int_verbose=False):
    if not selected_file or not selected_file.strip():
        create_log("\n\nHANDLE_DB: RETRIEVE_GAME: Error: No file selected\n\n", force_log=True)
        raise ValueError("No file selected")
    
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT game_state FROM game_states WHERE user_id = ? AND game_name = ?", (user_id, selected_file))
            row = c.fetchone()
            if not row:
                create_log(f"\n\nHANDLE_DB: RETRIEVE_GAME: Error: Game {selected_file} not found for user {user_id}\n\n", force_log=True)
                raise ValueError("Selected save file does not exist")
            
            game_state = json.loads(row['game_state'])
            if not validate_game_state(game_state):
                create_log("\n\nHANDLE_DB: RETRIEVE_GAME: Error: Invalid game state\n\n", force_log=True)
                raise ValueError("Invalid save file: No game state found")
            
            if int_verbose:
                create_log(f"HANDLE_DB: RETRIEVE_GAME: Loaded game {selected_file} for user {user_id}")
            return game_state
    except Exception as e:
        create_log(f"\n\nHANDLE_DB: RETRIEVE_GAME: Error loading game: {str(e)}\n\n", force_log=True)
        raise

def clean_temp_saves(force=False, int_verbose=False):
    if os.path.exists(TEMP_SAVES_PATH):
        if force or time.time() - os.path.getmtime(TEMP_SAVES_PATH) > 86400:
            os.remove(TEMP_SAVES_PATH)
            if int_verbose:
                create_log("HANDLE_DB: CLEAN_TEMP_SAVES: Removed temp save")

def check_db_tables(index='game_states'):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='game_states'")
            if not c.fetchone():
                print("CHECK_DB_TABLES: game_states table does not exist")
            else:
                print("CHECK_DB_TABLES: game_states table exists")

            c = conn.cursor()
            c.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{index}'")
            if not c.fetchone():
                print(f"CHECK_DB_TABLES: {index} table does not exist")
            else:
                print(f"CHECK_DB_TABLES: {index} table exists")
    except Exception as e:
        print(f"CHECK_DB_TABLES: Error checking database: {e}")
        raise

def learn_db_structure():
    """Connect to the database and retrieve the names of all tables and their schemas."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = c.fetchall()
            
            print("Database Tables and Schemas:")
            for table in tables:
                table_name = table[0]
                print(f"\nTable: {table_name}")
                c.execute(f"PRAGMA table_info({table_name})")
                schema = c.fetchall()
                for column in schema:
                    print(f"  - {column[1]} ({column[2]})")
    except Exception as e:
        print(f"LEARN_DB_STRUCTURE: Error learning database structure: {e}")

def delete_user(username):
    """Deletes a user and their game states from the database."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            # Get user_id first to delete related game states
            c.execute("SELECT id FROM users WHERE username = ?", (username,))
            user = c.fetchone()
            if user:
                user_id = user[0]
                c.execute("DELETE FROM game_states WHERE user_id = ?", (user_id,))
                c.execute("DELETE FROM users WHERE username = ?", (username,))
                conn.commit()
                print(f"DELETE_USER: User '{username}' and their game states deleted successfully.")
            else:
                print(f"DELETE_USER: User '{username}' not found.")
    except Exception as e:
        print(f"DELETE_USER: Error deleting user '{username}': {e}")

def list_users():
    """Connects to the database and retrieves all usernames from the users table."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute("SELECT username FROM users")
            users = c.fetchall()
            print(f"Users in the database: {users}")
            return [user[0] for user in users]
    except Exception as e:
        print(f"LIST_USERS: Error retrieving users: {e}")
        return []

def create_user(username, password):
    """Creates a new user in the database."""
    try:
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed_password))
            conn.commit()
            print(f"CREATE_USER: User '{username}' created successfully.")
    except sqlite3.IntegrityError:
        print(f"CREATE_USER: Error: Username '{username}' already exists.")
    except Exception as e:
        print(f"CREATE_USER: Error creating user '{username}': {e}")

# init_db()
# check_db_tables('users')
# learn_db_structure()
# delete_user('SMCNetwolf-02')
# list_users()
#init_db()
#check_db_tables('users')
#learn_db_structure()
#create_user('SMCNetwolf-02', 'password123')
#delete_user('SMCNetwolf-02')
#list_users()

