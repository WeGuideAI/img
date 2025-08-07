from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import sqlite3
import os
import base64
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# Upload folder
UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# -----------------------------
# Database Setup
# -----------------------------
def init_db():
    conn = sqlite3.connect('student.db')
    c = conn.cursor()

    # Students table
    c.execute('''
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
    ''')

    # Content table
    c.execute('''
        CREATE TABLE IF NOT EXISTS content (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER,
            image TEXT,
            audio TEXT,
            label TEXT,
            FOREIGN KEY(student_id) REFERENCES students(id)
        )
    ''')

    conn.commit()
    conn.close()

def get_db_connection():
    conn = sqlite3.connect('student.db')
    conn.row_factory = sqlite3.Row
    return conn

init_db()

# -----------------------------
# Helpers
# -----------------------------
def get_student_id(name):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM students WHERE name = ?", (name,))
    row = cur.fetchone()
    conn.close()
    return row["id"] if row else None

def get_student_content(student_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, image, audio, label FROM content WHERE student_id = ?", (student_id,))
    data = cur.fetchall()
    conn.close()
    return data

def save_file(file_data, student_name, filename, folder):
    """Saves a file from a FileStorage object or base64 data."""
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], folder)
    os.makedirs(filepath, exist_ok=True)
    file_path = os.path.join(filepath, secure_filename(filename))

    if isinstance(file_data, str) and file_data.startswith('data:'):
        # Handle base64 audio data
        header, encoded = file_data.split(',', 1)
        decoded_data = base64.b64decode(encoded)
        with open(file_path, 'wb') as f:
            f.write(decoded_data)
    else:
        # Handle regular file uploads
        file_data.save(file_path)

    return f'{folder}/{secure_filename(filename)}'

# -----------------------------
# Routes
# -----------------------------

@app.route('/', methods=['GET', 'POST'])
def playground():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT name FROM students")
    students = [row["name"] for row in cur.fetchall()]
    conn.close()

    selected_student = request.args.get("student")
    student_content = []
    theme = session.get("theme", "colorful")

    if selected_student:
        student_id = get_student_id(selected_student)
        if student_id:
            student_content = get_student_content(student_id)

    return render_template('playground.html',
                           students=students,
                           selected_student=selected_student,
                           content=student_content,
                           theme=theme)

@app.route('/set_theme', methods=['POST'])
def set_theme():
    passcode = request.form.get("passcode")
    if passcode != "1234":
        return "Unauthorized", 403

    new_theme = request.form.get("theme")
    if new_theme in ["colorful", "simple"]:
        session["theme"] = new_theme

    return redirect(url_for('playground'))

@app.route('/dashboard')
def dashboard():
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT id, name FROM students")
    students = cur.fetchall()

    content = {}
    for student_row in students:
        cur.execute("SELECT * FROM content WHERE student_id = ?", (student_row["id"],))
        content[student_row["name"]] = cur.fetchall()

    conn.close()

    return render_template("supervisor_dashboard.html", students=students, content=content)

@app.route('/add_student', methods=['POST'])
def add_student():
    name = request.form.get('student_name')
    if not name:
        return redirect(url_for('dashboard'))

    conn = get_db_connection()
    try:
        conn.execute('INSERT INTO students (name) VALUES (?)', (name,))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    conn.close()
    return redirect(url_for('dashboard'))

@app.route('/edit_student', methods=['POST'])
def edit_student():
    student_id = request.form.get('student_id')
    new_name = request.form.get('new_name')
    if not student_id or not new_name:
        return redirect(url_for('dashboard'))
    
    conn = get_db_connection()
    try:
        conn.execute('UPDATE students SET name = ? WHERE id = ?', (new_name, student_id))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    conn.close()
    return redirect(url_for('dashboard'))

@app.route('/delete_student/<int:student_id>', methods=['POST'])
def delete_student(student_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM content WHERE student_id = ?', (student_id,))
    conn.execute('DELETE FROM students WHERE id = ?', (student_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))

@app.route('/api/upload_content', methods=['POST'])
def api_upload_content():
    student_name = request.form.get('student_select')
    label = request.form.get('label')
    image_file = request.files.get('image')
    audio_data = request.form.get('audio')

    student_id = get_student_id(student_name)
    if not student_id:
        return jsonify({"success": False, "error": "Student not found"}), 404

    image_path = None
    if image_file:
        image_path = save_file(image_file, student_name, image_file.filename, student_name)
    
    audio_path = None
    if audio_data:
        audio_filename = f"audio_{label}_{student_name}.wav"
        audio_path = save_file(audio_data, student_name, audio_filename, student_name)

    conn = get_db_connection()
    conn.execute('INSERT INTO content (student_id, image, audio, label) VALUES (?, ?, ?, ?)',
                 (student_id, image_path, audio_path, label))
    conn.commit()
    conn.close()

    return jsonify({"success": True})

@app.route('/edit_content/<int:content_id>', methods=['POST'])
def edit_content(content_id):
    new_label = request.form.get('new_label')
    if not new_label:
        return "New label is required", 400

    conn = get_db_connection()
    conn.execute('UPDATE content SET label = ? WHERE id = ?', (new_label, content_id))
    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))

@app.route('/delete_content/<int:content_id>', methods=['POST'])
def delete_content(content_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM content WHERE id = ?', (content_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))

# -----------------------------
# Run App
# -----------------------------
if __name__ == '__main__':
    app.run(debug=True)
