import os
import sqlite3


from flask import Flask, send_file  , render_template, request, jsonify, url_for, flash, redirect
from werkzeug.exceptions import abort


#if you use templates, the index.html file should be in the templates folder, else in src folder
use_templates = False

#if you use database, in this build you have to use templates:
use_database = False

# if you use chatbot suggested by gemini, in this build you use an specific template:
use_gemini_chatbot = False

app = Flask(__name__)

#TODO: implement secret key
app.config['SECRET_KEY'] = 'your secret key'


@app.route("/")
def index():
    if use_database:
        conn = get_db_connection()
        posts = conn.execute('SELECT * FROM posts').fetchall()
        conn.close()
        return render_template('index_template_db.html', posts=posts)
    elif use_gemini_chatbot:
        return render_template('index_gemini.html')
    elif use_templates:
        return render_template('index_template.html')
    else: 
        return send_file('templates/index.html')
    

@app.route("/get", methods=["GET", "POST"])
def get_bot_response():
    user_message = request.form["msg"]
    # Basic response logic (replace with more advanced logic)
    if "hello" in user_message.lower():
        bot_response = "Hello there!"
    elif "how are you" in user_message.lower():
        bot_response = "I'm doing well, thank you."
    else:
        bot_response = "I'm not sure I understand."
    return jsonify({"response": bot_response})  


@app.route('/<int:post_id>')
def post(post_id):
    post = get_post(post_id)
    return render_template('post.html', post=post)


@app.route('/create', methods=('GET', 'POST'))
def create():
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']

        if not title:
            flash('Title is required!')
        else:
            conn = get_db_connection()
            conn.execute('INSERT INTO posts (title, content) VALUES (?, ?)',
                         (title, content))
            conn.commit()
            conn.close()
            return redirect(url_for('index'))
    return render_template('create_post.html')

@app.route('/<int:id>/edit', methods=('GET', 'POST'))
def edit(id):
    post = get_post(id)

    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']

        if not title:
            flash('Title is required!')
        else:
            conn = get_db_connection()
            conn.execute('UPDATE posts SET title = ?, content = ?'
                         ' WHERE id = ?',
                         (title, content, id))
            conn.commit()
            conn.close()
            return redirect(url_for('index'))

    return render_template('edit_post.html', post=post)

@app.route('/<int:id>/delete', methods=('POST',))
def delete(id):
    post = get_post(id)
    conn = get_db_connection()
    conn.execute('DELETE FROM posts WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    flash('"{}" was successfully deleted!'.format(post['title']))
    return redirect(url_for('index'))



def get_db_connection():
    conn = sqlite3.connect('database/blog_database.db')
    conn.row_factory = sqlite3.Row
    return conn

def get_post(post_id):
    conn = get_db_connection()
    post = conn.execute('SELECT * FROM posts WHERE id = ?',
                        (post_id,)).fetchone()
    conn.close()
    if post is None:
        abort(404)
    return post


def main():
        app.run(port=int(os.environ.get('PORT', 80)))


if __name__ == "__main__":
    main()    