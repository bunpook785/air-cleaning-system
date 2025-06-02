# app.py
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from datetime import date, datetime, timedelta
import gspread # สำหรับเชื่อมต่อ Google Sheets
from oauth2client.service_account import ServiceAccountCredentials # สำหรับยืนยันตัวตน Google
import os
import json # สำหรับอ่านไฟล์ JSON ของ Service Account
from functools import wraps # สำหรับ decorator (ถ้าจำเป็น)

app = Flask(__name__)
# IMPORTANT: Change this to a very strong, random key in production!
# You should ideally get this from an environment variable (os.getenv('SECRET_KEY'))
app.secret_key = os.getenv('SECRET_KEY', 'your_super_secret_key_change_this_in_production')

# --- Google Sheets Setup ---
# Get credentials from environment variable for Replit deployment
# In Replit, you will set this as a secret named 'GOOGLE_SHEETS_CREDENTIALS'
# The value will be the *entire JSON content* of your downloaded service account key file
GOOGLE_SHEETS_CREDENTIALS_JSON = os.getenv('GOOGLE_SHEETS_CREDENTIALS')
if not GOOGLE_SHEETS_CREDENTIALS_JSON:
    raise ValueError("GOOGLE_SHEETS_CREDENTIALS environment variable not set.")

try:
    # Parse the JSON string from the environment variable
    creds_dict = json.loads(GOOGLE_SHEETS_CREDENTIALS_JSON)
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
except Exception as e:
    raise RuntimeError(f"Error loading Google Sheets credentials: {e}")

# Open your Google Sheet by name
try:
    spreadsheet = client.open("AirConServiceData") # <-- Change this to your Google Sheet's name
    aircons_sheet = spreadsheet.worksheet("AirCons") # <-- Name of the AirCons sheet
    servicelogs_sheet = spreadsheet.worksheet("ServiceLogs") # <-- Name of the ServiceLogs sheet
    technicians_sheet = spreadsheet.worksheet("Technicians") # <-- Name of the Technicians sheet
except Exception as e:
    raise RuntimeError(f"Error opening Google Sheet or worksheets: {e}. Make sure the sheet name is correct and service account has Editor access.")


# --- Helper functions for Google Sheets data ---

def get_all_aircons():
    # Get all records from the 'AirCons' sheet
    # This reads all rows starting from the second row (skipping headers)
    records = aircons_sheet.get_all_records()
    
    # Convert list of dictionaries to a dictionary keyed by 'serial'
    air_conditioners_data = {}
    for record in records:
        record_serial = str(record.get('serial')).strip() # Ensure serial is string and trim whitespace
        if record_serial:
            # Convert date strings to date objects if they exist
            if record.get('last_clean_date'):
                try:
                    record['last_clean_date'] = datetime.strptime(str(record['last_clean_date']), '%Y-%m-%d').date()
                except ValueError:
                    record['last_clean_date'] = None # Invalid date format
            if record.get('next_clean_date'):
                try:
                    record['next_clean_date'] = datetime.strptime(str(record['next_clean_date']), '%Y-%m-%d').date()
                except ValueError:
                    record['next_clean_date'] = None # Invalid date format
            
            air_conditioners_data[record_serial] = record
    return air_conditioners_data

def get_aircon_by_serial(serial):
    aircons = get_all_aircons()
    return aircons.get(serial)

def update_aircon_data(serial, data):
    # Find the row number for the given serial
    cell = aircons_sheet.find(serial, in_column=1) # Find serial in column A (1st column)
    if not cell:
        return False # Serial not found

    # Get all headers from the sheet to map column names to indices
    headers = aircons_sheet.row_values(1)
    
    # Update only the specific columns provided in 'data'
    # Ensure data values are formatted correctly for sheets (e.g., date to string)
    updated_values = []
    for col_idx, header in enumerate(headers):
        if header in data:
            value = data[header]
            if isinstance(value, date): # Convert date objects back to string for sheet
                updated_values.append(value.strftime('%Y-%m-%d'))
            elif value is None: # Handle None values for empty cells
                updated_values.append('')
            else:
                updated_values.append(str(value))
        else:
            # If a field is not in 'data', keep its existing value (read from sheet first)
            # This requires reading the entire row, which can be inefficient for many updates.
            # A simpler approach for this project: just update the specific cells.
            # For simplicity, we'll assume 'data' contains all fields that might be updated.
            # If a field is *not* in 'data', its original value won't change.
            # The user's original HTML form sends all fields, so this is okay.
            pass # We will update specific cells later

    # Create a list of A1 notations for the cells to update and their values
    updates = []
    for key, value in data.items():
        if key in headers:
            col_index = headers.index(key) + 1 # +1 because gspread is 1-indexed
            # Convert date objects to string for Google Sheets
            if isinstance(value, date):
                value = value.strftime('%Y-%m-%d')
            elif value is None:
                value = '' # Empty string for None values
            updates.append({'range': f"{gspread.utils.rowcol_to_a1(cell.row, col_index)}", 'values': [[value]]})
    
    if updates:
        aircons_sheet.batch_update(updates)
    
    return True

def add_service_log(log_data):
    # Ensure log_data matches the sheet's columns order
    # ['serial', 'service_date', 'service_type', 'problems_found', 'actions_taken', 'parts_replaced', 'service_fee', 'technician_name', 'notes']
    
    # Convert date object to string if present
    if 'service_date' in log_data and isinstance(log_data['service_date'], date):
        log_data['service_date'] = log_data['service_date'].strftime('%Y-%m-%d')
    if 'service_fee' in log_data and log_data['service_fee'] is not None:
        log_data['service_fee'] = str(log_data['service_fee']) # Ensure it's string for GSheets

    # Get headers from ServiceLogs sheet to ensure correct order
    headers = servicelogs_sheet.row_values(1)
    row_to_append = [log_data.get(header, '') for header in headers] # Get value or empty string if key not found

    servicelogs_sheet.append_row(row_to_append)
    return True

def get_service_logs_by_serial(serial):
    all_logs = servicelogs_sheet.get_all_records()
    filtered_logs = [
        log for log in all_logs 
        if str(log.get('serial')).strip() == str(serial).strip()
    ]
    # Convert date strings to date objects for countdown logic or formatting
    for log in filtered_logs:
        if log.get('service_date'):
            try:
                log['service_date'] = datetime.strptime(str(log['service_date']), '%Y-%m-%d').date()
            except ValueError:
                log['service_date'] = None
    return filtered_logs

def get_technician_by_username(username):
    all_technicians = technicians_sheet.get_all_records()
    for tech in all_technicians:
        if tech.get('username') == username:
            return tech
    return None

# --- Flask Routes ---

@app.route("/")
def home():
    return "ระบบนัดล้างแอร์ออนไลน์"

@app.route("/ac/<ac_id>")
def show_ac(ac_id):
    air_conditioners = get_all_aircons() # Load data from Google Sheet
    ac = air_conditioners.get(ac_id)
    if not ac:
        return render_template("show_ac.html", ac=None, countdown="ไม่พบข้อมูลเครื่องแอร์นี้")

    today = date.today()
    countdown_message = ""
    
    # Make sure next_clean_date is a date object
    if ac.get('next_clean_date') and isinstance(ac['next_clean_date'], date):
        next_date = ac['next_clean_date']
        
        diff = next_date - today
        if diff.days > 0:
            countdown_message = f"เหลือเวลาอีก {diff.days} วัน จะถึงกำหนดล้างแอร์ครั้งต่อไป"
        elif diff.days == 0:
            countdown_message = "วันนี้ถึงกำหนดล้างแอร์แล้ว!"
        else:
            countdown_message = f"เลยกำหนดล้างแอร์มาแล้ว {abs(diff.days)} วัน โปรดติดต่อช่างเพื่อเข้ารับบริการ"
    else:
        countdown_message = "ยังไม่มีกำหนดการล้างครั้งต่อไป"

    # Get service logs for display
    service_logs = get_service_logs_by_serial(ac_id)
    
    return render_template("show_ac.html", ac=ac, countdown=countdown_message, service_logs=service_logs)

@app.route("/ac/<ac_id>/login", methods=["GET", "POST"])
def technician_login(ac_id):
    if request.method == "POST":
        password_input = request.form.get("password")
        username_input = request.form.get("username") # Assuming username is also needed

        technician = get_technician_by_username(username_input)
        
        if technician and technician.get('password') == password_input: # Simple password check for demo
            session["technician_logged_in"] = True
            session["ac_id_for_edit"] = ac_id # Store the AC ID for editing
            return redirect(url_for("edit_ac", ac_id=ac_id))
        else:
            return render_template("login.html", ac_id=ac_id, error="ชื่อผู้ใช้งานหรือรหัสผ่านไม่ถูกต้อง")
    return render_template("login.html", ac_id=ac_id)

@app.route("/ac/<ac_id>/edit", methods=["GET", "POST"])
def edit_ac(ac_id):
    # Check if technician is logged in and is authorized for this AC
    if not session.get("technician_logged_in") or session.get("ac_id_for_edit") != ac_id:
        # If not logged in or not authorized, redirect to the view page
        return redirect(url_for("show_ac", ac_id=ac_id))
    
    # Load data for the specific AC from Google Sheet
    ac = get_aircon_by_serial(ac_id)
    if not ac:
        return "ไม่พบข้อมูลเครื่องแอร์นี้", 404

    if request.method == "POST":
        # Get data from the form
        customer_name = request.form.get("customer_name", "")
        customer_phone = request.form.get("customer_phone", "")
        last_clean_date_str = request.form.get("last_clean_date", None)
        next_clean_date_str = request.form.get("next_clean_date", None)
        notes = request.form.get("notes", "")

        # New service log data
        service_date_str = request.form.get("service_date", None)
        service_type = request.form.get("service_type", "ล้างแอร์")
        problems_found = request.form.get("problems_found", "")
        actions_taken = request.form.get("actions_taken", "")
        parts_replaced = request.form.get("parts_replaced", "")
        service_fee = request.form.get("service_fee", "")
        service_notes = request.form.get("service_notes", "") # New field for service log notes

        # Convert date strings to date objects
        last_clean_date = datetime.strptime(last_clean_date_str, '%Y-%m-%d').date() if last_clean_date_str else None
        next_clean_date = datetime.strptime(next_clean_date_str, '%Y-%m-%d').date() if next_clean_date_str else None
        service_date = datetime.strptime(service_date_str, '%Y-%m-%d').date() if service_date_str else None
        
        # Convert service_fee to float/decimal if it's not empty
        if service_fee:
            try:
                service_fee = float(service_fee)
            except ValueError:
                service_fee = None # Handle invalid numeric input

        # Get technician full name (assuming logged in technician is the one making the update)
        # For a full system, you'd get the actual technician name from their login session/ID
        # For this demo, we'll just use a placeholder or retrieve the logged-in technician's name
        logged_in_username = session.get('technician_username') # Assuming you store username in session on login
        technician_info = get_technician_by_username(logged_in_username) if logged_in_username else None
        technician_full_name = technician_info.get('full_name', 'ไม่ระบุชื่อช่าง') if technician_info else 'ไม่ระบุชื่อช่าง'


        # Prepare data for updating AirCons sheet
        update_data = {
            "customer_name": customer_name,
            "customer_phone": customer_phone,
            "last_clean_date": last_clean_date,
            "next_clean_date": next_clean_date,
            "notes": notes
        }
        update_aircon_data(ac_id, update_data)

        # Prepare data for adding to ServiceLogs sheet
        if service_date and actions_taken: # Only add log if necessary fields are present
            log_data = {
                "serial": ac_id,
                "service_date": service_date,
                "service_type": service_type,
                "problems_found": problems_found,
                "actions_taken": actions_taken,
                "parts_replaced": parts_replaced,
                "service_fee": service_fee,
                "technician_name": technician_full_name,
                "notes": service_notes # Using the new field for service log notes
            }
            add_service_log(log_data)

        return redirect(url_for("show_ac", ac_id=ac_id))
    
    # For GET request, render the form
    # Convert date objects back to string for HTML date input field
    if ac.get('last_clean_date'):
        ac['last_clean_date'] = ac['last_clean_date'].strftime('%Y-%m-%d')
    if ac.get('next_clean_date'):
        ac['next_clean_date'] = ac['next_clean_date'].strftime('%Y-%m-%d')

    # Default today's date for service_date in form
    today_str = date.today().strftime('%Y-%m-%d')

    return render_template("edit_ac.html", ac=ac, today_date=today_str)

@app.route("/logout")
def logout():
    session.pop("technician_logged_in", None)
    session.pop("ac_id_for_edit", None)
    session.pop("technician_username", None) # Clear technician username too
    return redirect(url_for("home"))


if __name__ == "__main__":
    app.run(debug=True) # debug=True is for development only
