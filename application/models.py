import os
import logging
import textwrap
import fitz  # PyMuPDF
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
from gridfs import GridFS
from bson.objectid import ObjectId
from groq import Groq
import uuid
from datetime import datetime
import datetime
import io
from flask import send_file, abort

# API key setup for Groq (Summarization)
api_key = "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"

# Initialize the Groq client
client_groq = Groq(api_key=api_key)

# Verify API key is set correctly
if not api_key:
    logging.error("API key is not set")
    exit(1)
else:
    logging.info("API key set correctly.")

# MongoDB setup
client = MongoClient('mongodb://localhost:27017/')
db = client['myhealth_db']
patients_collection = db['patients']
doctors_collection = db['doctors']
prescriptions_collection = db['prescriptions']
fs = GridFS(db)
contacts_collection = db['contacts']


# Create patient
def create_patient(username, email, name, mobile_no, password):
    hashed_password = generate_password_hash(password)
    patient = {
        'username': username,
        'email': email,
        'name': name,
        'mobile_no': mobile_no,
        'password': hashed_password
    }
    result = patients_collection.insert_one(patient)
    if result.acknowledged:
        print(f'Patient created with id: {result.inserted_id}')
    else:
        print('Failed to create patient')

# Create doctor
def create_doctor(d_username, email, name, mobile_no, license_no, hospital_name, password):
    hashed_password = generate_password_hash(password)
    doctor = {
        'd_username': d_username,
        'email': email,
        'name': name,
        'mobile_no': mobile_no,
        'license_no': license_no,
        'hospital_name': hospital_name,
        'password': hashed_password
    }
    result = doctors_collection.insert_one(doctor)
    if result.acknowledged:
        print(f'Doctor created with id: {result.inserted_id}')
    else:
        print('Failed to create doctor')

# Verify patient
def verify_patient(username, password):
    patient = patients_collection.find_one({'username': username})
    if patient and check_password_hash(patient['password'], password):
        return patient
    return None

# Verify doctor
def verify_doctor(d_username, password):
    doctor = doctors_collection.find_one({'d_username': d_username})
    if doctor and check_password_hash(doctor['password'], password):
        return doctor
    return None


def upload_report(username, report_file, filename):
    reports_collection = db[f'reports_{username}']  # Collection specific to the user
    file_id = fs.put(report_file, filename=filename)
    
    # Save report metadata in the user's collection
    report_id = reports_collection.insert_one({
        'file_id': file_id,
        'filename': filename,
        'username': username,
        'report_id': str(file_id)  # Make sure to include report_id
    }).inserted_id

    return report_id

def get_reports_for_patient(username):
    reports_collection = db[f'reports_{username}']
    reports = reports_collection.find()
    
    reports_list = []
    for report in reports:
        reports_list.append({
            'report_id': str(report.get('report_id', 'N/A')),  # Default to 'N/A' if missing
            'filename': report.get('filename', 'Unknown'),
            'username': report.get('username', 'Unknown')
        })

    return reports_list

def download_report(username, file_id):
    reports_collection = db[f'reports_{username}']
    try:
        # Ensure file_id is of type ObjectId
        if isinstance(file_id, str):
            file_id = ObjectId(file_id)

        # Find the report by file_id
        report = reports_collection.find_one({'file_id': file_id})
        if report:
            return fs.get(file_id)
        else:
            raise ValueError(f"No report found with file_id: {file_id}")
    except Exception as e:
        logging.error(f"Error downloading report: {e}")
        return None

def summarize_report(username, file_id):
    reports_collection = db[f'reports_{username}']

    try:
        # Convert file_id to ObjectId if it's a string
        if isinstance(file_id, str):
            try:
                file_id = ObjectId(file_id)
            except Exception as e:
                logging.error(f"Invalid file_id format: {file_id}, Error: {e}")
                return "Invalid file ID format."

        # Find the report by file_id
        report = reports_collection.find_one({'file_id': file_id})
        if report:
            # Download the file from GridFS
            file = fs.get(report['file_id'])
            file_path = '/tmp/temp_report.pdf'  # Temporary path to save the file

            # Save the file locally
            with open(file_path, 'wb') as f:
                f.write(file.read())

            # Extract text from the saved PDF
            text = extract_text_from_pdf(file_path)

            # Summarize the content
            summary = summarize_content_in_chunks(text)

            # Optionally clean up the temporary file
            os.remove(file_path)

            return summary
        else:
            logging.error(f"No report found with file_id: {file_id}")
            return "Report not found."
    except Exception as e:
        logging.error(f"Error summarizing report: {e}")
        return "Error summarizing report."

# Extract text from PDF
def extract_text_from_pdf(file_path):
    try:
        pdf_document = fitz.open(file_path)
        text = ""
        for page_num in range(len(pdf_document)):
            page = pdf_document.load_page(page_num)
            text += page.get_text()
        return text
    except Exception as e:
        logging.error(f"Error extracting text from PDF: {e}")
        return None

# Summarize content in chunks
def summarize_content_in_chunks(text, chunk_size=2000, model="llama-3.1-70b-versatile"):
    if text:
        chunks = textwrap.wrap(text, chunk_size)
        summaries = []
        for chunk in chunks:
            try:
                chat_completion = client_groq.chat.completions.create(
                    messages=[
                        {
                            "role": "user",
                            "content": f"Provide a brief and concise summary focusing on the key findings: {chunk}",
                        }
                    ],
                    model=model,
                )
                summary = chat_completion.choices[0].message.content
                summaries.append(summary)
            except Exception as e:
                logging.error(f"Error summarizing content: {e}")
                return None
        combined_summary = " ".join(summaries)
        condensed_summary = condense_summary(combined_summary, model=model)
        return condensed_summary
    else:
        return "No content to summarize."

# Condense summary
def condense_summary(text, model="llama-3.1-70b-versatile"):
    try:
        chat_completion = client_groq.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": f"Make the summary more precise: {text}",
                }
            ],
            model=model,
        )
        condensed_summary = chat_completion.choices[0].message.content
        return condensed_summary
    except Exception as e:
        logging.error(f"Error condensing summary: {e}")
        return None

# Check if a username is valid
def is_valid_patient_username(username):
    patient = patients_collection.find_one({'username': username})
    return patient is not None

def get_prescriptions_for_user(username):
    # Access the MongoDB collection specific to the user
    prescriptions_collection = db[f'prescriptions_{username}']
    
    # Retrieve all prescriptions for the user
    prescriptions = prescriptions_collection.find()
    prescriptions_list = []
    
    for prescription in prescriptions:
        prescriptions_list.append({
            'prescription_id': str(prescription['_id']),
            'username': prescription.get('username', ''),
            'doctor_name': prescription.get('doctor_name', ''),
            'patient_name': prescription.get('patient_name', ''),
            'patient_age': prescription.get('patient_age', ''),
            'hospital_name': prescription.get('hospital_name', ''),
            'medication_name': prescription.get('medication_name', ''),
            'dosage': prescription.get('dosage', ''),
            'timing': prescription.get('timing', ''),
            'remarks': prescription.get('remarks', ''),
            'note': prescription.get('note', ''),
            'created_at': prescription.get('created_at', '')  # Add created_at if it exists
        })
    
    return prescriptions_list
# Create prescription
def create_prescription(username, hospital_name, medication_name, dosage, before_food, after_food, morning, afternoon, evening, remarks, note):
    # Create or access the collection specific to the user
    prescriptions_collection = db[f'prescriptions_{username}']

    # Prepare the prescription data
    prescription = {
        'hospital_name': hospital_name,
        'medication_name': medication_name,
        'dosage': dosage,
        'before_food': before_food,
        'after_food': after_food,
        'morning': morning,
        'afternoon': afternoon,
        'evening': evening,
        'remarks': remarks,
        'note': note,
        'created_at': datetime.now()  # Optional: add a timestamp for when the prescription was added
    }

    # Insert the prescription data into the user-specific collection
    result = prescriptions_collection.insert_one(prescription)
    
    # Check if the insertion was successful
    if result.acknowledged:
        print(f'Prescription added for {username} with id: {result.inserted_id}')
    else:
        print('Failed to add prescription')

        
def upload_report_for_doctor(username, report_file, filename):
    """ Function to upload a report to the database for a patient, uploaded by a doctor.

    Args:
        username (str): The username of the patient.
        report_file (FileStorage): The uploaded report file.
        filename (str): The name of the file.
    
    Returns:
        report_id (str): The ID of the uploaded report in GridFS.
    """
    # Upload the file to GridFS
    report_id = fs.put(report_file, filename=filename)
    
    # Create metadata entry for the report
    report_data = {
        'username': username,
        'report_id': report_id,
        'filename': filename,
        'uploader_role': 'doctor',  # Marking the uploader as 'doctor'
        'upload_date': datetime.utcnow()
    }
    
    # Insert the metadata into the reports collection for the user
    reports_collection = db[f'reports_{username}']
    reports_collection.insert_one(report_data)
    
    return report_id



def save_contact(name, email, message):
    """Function to save contact form data into the MongoDB database."""
    
    contact_data = {
        'name': name,
        'email': email,
        'message': message,
        'submitted_at': datetime.datetime.now()
    }

    # Insert contact data into the contacts collection
    contacts_collection.insert_one(contact_data)
    return True
        
def get_report_from_gridfs(file_id):
    """Retrieve a report from GridFS by its ID."""
    try:
        print(f"Attempting to retrieve report with ID: {file_id}")
        report = fs.get(ObjectId(file_id))
        return report
    except Exception as e:
        print(f"Error retrieving report with ID {file_id}: {e}")
        return None
def serve_report_as_pdf(file_id):
    """Serve the report as a PDF file."""
    report = get_report_from_gridfs(file_id)
    if report:
        try:
            # Create an in-memory byte stream for the file
            file_stream = io.BytesIO(report.read())
            
            # Serve the file as a PDF
            return send_file(
                file_stream,
                mimetype='application/pdf',
                download_name='report.pdf',  # For Flask 2.0 and later
                as_attachment=False
            )
        except Exception as e:
            # Log or print exception details for debugging
            print(f"Error serving report: {e}")
            abort(500)  # Internal Server Error if file serving fails
    else:
        abort(404)  # File not found
# Assuming MongoDB is already connected in models.py as db
def get_all_users():
    # Ensure you have a working MongoDB connection
    patients_collection = db['patients']
    
    # Query MongoDB to get all patient username and name fields
    users = patients_collection.find({}, {'_id': 0, 'username': 1, 'name': 1})
    
    # Convert to a dictionary where username is the key and name is the value
    users_dict = {user['username']: user['name'] for user in users}
    
    return users_dict  # Return dictionary of users to the caller

def get_reports_for_doctor(username):
    """Retrieve all reports for a specific doctor/patient."""
    # Adjust to fetch report data including file_id
    collection_name = f"reports_{username}"
    reports_collection = db[collection_name]
    reports = reports_collection.find({}, {'_id': 0, 'file_id': 1, 'filename': 1, 'report_id': 1})
    return list(reports)  # Convert to a list of reports

def list_reports_for_patient(username):
    """Retrieve all reports for a specific patient."""
    collection_name = f"reports_{username}"
    reports_collection = db[collection_name]
    reports = reports_collection.find({}, {'_id': 0, 'file_id': 1, 'filename': 1, 'report_id': 1})
    return list(reports)  # Convert to a list of reports

def get_patient_report_from_gridfs(file_id):
    """Retrieve a report from GridFS by its ID."""
    try:
        print(f"Attempting to retrieve report with ID: {file_id}")
        report = fs.get(ObjectId(file_id))
        return report
    except Exception as e:
        print(f"Error retrieving report with ID {file_id}: {e}")
        return None
