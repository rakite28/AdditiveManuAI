import sqlite3
import json
from datetime import datetime

DATABASE_NAME = "data/app_data.db"

def get_db_connection():
    """Establishes a connection to the database."""
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def initialize_database():
    """Creates the database tables if they don't already exist."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Printer table: Store ID and a JSON blob of the printer's properties
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS printers (
        id TEXT PRIMARY KEY,
        data TEXT NOT NULL
    )''')

    # Filaments table: Store material, brand, and a JSON blob of details
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS filaments (
        material TEXT NOT NULL,
        brand TEXT NOT NULL,
        details TEXT NOT NULL,
        PRIMARY KEY (material, brand)
    )''')

    # Logs table: Store timestamp and a JSON blob of the log entry
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        entry TEXT NOT NULL
    )''')

    conn.commit()
    conn.close()

# --- Printer Functions ---

def get_all_printers():
    conn = get_db_connection()
    printers_raw = conn.execute('SELECT data FROM printers').fetchall()
    conn.close()
    # Decode the JSON data from the 'data' column
    return [json.loads(row['data']) for row in printers_raw]

def add_or_update_printer(printer_data):
    conn = get_db_connection()
    # Use REPLACE to handle both insert and update based on the primary key (id)
    conn.execute('REPLACE INTO printers (id, data) VALUES (?, ?)',
                 (printer_data['id'], json.dumps(printer_data)))
    conn.commit()
    conn.close()

def delete_printer_by_id(printer_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM printers WHERE id = ?', (printer_id,))
    deleted_rows = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted_rows > 0

# --- Filament Functions ---

def get_all_filaments():
    conn = get_db_connection()
    filaments_raw = conn.execute('SELECT material, brand, details FROM filaments').fetchall()
    conn.close()
    # Reconstruct the nested dictionary structure
    filaments = {}
    for row in filaments_raw:
        material, brand, details_json = row['material'], row['brand'], row['details']
        if material not in filaments:
            filaments[material] = {}
        filaments[material][brand] = json.loads(details_json)
    return filaments

def add_or_update_filament(material, brand, details):
    conn = get_db_connection()
    conn.execute('REPLACE INTO filaments (material, brand, details) VALUES (?, ?, ?)',
                 (material, brand, json.dumps(details)))
    conn.commit()
    conn.close()

def delete_filament_by_material_and_brand(material, brand):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM filaments WHERE material = ? AND brand = ?', (material, brand))
    deleted_rows = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted_rows > 0

# --- Log Functions ---

def get_all_logs():
    conn = get_db_connection()
    # Order by timestamp descending to get the most recent logs first
    logs_raw = conn.execute('SELECT entry FROM logs ORDER BY timestamp DESC').fetchall()
    conn.close()
    return [json.loads(row['entry']) for row in logs_raw]

def add_log(log_entry):
    conn = get_db_connection()
    conn.execute('INSERT INTO logs (timestamp, entry) VALUES (?, ?)',
                 (log_entry.get('timestamp', datetime.now().isoformat()), json.dumps(log_entry)))
    conn.commit()
    conn.close()
