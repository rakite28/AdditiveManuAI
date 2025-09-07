import os
import re
import json
import time
import shutil
import sys
import logging
from datetime import datetime, timedelta
import easyocr
from openpyxl import load_workbook, Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from flask import Flask, request, jsonify, send_from_directory, abort
from flask_cors import CORS
from werkzeug.utils import secure_filename
from werkzeug.exceptions import HTTPException

# --- Custom Modules ---
import database as db
from exceptions import InvalidAPIUsage
from helpers import (
    calculate_printer_hourly_rate,
    calculate_cogs_values,
    parse_time_string,
    extract_data_from_ocr,
    generate_quotation_pdf
)

# --- Server Configuration ---
UPLOAD_FOLDER = "uploads"
GENERATED_FILES_FOLDER = "generated_files"

# --- Logging Configuration ---
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[logging.StreamHandler(sys.stdout)])

# --- Flask App Initialization ---
app = Flask(__name__)
CORS(app)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# --- Error Handlers ---
@app.errorhandler(InvalidAPIUsage)
def handle_invalid_usage(error):
    response = jsonify(error.to_dict())
    response.status_code = error.status_code
    return response

@app.errorhandler(HTTPException)
def handle_http_exception(e):
    response = e.get_response()
    response.data = json.dumps({
        "code": e.code,
        "name": e.name,
        "error": e.description,
    })
    response.content_type = "application/json"
    return response

@app.errorhandler(Exception)
def handle_generic_exception(e):
    logging.error(f"Unhandled Exception: {e}", exc_info=True)
    response = jsonify({"error": "An unexpected internal server error occurred."})
    response.status_code = 500
    return response

# --- One-time Model Loading ---
logging.info("Loading EasyOCR model into memory...")
try:
    ocr_reader = easyocr.Reader(['en'])
    logging.info("EasyOCR model loaded successfully.")
except Exception as e:
    logging.critical(f"FATAL: Could not load EasyOCR model. Error: {e}")
    ocr_reader = None

# --- Initial File & Folder Setup ---
def initialize_server_folders():
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(GENERATED_FILES_FOLDER, exist_ok=True)
    os.makedirs("data", exist_ok=True)


# --- API Endpoints ---

@app.route('/printers', methods=['GET', 'POST'])
def handle_printers():
    if request.method == 'GET':
        printers = db.get_all_printers()
        for printer in printers:
            printer['hourly_rate'] = calculate_printer_hourly_rate(printer)
        return jsonify(printers)

    if request.method == 'POST':
        data = request.json
        if not data:
            raise InvalidAPIUsage("No data provided.", status_code=400)

        if 'id' not in data or not data['id']:
            data['id'] = str(time.time())

        db.add_or_update_printer(data)
        logging.info(f"Added/updated printer with ID: {data['id']}")
        return jsonify(data), 201

@app.route('/printers/<string:printer_id>', methods=['DELETE'])
def delete_printer(printer_id):
    if not db.delete_printer_by_id(printer_id):
        raise InvalidAPIUsage("Printer not found.", status_code=404)
    logging.info(f"Deleted printer with ID: {printer_id}")
    return jsonify({"message": "Printer deleted"}), 200

@app.route('/filaments', methods=['GET', 'POST'])
def handle_filaments():
    if request.method == 'GET':
        return jsonify(db.get_all_filaments())

    if request.method == 'POST':
        data = request.json
        if not data or 'material' not in data or 'brand' not in data or 'details' not in data:
            raise InvalidAPIUsage("Request must include 'material', 'brand', and 'details'.", status_code=400)

        db.add_or_update_filament(data['material'], data['brand'], data['details'])
        logging.info(f"Added/updated filament: {data['material']}/{data['brand']}")
        return jsonify(data), 201

@app.route('/filaments/<string:material>/<string:brand>', methods=['DELETE'])
def delete_filament(material, brand):
    if not db.delete_filament_by_material_and_brand(material, brand):
        raise InvalidAPIUsage("Filament not found.", status_code=404)
    logging.info(f"Deleted filament: {material}/{brand}")
    return jsonify({"message": "Filament deleted"}), 200

@app.route('/logs', methods=['GET', 'POST'])
def handle_logs():
    if request.method == 'GET':
        return jsonify(db.get_all_logs())

    if request.method == 'POST':
        log_entry = request.json
        if not log_entry:
            raise InvalidAPIUsage("No log entry provided.", status_code=400)
        if 'timestamp' not in log_entry:
            log_entry['timestamp'] = datetime.now().isoformat()

        db.add_log(log_entry)
        logging.info("Added new log entry.")
        return jsonify(log_entry), 201

@app.route('/ocr', methods=['POST'])
def process_ocr():
    if ocr_reader is None:
        raise InvalidAPIUsage("OCR service is not available.", status_code=503)
    if 'file' not in request.files:
        raise InvalidAPIUsage("No file part in the request.", status_code=400)
    file = request.files['file']
    if file.filename == '':
        raise InvalidAPIUsage("No file selected for uploading.", status_code=400)

    if file:
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)

        if not os.path.abspath(filepath).startswith(os.path.abspath(app.config['UPLOAD_FOLDER'])):
            raise InvalidAPIUsage("Invalid file path.", status_code=400)

        file.save(filepath)
        logging.info(f"Processing OCR for file: {filename}")

        try:
            ocr_results = ocr_reader.readtext(filepath)
            extracted_data = extract_data_from_ocr(ocr_results)
            return jsonify(extracted_data)
        finally:
            if os.path.exists(filepath):
                os.remove(filepath)

@app.route('/generate-quotation', methods=['POST'])
def create_quotation():
    data = request.json
    if not data:
        raise InvalidAPIUsage("No data provided for quotation.", status_code=400)

    customer_name = data.get('customer_name', 'quote')
    safe_customer_name = secure_filename(customer_name)
    filename = f"Quotation_{safe_customer_name}_{int(time.time())}.pdf"
    filepath = os.path.join(app.config['GENERATED_FILES_FOLDER'], filename)

    # Generate the PDF using the placeholder function
    generate_quotation_pdf(filepath, data)
    logging.info(f"Generated quotation: {filename}")

    download_url = f"/downloads/{filename}"
    return jsonify({"download_url": download_url, "filename": filename})

@app.route('/downloads/<string:filename>', methods=['GET'])
def download_file(filename):
    """Endpoint to serve the generated files."""
    if '/' in filename or '\\' in filename:
        abort(404)

    safe_directory = os.path.abspath(app.config['GENERATED_FILES_FOLDER'])
    safe_filepath = os.path.abspath(os.path.join(safe_directory, filename))

    if not safe_filepath.startswith(safe_directory):
        abort(404)

    return send_from_directory(app.config['GENERATED_FILES_FOLDER'], filename, as_attachment=True)

# --- Main Execution ---
if __name__ == '__main__':
    initialize_server_folders()
    db.initialize_database()
    port = int(os.environ.get("PORT", 5000))
    logging.info(f"Server starting on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
