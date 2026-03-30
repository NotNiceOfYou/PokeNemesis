import os
import psycopg2
import requests
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from nemesis import Nemesis

app = Flask(__name__)
app.secret_key = 'your-secret-key-here-change-in-production'  # Change this!

# Database connection settings (adjust if needed)
DB_CONFIG = {
    'dbname': 'PokemonDatabase',
    'user': 'postgres',
    'password': 'abcd1234',
    'host': 'localhost',
    'port': '5432'
}

nemesis_engine = Nemesis(DB_CONFIG)

def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)

# ---------- Helper: login_required decorator ----------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            # For API routes return 401, for page routes redirect
            if request.path.startswith('/api/'):
                return jsonify({'error': 'Not logged in'}), 401
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function

# ---------- Routes for pages ----------
@app.route('/')
def home():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login_page'))

@app.route('/login')
def login_page():
    return render_template('login.html')

@app.route('/register')
def register_page():
    return render_template('register.html')

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')

# ---------- API routes ----------
@app.route('/api/user', methods=['GET'])
@login_required
def api_user():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT username FROM users WHERE id = %s", (session['user_id'],))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        return jsonify({'error': 'User not found'}), 404
    return jsonify({'user_id': session['user_id'], 'username': row[0]})

@app.route('/api/pokemon', methods=['GET'])
@login_required
def api_pokemon():
    """Return list of all Pokémon with id and name (ordered by id)."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name FROM pokemon ORDER BY id")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify([{'id': r[0], 'name': r[1]} for r in rows])

@app.route('/api/teams', methods=['GET', 'POST'])
@login_required
def api_teams():
    conn = get_db_connection()
    cur = conn.cursor()
    if request.method == 'GET':
        cur.execute("""
            SELECT id, name, pokemon_ids FROM teams
            WHERE user_id = %s ORDER BY id
        """, (session['user_id'],))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify([{
            'id': r[0],
            'name': r[1],
            'pokemon_ids': r[2]  # already a list (PostgreSQL array)
        } for r in rows])
    else:  # POST – create new team
        data = request.get_json()
        name = data.get('name')
        pokemon_ids = data.get('pokemon_ids')  # list of 6 ints
        if not name or not pokemon_ids or len(pokemon_ids) != 6:
            return jsonify({'error': 'Invalid team data'}), 400
        # Check team count limit (max 10)
        cur.execute("SELECT COUNT(*) FROM teams WHERE user_id = %s", (session['user_id'],))
        count = cur.fetchone()[0]
        if count >= 10:
            cur.close()
            conn.close()
            return jsonify({'error': 'You already have 10 teams. Delete one first.'}), 400
        # Insert — use DEFAULT for id (SERIAL)
        cur.execute("""
            INSERT INTO teams (user_id, name, pokemon_ids)
            VALUES (%s, %s, %s)
        """, (session['user_id'], name, pokemon_ids))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({'success': True}), 201

@app.route('/api/teams/<int:team_id>', methods=['DELETE'])
@login_required
def api_delete_team(team_id):
    conn = get_db_connection()
    cur = conn.cursor()
    # Ensure team belongs to current user
    cur.execute("DELETE FROM teams WHERE id = %s AND user_id = %s", (team_id, session['user_id']))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/nemesis', methods=['POST'])
@login_required
def api_nemesis():
    data = request.get_json()
    opponent_ids = data.get('team')

    # Basic validation
    if not opponent_ids or len(opponent_ids) != 6:
        return jsonify({'error': 'Team must contain exactly 6 Pokémon IDs'}), 400

    try:
        # Pass the request to your clean, separated class
        nemesis_team = nemesis_engine.get_team(opponent_ids)
        
        return jsonify({'nemesis_team': nemesis_team}), 200

    except Exception as e:
        # Good practice to catch unexpected errors and not crash the server
        return jsonify({'error': str(e)}), 500

# ---------- Authentication routes ----------
@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    username = data.get('username', '').strip()
    password = data.get('password', '')
    if not username or not password:
        return jsonify({'error': 'Missing username or password'}), 400

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, password_hash FROM users WHERE username = %s", (username,))
    user = cur.fetchone()
    cur.close()
    conn.close()

    if user and check_password_hash(user[1], password):
        session['user_id'] = user[0]
        return jsonify({'success': True})
    else:
        return jsonify({'error': 'Invalid username or password'}), 401

@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    username = data.get('username', '').strip()
    password = data.get('password', '')
    if not username or not password:
        return jsonify({'error': 'Missing username or password'}), 400
    if len(password) < 4:
        return jsonify({'error': 'Password must be at least 4 characters'}), 400

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        hashed = generate_password_hash(password)
        cur.execute("INSERT INTO users (username, password_hash) VALUES (%s, %s)", (username, hashed))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({'success': True}), 201
    except psycopg2.IntegrityError:
        conn.rollback()
        cur.close()
        conn.close()
        return jsonify({'error': 'Username already exists'}), 409

@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'success': True})

# ---------- Run the app ----------
if __name__ == '__main__':
    app.run(debug=True)