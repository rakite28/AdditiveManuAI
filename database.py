import sqlite3
import json
from datetime import datetime
from passlib.hash import pbkdf2_sha256

DATABASE_NAME = "data/app_data.db"

def get_db_connection():
    """Establishes a connection to the database."""
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def initialize_database():
    """Creates and updates the database tables if they don't already exist."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # --- Auth Tables ---
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS companies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL
    )''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'user',
        company_id INTEGER NOT NULL,
        FOREIGN KEY (company_id) REFERENCES companies (id)
    )''')

    # --- Data Tables (with multi-tenancy support) ---
    # Add company_id to printers if it doesn't exist
    try:
        cursor.execute('ALTER TABLE printers ADD COLUMN company_id INTEGER REFERENCES companies(id)')
    except sqlite3.OperationalError:
        pass # Column already exists
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS printers (
        id TEXT PRIMARY KEY,
        company_id INTEGER NOT NULL,
        data TEXT NOT NULL,
        FOREIGN KEY (company_id) REFERENCES companies (id)
    )''')

    # Add company_id to filaments if it doesn't exist
    try:
        cursor.execute('ALTER TABLE filaments ADD COLUMN company_id INTEGER REFERENCES companies(id)')
    except sqlite3.OperationalError:
        pass # Column already exists
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS filaments (
        material TEXT NOT NULL,
        brand TEXT NOT NULL,
        company_id INTEGER NOT NULL,
        details TEXT NOT NULL,
        PRIMARY KEY (material, brand, company_id),
        FOREIGN KEY (company_id) REFERENCES companies (id)
    )''')

    # Add company_id to logs if it doesn't exist
    try:
        cursor.execute('ALTER TABLE logs ADD COLUMN company_id INTEGER REFERENCES companies(id)')
    except sqlite3.OperationalError:
        pass # Column already exists
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        company_id INTEGER NOT NULL,
        entry TEXT NOT NULL,
        FOREIGN KEY (company_id) REFERENCES companies (id)
    )''')

    conn.commit()
    conn.close()

# --- Auth and User Functions ---

def create_company_and_admin(company_name, admin_username, admin_email, admin_password):
    conn = get_db_connection()
    try:
        with conn:
            cursor = conn.execute('INSERT INTO companies (name) VALUES (?)', (company_name,))
            company_id = cursor.lastrowid
            password_hash = pbkdf2_sha256.hash(admin_password)
            conn.execute(
                'INSERT INTO users (username, email, password_hash, role, company_id) VALUES (?, ?, ?, ?, ?)',
                (admin_username, admin_email, password_hash, 'admin', company_id)
            )
        return {"company_id": company_id}
    except sqlite3.IntegrityError as e:
        return {"error": f"A company, username, or email with that name already exists."}
    finally:
        conn.close()

def find_user_by_identifier(identifier):
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE username = ? OR email = ?', (identifier, identifier)).fetchone()
    conn.close()
    return user

def verify_password(password, password_hash):
    return pbkdf2_sha256.verify(password, password_hash)

def create_user(username, email, password, role, company_id):
    """Creates a new user within a company."""
    conn = get_db_connection()
    try:
        with conn:
            password_hash = pbkdf2_sha256.hash(password)
            conn.execute(
                'INSERT INTO users (username, email, password_hash, role, company_id) VALUES (?, ?, ?, ?, ?)',
                (username, email, password_hash, role, company_id)
            )
        return {"message": "User created successfully."}
    except sqlite3.IntegrityError:
        return {"error": "Username or email already exists."}
    finally:
        conn.close()

def find_user_by_id(user_id):
    """Finds a user by their ID."""
    conn = get_db_connection()
    user = conn.execute('SELECT id, username, email, role, company_id FROM users WHERE id = ?', (user_id,)).fetchone()
    conn.close()
    return user

def update_user_profile(user_id, profile_data):
    """Updates a user's non-sensitive profile information."""
    conn = get_db_connection()
    try:
        with conn:
            # For now, only username is editable. Can be expanded.
            conn.execute(
                'UPDATE users SET username = ? WHERE id = ?',
                (profile_data.get('username'), user_id)
            )
        return {"message": "Profile updated successfully."}
    except sqlite3.IntegrityError:
        return {"error": "Username already taken."}
    finally:
        conn.close()

def update_user_password(user_id, new_password):
    """Updates a user's password."""
    conn = get_db_connection()
    with conn:
        password_hash = pbkdf2_sha256.hash(new_password)
        conn.execute('UPDATE users SET password_hash = ? WHERE id = ?', (password_hash, user_id))
    conn.close()
    return {"message": "Password updated successfully."}


# --- Printer Functions (Scoped by company_id) ---

def get_all_printers(company_id):
    conn = get_db_connection()
    printers_raw = conn.execute('SELECT data FROM printers WHERE company_id = ?', (company_id,)).fetchall()
    conn.close()
    return [json.loads(row['data']) for row in printers_raw]

def add_or_update_printer(printer_data, company_id):
    conn = get_db_connection()
    conn.execute('REPLACE INTO printers (id, company_id, data) VALUES (?, ?, ?)',
                 (printer_data['id'], company_id, json.dumps(printer_data)))
    conn.commit()
    conn.close()

def replace_all_printers(printers_list, company_id):
    """Deletes all existing printers for a company and replaces them with a new list."""
    conn = get_db_connection()
    with conn:
        conn.execute('DELETE FROM printers WHERE company_id = ?', (company_id,))
        for printer in printers_list:
            conn.execute('INSERT INTO printers (id, company_id, data) VALUES (?, ?, ?)',
                         (printer['id'], company_id, json.dumps(printer)))

def delete_printer_by_id(printer_id, company_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM printers WHERE id = ? AND company_id = ?', (printer_id, company_id))
    deleted_rows = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted_rows > 0

# --- Filament Functions (Scoped by company_id) ---

def get_all_filaments(company_id):
    conn = get_db_connection()
    filaments_raw = conn.execute('SELECT material, brand, details FROM filaments WHERE company_id = ?', (company_id,)).fetchall()
    conn.close()
    filaments = {}
    for row in filaments_raw:
        material, brand, details_json = row['material'], row['brand'], row['details']
        if material not in filaments:
            filaments[material] = {}
        filaments[material][brand] = json.loads(details_json)
    return filaments

def add_or_update_filament(material, brand, details, company_id):
    conn = get_db_connection()
    conn.execute('REPLACE INTO filaments (material, brand, company_id, details) VALUES (?, ?, ?, ?)',
                 (material, brand, company_id, json.dumps(details)))
    conn.commit()
    conn.close()

def replace_all_filaments(filaments_data, company_id):
    """Deletes all existing filaments for a company and replaces them with new data."""
    conn = get_db_connection()
    with conn:
        conn.execute('DELETE FROM filaments WHERE company_id = ?', (company_id,))
        for material, brands in filaments_data.items():
            for brand, details in brands.items():
                conn.execute('INSERT INTO filaments (material, brand, company_id, details) VALUES (?, ?, ?, ?)',
                             (material, brand, company_id, json.dumps(details)))

def delete_filament_by_material_and_brand(material, brand, company_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM filaments WHERE material = ? AND brand = ? AND company_id = ?', (material, brand, company_id))
    deleted_rows = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted_rows > 0

# --- Log Functions (Scoped by company_id) ---

def get_all_logs(company_id):
    conn = get_db_connection()
    logs_raw = conn.execute('SELECT entry FROM logs WHERE company_id = ? ORDER BY timestamp DESC', (company_id,)).fetchall()
    conn.close()
    return [json.loads(row['entry']) for row in logs_raw]

def add_log(log_entry, company_id):
    conn = get_db_connection()
    conn.execute('INSERT INTO logs (timestamp, company_id, entry) VALUES (?, ?, ?)',
                 (log_entry.get('timestamp', datetime.now().isoformat()), company_id, json.dumps(log_entry)))
    conn.commit()
    conn.close()

def get_processed_log_filenames(company_id):
    """Returns a set of all filenames that have been logged for a company."""
    conn = get_db_connection()
    rows = conn.execute('SELECT entry FROM logs WHERE company_id = ?', (company_id,)).fetchall()
    conn.close()
    filenames = set()
    for row in rows:
        try:
            entry_data = json.loads(row['entry'])
            if 'filename' in entry_data:
                filenames.add(entry_data['filename'])
        except (json.JSONDecodeError, KeyError):
            continue
    return list(filenames) # Return as list for JSON serialization
