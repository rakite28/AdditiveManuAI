import re
from exceptions import InvalidAPIUsage

def calculate_printer_hourly_rate(printer_data):
    try:
        required_keys = ['setup_cost', 'maintenance_cost', 'lifetime_years', 'power_w', 'price_kwh']
        for key in required_keys:
            if key not in printer_data:
                raise InvalidAPIUsage(f"Missing required field in printer data: '{key}'", status_code=400)

        total_cost = float(printer_data['setup_cost']) + (float(printer_data['maintenance_cost']) * float(printer_data['lifetime_years']))
        total_hours = float(printer_data['lifetime_years']) * 365 * 24 * (float(printer_data.get('uptime_percent', 50)) / 100)

        if total_hours == 0:
            raise InvalidAPIUsage("Printer lifetime results in zero operational hours.", status_code=400)

        depreciation = total_cost / total_hours
        electricity = (float(printer_data['power_w']) / 1000) * float(printer_data['price_kwh'])
        return depreciation + electricity
    except (ValueError, TypeError) as e:
        raise InvalidAPIUsage(f"Invalid data type for printer calculation: {e}", status_code=400)

def calculate_cogs_values(form_data, printer_data, filament_data):
    try:
        filament_g = float(form_data.get("Filament (g)", 0))
        time_str = form_data.get("Time (e.g. 7h 30m)", "0h 0m")
        labour_time_min = float(form_data.get("Labour Time (min)", 0))
        labour_rate_user = float(form_data.get("Labour Rate (₹/hr)", 100))

        print_time_hours = parse_time_string(time_str)
        mat_cost = (float(filament_data.get('price', 0)) / 1000) * filament_g * float(filament_data.get('efficiency_factor', 1.0))
        labour_cogs = (labour_rate_user / 60) * labour_time_min

        printer_hourly_rate = calculate_printer_hourly_rate(printer_data)
        printer_cogs = printer_hourly_rate * float(printer_data.get('buffer_factor', 1.0)) * print_time_hours

        total_cogs = mat_cost + labour_cogs + printer_cogs
        return {"user_cogs": total_cogs}
    except (ValueError, TypeError) as e:
        raise InvalidAPIUsage(f"Invalid data type for COGS calculation: {e}", status_code=400)
    except KeyError as e:
        raise InvalidAPIUsage(f"Missing required field for COGS calculation: {e}", status_code=400)

def parse_time_string(time_str):
    h = m = s = 0
    h_match = re.search(r'(\d+)\s*h', time_str, re.IGNORECASE)
    m_match = re.search(r'(\d+)\s*m', time_str, re.IGNORECASE)
    s_match = re.search(r'(\d+)\s*s', time_str, re.IGNORECASE)
    if h_match: h = int(h_match.group(1))
    if m_match: m = int(m_match.group(1))
    if s_match: s = int(s_match.group(1))
    return round(h + (m / 60.0) + (s / 3600.0), 2)

def extract_data_from_ocr(ocr_results):
    """
    Placeholder function for extracting structured data from OCR results.
    This function needs to be implemented based on the expected format of the OCR output.
    """
    print(f"WARNING: extract_data_from_ocr is not implemented. OCR results: {ocr_results}")
    return {}

def generate_quotation_pdf(filepath, data):
    """
    Placeholder function for generating a quotation PDF.
    This function needs to be implemented.
    """
    print(f"WARNING: generate_quotation_pdf is not implemented. Filepath: {filepath}, Data: {data}")
    # Create a dummy file to avoid 404 errors for the download link
    with open(filepath, 'w') as f:
        f.write("This is a placeholder for the quotation PDF.")
