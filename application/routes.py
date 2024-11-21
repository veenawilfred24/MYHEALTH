import os
import logging
import chardet
import textwrap
import fitz  # PyMuPDF
from groq import Groq
from flask import Flask, request, jsonify, render_template, redirect, url_for, session, flash, send_file, abort
from application import app
from application.models import (create_patient, create_doctor, verify_patient, verify_doctor,  get_reports_for_patient,list_reports_for_patient, get_patient_report_from_gridfs, upload_report, download_report, summarize_report,get_prescriptions_for_user,create_prescription,is_valid_patient_username,upload_report_for_doctor,save_contact,get_reports_for_doctor,serve_report_as_pdf,get_all_users)
from application.forms import (PatientLoginForm, PatientSignupForm, DoctorLoginForm, DoctorSignupForm, AddPrescriptionForm, SelectUserForm)
from gridfs import GridFS
from bson.objectid import ObjectId
from datetime import datetime
from werkzeug.utils import secure_filename
from bs4 import BeautifulSoup
import requests
import os
from config import Config 
import io 

app.config.from_object(Config)

client = Config.client


# Helper functions for PDF text extraction and summarization
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

def summarize_content_in_chunks(text, chunk_size=2000, model="llama-3.1-70b-versatile"):
    logging.info(f"Starting summarization for text of length {len(text)}")
    chunks = textwrap.wrap(text, chunk_size)
    summaries = []

    for chunk in chunks:
        try:
            logging.info(f"Processing chunk of size: {len(chunk)}")
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
    return " ".join(summaries)

def scrape_health_articles(query):
    search_url = f"https://pubmed.ncbi.nlm.nih.gov/?term={query.replace(' ', '+')}"
    response = requests.get(search_url)
    soup = BeautifulSoup(response.text, 'html.parser')
    articles = []

    for link in soup.find_all('a', class_='docsum-title'):
        article_url = f"https://pubmed.ncbi.nlm.nih.gov{link.get('href')}"
        articles.append(article_url)

    return articles

def generate_prompt(query, articles, context):
    prompt = (
        f"You are a health-related chatbot. Your role is to provide relevant information and insights based on scientific articles."
        f"\n\nInstructions:"
        f"\n1. When a user asks a question, you should use the provided articles to generate a detailed and informative response."
        f"\n2. Include relevant details from the articles to support your response."
        f"\n3. If the user query is not clear or doesn't match the content of the articles, ask for clarification."
        f"\n4. Be concise, informative, and professional."
        f"\n\nUser Query: {query}"
        f"\n\nArticles:"
        f"\n{context}"
        f"\n\nGenerate a response based on the above instructions."
    )
    return prompt
@app.route('/chat', methods=['POST'])
def chat():
    data = request.get_json()
    user_query = data.get('query', '')

    if not user_query:
        return jsonify({'response': 'No query provided', 'articles': []})

    # Scrape PubMed for relevant articles
    articles = scrape_health_articles(user_query)
    
    # Prepare context and prompt for the LLM
    context = "\n".join(articles)
    prompt = generate_prompt(user_query, articles, context)

    try:
        # Generate a response using the Groq API
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.1-70b-versatile"
        )
        response_text = chat_completion.choices[0].message.content
    except Exception as e:
        response_text = f"Error querying the Groq API: {e}"

    return jsonify({'response': response_text, 'articles': articles})

@app.route('/')
def landing():
    return render_template('index.html')

"""@app.route('/home')
def home():
    if 'username' not in session:
        return redirect(url_for('patient_login'))  # Redirect to login if not authenticated
    return render_template('home.html')"""

@app.route('/reports')
def reports():
    if 'username' not in session:
        return redirect(url_for('patient_login'))
    return render_template('manage_reports.html')

@app.route('/manage_reports', methods=['GET', 'POST'])
def manage_reports():
    if 'user_role' not in session or session['user_role'] != 'patient':
        return redirect(url_for('patient_login'))

    reports = get_reports_for_patient(session['username'])
    summary = None

    if request.method == 'POST':
        if 'report_file' in request.files:
            report_file = request.files['report_file']
            filename = secure_filename(report_file.filename)
            upload_report(session['username'], report_file, filename)
            return redirect(url_for('manage_reports'))

        if 'file_id' in request.form:
            file_id = request.form['file_id']
            try:
                # Print file_id for debugging purposes
                logging.info(f"Received file_id: {file_id}")
                summary = summarize_report(session['username'], file_id)
                if summary:
                    logging.info(f"Summary generated: {summary}")
                else:
                    logging.error("Failed to generate summary.")
            except Exception as e:
                logging.error(f"Error in summarize_report: {e}")

    return render_template('manage_reports.html', reports=reports, summary=summary)



@app.route('/upload_report', methods=['POST'])
def upload_report_route():
    if 'username' not in session or session['user_role'] != 'patient':
        return redirect(url_for('patient_login'))
    
    file = request.files.get('file')
    if file and file.filename != '':
        filename = secure_filename(file.filename)
        report_id = upload_report(session['username'], file, filename)

        # Immediately trigger summarization after upload
        summary = summarize_report(session['username'], report_id)
        if summary:
            flash(f"File uploaded and summarized successfully with report ID: {report_id}", "success")
        else:
            flash("File uploaded but summarization failed.", "error")
        
        return redirect(url_for('view_reports_route'))

    flash("Failed to upload file.", "error")
    return redirect(url_for('manage_reports'))

@app.route('/download_report/<report_id>')
def download_report_route(report_id):
    if 'username' not in session or session['user_role'] != 'patient':
        return redirect(url_for('patient_login'))

    try:
        file = download_report(report_id)
        return send_file(file, as_attachment=True, download_name=file.filename)
    except ValueError as e:
        flash(str(e), 'error')
        return redirect(url_for('manage_reports'))

@app.route('/summarize_report', methods=['POST'])
def summarize_report_route():
    if 'user_role' not in session or session['user_role'] != 'patient':
        return redirect(url_for('patient_login'))

    report_id = request.form.get('file_id')
    if not report_id:
        flash("Report ID is required.", "error")
        return redirect(url_for('manage_reports'))
    
    summary = summarize_report(session['username'], report_id)
    return render_template('manage_reports.html', summary=summary)



@app.route('/view_prescription/<username>')
def view_prescription(username):
    # Call the function to get prescriptions from the model
    prescriptions = get_prescriptions_for_user(username)
    
    # Render the template with the list of prescriptions
    return render_template('view_prescription.html', prescriptions=prescriptions, username=username)


@app.route('/family_health')
def family_health():
    if 'username' not in session:
        return redirect(url_for('patient_login'))
    return render_template('family_health.html')

@app.route('/book_appointments')
def book_appointments():
    if 'username' not in session:
        return redirect(url_for('patient_login'))
    return render_template('book_appointments.html')

@app.route('/article')
def article():
    return render_template('article.html')


@app.route('/doctor_signup', methods=['GET', 'POST'])
def doctor_signup():
    form = DoctorSignupForm()
    if form.validate_on_submit():
        create_doctor(
            d_username=form.d_username.data,
            email=form.email.data,
            name=form.name.data,
            mobile_no=form.mobile_no.data,
            license_no=form.license_no.data,
            hospital_name=form.hospital_name.data,
            password=form.password.data
        )
        return redirect(url_for('doctor_login'))
    return render_template('doctor_signup.html', form=form)

@app.route('/doctor_login', methods=['GET', 'POST'])
def doctor_login():
    form = DoctorLoginForm()
    if form.validate_on_submit():
        doctor = verify_doctor(d_username=form.d_username.data, password=form.password.data)
        if doctor:
            session['d_username'] = doctor['d_username']
            session['user_role'] = 'doctor'
            return redirect(url_for('doctor_dashboard'))
        else:
            flash('Invalid username or password.', 'error')
    return render_template('doctor_login.html', form=form)

@app.route('/patient_signup', methods=['GET', 'POST'])
def patient_signup():
    form = PatientSignupForm()
    if form.validate_on_submit():
        create_patient(
            username=form.username.data,
            email=form.email.data,
            name=form.name.data,
            mobile_no=form.mobile_no.data,
            password=form.password.data
        )
        return redirect(url_for('patient_login'))
    return render_template('patient_signup.html', form=form)

@app.route('/patient_login', methods=['GET', 'POST'])
def patient_login():
    form = PatientLoginForm()
    if form.validate_on_submit():
        patient = verify_patient(username=form.username.data, password=form.password.data)
        if patient:
            session['username'] = patient['username']
            session['user_role'] = 'patient'
            return redirect(url_for('patient_dashboard', username=session['username']))
        else:
            flash('Invalid username or password.', 'error')
    return render_template('patient_login.html', form=form)

@app.route('/view_reports', methods=['GET', 'POST'])
def view_reports_route():
    if 'username' not in session or session['user_role'] != 'patient':
        return redirect(url_for('patient_login'))

    # Fetch all reports for the logged-in patient
    reports = get_reports_for_patient(session['username'])

    summary = None
    if request.method == 'POST':
        # Handle report summarization
        report_id = request.form.get('report_id')
        logging.info(f"Received request to summarize report ID: {report_id}")
        summary = summarize_report(session['username'], report_id)  # Ensure order of parameters
        if summary:
            logging.info(f"Generated summary: {summary}")
        else:
            logging.error("Summarization failed.")

    return render_template('view_reports.html', reports=reports, summary=summary)

@app.route('/patient_dashboard/<username>')
def patient_dashboard(username):
    if 'username' not in session or session['user_role'] != 'patient':
        return redirect(url_for('patient_login'))
    return render_template('patient_dashboard.html',username=session['username'])

@app.route('/doctor_dashboard')
def doctor_dashboard():
    if 'd_username' not in session or session['user_role'] != 'doctor':
        return redirect(url_for('doctor_login'))
    return render_template('doctor_dashboard.html')

@app.route('/logout')
def logout():
    # Clear the session
    user_type = session.get('user_type', None)
    session.clear()

    # Redirect based on the user type
    if user_type == 'doctor':
        return redirect(url_for('doctor_login'))
    elif user_type == 'patient':
        return redirect(url_for('patient_login'))
    else:
        # If somehow no user type is set, redirect to a generic login page or home page
        return redirect(url_for('index'))


@app.route('/select_user', methods=['GET', 'POST'])
def select_user():
    form = SelectUserForm()
    username = None  # Initialize username variable
    if form.validate_on_submit():
        username = form.username.data  # Get the entered username
    return render_template('select_user.html', form=form, username=username)


@app.route('/add_prescription/<username>', methods=['GET', 'POST'])
def add_prescription(username):
    form = AddPrescriptionForm()
    if form.validate_on_submit():
        create_prescription(
            username=username,
            hospital_name=form.hospital_name.data,
            medication_name=form.medication_name.data,
            dosage=form.dosage.data,
            before_food=form.before_food.data,
            after_food=form.after_food.data,
            morning=form.morning.data,
            afternoon=form.afternoon.data,
            evening=form.evening.data,
            remarks=form.remarks.data,
            note=form.note.data
        )
        flash('Prescription added successfully!', 'success')
        return redirect(url_for('doctor_dashboard'))
    return render_template('add_prescription.html', form=form, username=username)

@app.route('/success')
def success():
    return "Prescription added successfully!"

@app.route('/prescriptions', methods=['GET'])
def prescriptions():
    username = request.args.get('username')
    if not username:
        flash('Username not provided!', 'danger')
        return redirect(url_for('select_user'))

    prescriptions_list = list(prescriptions_collection.find({"username": username}))
    return render_template('prescriptions.html', prescriptions=prescriptions_list, username=username)

@app.route('/select_user_for_report', methods=['GET', 'POST'])
def select_user_for_report():
    form = SelectUserForm()
    username = None  # Initialize username variable
    if form.validate_on_submit():
        username = form.username.data  # Get the entered username
    return render_template('select_user_for_report.html', form=form, username=username)



@app.route('/doctor_upload_report/<username>', methods=['GET', 'POST'])
def doctor_upload_report(username):
    if request.method == 'POST':
        if 'report_file' not in request.files:
            flash('No file part')
            return redirect(request.url)
        
        report_file = request.files['report_file']
        
        if report_file.filename == '':
            flash('No selected file')
            return redirect(request.url)
        
        if report_file:
            # Use the updated function specifically for doctor uploads
            report_id = upload_report_for_doctor(username, report_file, report_file.filename)
            
            flash(f'Report uploaded successfully for {username} by the doctor.')
            return redirect(url_for('doctor_dashboard'))
    
    return render_template('doctor_upload_reports.html', username=username)

@app.route('/submit_contact', methods=['POST'])
def submit_contact():
    name = request.form.get('name')
    email = request.form.get('email')
    message = request.form.get('message')

    # Validate form fields
    if not name or not email or not message:
        flash('All fields are required!', 'error')
        return redirect(url_for('landing'))

    # Call the save_contact function from models.py
    save_contact(name, email, message)
    
    flash('Your message has been sent!', 'success')
    return redirect(url_for('landing'))

@app.route('/doctor/view_report_doc', methods=['GET', 'POST'])
def view_report_doc():
    if request.method == 'POST':
        username = request.form.get('username')  # Form submission
        return redirect(url_for('manage_patient_records', username=username))
    
    # Render the user selection form
    users = get_all_users()  # Function to retrieve all patients
    return render_template('view_report_doc.html', users=users)
@app.route('/doctor/manage_records/<username>', methods=['GET'])
def manage_patient_records(username):
    reports = get_reports_for_doctor(username)  # Retrieves all reports for the selected patient
    return render_template('doctor_view_reports.html', reports=reports, username=username)
@app.route('/doctor/view_report/<file_id>', methods=['GET'])
def view_report(file_id):
    return serve_report_as_pdf(file_id)
@app.route('/test_report/<file_id>', methods=['GET'])
def test_report(file_id):
    return serve_report_as_pdf(file_id)


@app.route('/patient/view_reports', methods=['GET'])
def view_patient_reports():
    """Render the page for viewing patient's reports."""
    username = session.get('username')  # Get the username from session
    if not username:
        return redirect(url_for('login'))  # Redirect to login if no user is found
    
    reports = list_reports_for_patient(username)
    return render_template('view_patient_reports.html', reports=reports)

@app.route('/patient/view_report/<file_id>', methods=['GET'])
def view_patient_report(file_id):
    """Serve the report as a PDF file."""
    report = get_patient_report_from_gridfs(file_id)
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



