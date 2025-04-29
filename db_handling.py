#TODO: Database setup
'''
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
'''