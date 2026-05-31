import os
import json
import time
import logging
import smtplib
import datetime
import dateparser
import os.path
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from langchain.tools import tool
from langchain_community.utilities import GoogleSerperAPIWrapper
from tenacity import retry, stop_after_attempt, wait_exponential
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.oauth2 import service_account

from database import update_candidate_status
from rag_pipeline import rag_pipeline

logger = logging.getLogger(__name__)

# Setup Serper for scraping social media / job boards
os.environ["SERPER_API_KEY"] = os.getenv("SERPER_API_KEY", "")
search = GoogleSerperAPIWrapper()

# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/calendar.events']

@tool
def scrape_candidate_data(query: str) -> str:
    """
    Useful for the SourcingBot to scrape passive candidates. 
    Performs a deep X-Ray search across LinkedIn, Naukri, Indeed, and GitHub simultaneously.
    """
    logger.info(f"🔍 [SOURCING ENGINE] Executing multi-platform X-Ray search for: {query}")
    
    try:
        # The magical Boolean string that searches all major portals at once legally
        xray_string = (
            "(site:linkedin.com/in/ OR "
            "site:naukri.com/naukri-user/ OR "
            "site:indeed.com/r/ OR "
            "site:github.com)"
        )
        
        # We append the AI's query (e.g., "Senior Python Developer") to the X-Ray string
        full_query = f"{xray_string} {query}"
        
        return search.run(full_query)
        
    except Exception as e:
        logger.error(f"❌ [SOURCING ENGINE] Scrape failed: {str(e)}")
        return f"Self-Healing: Scrape failed. Fallback triggered. Error: {str(e)}"

@tool
def enrich_candidate_email(first_name: str, last_name: str, company_domain: str) -> str:
    """
    Takes a candidate's name and their company's website domain and returns their professional email address.
    Use this AFTER scraping their profile, but BEFORE sending an email.
    """
    api_key = os.getenv("HUNTER_API_KEY")
    if not api_key:
        return "ERROR: Hunter API key not configured."

    url = f"https://api.hunter.io/v2/email-finder?domain={company_domain}&first_name={first_name}&last_name={last_name}&api_key={api_key}"
    
    try:
        response = requests.get(url)
        data = response.json()
        
        if data.get("data") and data["data"].get("email"):
            email = data["data"]["email"]
            return f"SUCCESS: Found email address: {email}"
        else:
            return "FAILURE: Could not find an email for this candidate."
    except Exception as e:
        return f"ERROR during enrichment: {str(e)}"

@tool
def mcp_schedule_interview(candidate_email: str, time_slot: str) -> str:
    """
    Interacts with Google Calendar API to schedule real interviews and generate Meet links.
    """
    logger.info(f"📅 [CALENDAR ENGINE] Agent requested interview at {time_slot} for {candidate_email}")
    
    # 1. AI Natural Language Time Parsing
    parsed_time = dateparser.parse(time_slot)
    if not parsed_time:
        return f"CRITICAL ERROR: Could not parse the requested time format: {time_slot}. Please try a different format."
    
    # Assume the interview is 1 hour long
    start_time = parsed_time.isoformat()
    end_time = (parsed_time + datetime.timedelta(hours=1)).isoformat()

    # 2. Google Authentication Handshake via Service Account
    sa_path = "credentials.json" 
    
    if os.path.exists(sa_path):
        try:
            creds = service_account.Credentials.from_service_account_file(
                sa_path, scopes=SCOPES
            )
        except Exception as auth_err:
            return f"CRITICAL ERROR: Failed to parse Service Account file: {str(auth_err)}"
    else:
        return "CRITICAL ERROR: Google Service Account credential file missing."

    # 3. Execute Calendar Injection
    try:
        service = build('calendar', 'v3', credentials=creds)
        
        event_body = {
            'summary': 'Technical Interview (AI Scheduled)',
            'description': 'This interview was automatically scheduled by the Autonomous Talent Engine.',
            'start': {
                'dateTime': start_time,
                'timeZone': 'Asia/Kolkata', 
            },
            'end': {
                'dateTime': end_time,
                'timeZone': 'Asia/Kolkata',
            },
            'attendees': [
                {'email': candidate_email},
            ],
            'conferenceData': {
                'createRequest': {
                    'requestId': f"interview_{int(datetime.datetime.now().timestamp())}",
                    'conferenceSolutionKey': {'type': 'hangoutsMeet'}
                }
            }
        }

        logger.info("📡 [CALENDAR ENGINE] Transmitting event payload to Google servers...")
        event = service.events().insert(calendarId='primary', body=event_body, conferenceDataVersion=1).execute()
        
        meet_link = event.get('hangoutLink', 'No Meet link generated')
        calendar_link = event.get('htmlLink')
        
        logger.info(f"✅ [CALENDAR ENGINE] Success! Event created: {calendar_link}")
        
        return f"SUCCESS! Interview scheduled from {start_time} to {end_time}. Google Meet Link: {meet_link}"

    except Exception as e:
        logger.error(f"❌ [CALENDAR ENGINE] API Failure: {str(e)}")
        return f"CRITICAL ERROR: Failed to schedule calendar event due to API error: {str(e)}"

@tool
def query_company_policies(question: str) -> str:
    """Uses RAG to answer candidate questions about company culture or salary bands."""
    docs = rag_pipeline.vectorstore.similarity_search(question, k=3)
    return "\n".join([d.page_content for d in docs])

@tool
def update_ats_database(name: str, status: str, expected_salary: float, role: str) -> str:
    """Updates the PostgreSQL database. Use status: 'Selected' or 'Rejected'."""
    data = {"expected_salary": expected_salary, "role": role}
    return update_candidate_status(name, status, data)

@tool
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1.5, min=2, max=10))
def send_email_notification(candidate_email: str, subject: str, body: str) -> str:
    """
    Sends authentic, real-time emails to candidates via SMTP server routing.
    Self-Healing: Automatically handles handshake drops or network timeouts with retries.
    """
    smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    sender_email = os.getenv("SENDER_EMAIL")
    sender_password = os.getenv("SENDER_PASSWORD")

    if not sender_email or not sender_password:
        return "CRITICAL ERROR: Email dispatch aborted. Sender credentials missing in environment configurations."

    logger.info(f"⚡ [EMAIL ENGINE] Establishing secure link to {smtp_server}:{smtp_port}...")

    try:
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = candidate_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        server = smtplib.SMTP(smtp_server, smtp_port)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(sender_email, sender_password)
        
        logger.info(f"📤 [EMAIL ENGINE] Transmitting payload packet to real destination: {candidate_email}...")
        server.sendmail(sender_email, candidate_email, msg.as_string())
        server.quit()
        
        logger.info(f"✅ [EMAIL ENGINE] Email cleanly delivered to: {candidate_email}")
        return f"Real-time dispatch successful! Payload cleanly processed and routed to {candidate_email}."

    except Exception as e:
        logger.error(f"❌ [EMAIL ENGINE] Critical transmission failure occurred: {str(e)}")
        raise e

@tool
def mock_greenhouse_ats(candidate_email: str, action: str, stage: str, notes: str = "") -> str:
    """
    DUMMY ATS INTEGRATION: Simulates pushing data to Greenhouse ATS.
    Actions allowed: 'update_stage', 'add_note', 'create_offer'.
    Stages: 'Application Review', 'Interviewing', 'Offer', 'Rejected', 'Hired'.
    """
    logger.info(f"Initiating dummy ATS sync for {candidate_email}...")
    time.sleep(1.5)
    
    db_status_map = {
        "Application Review": "Pending",
        "Interviewing": "Interviewing",
        "Offer": "Selected",
        "Hired": "Selected",
        "Rejected": "Rejected"
    }
    
    local_db_status = db_status_map.get(stage, "Pending")
    
    try:
        candidate_name = candidate_email.split('@')[0].replace('.', ' ').title()
        update_candidate_status(candidate_name, local_db_status)
        
        simulated_response = {
            "status": 200,
            "message": "Success",
            "data": {
                "candidate": candidate_email,
                "ats_id": f"gh_{int(time.time())}",
                "action_taken": action,
                "current_stage": stage,
                "system_notes": notes
            }
        }
        
        return f"Dummy ATS Update Successful: {simulated_response}"
        
    except Exception as e:
        return f"Dummy ATS Error: {str(e)}"

# Export list for the orchestrator
tools_list = [
    scrape_candidate_data, 
    enrich_candidate_email, 
    mcp_schedule_interview, 
    query_company_policies, 
    update_ats_database,
    send_email_notification,
    mock_greenhouse_ats
]
