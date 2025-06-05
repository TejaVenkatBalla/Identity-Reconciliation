from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import sqlite3
from datetime import datetime
import os
from contextlib import contextmanager

app = FastAPI(title="Bitespeed Identity Reconciliation Service")

# Database setup
DATABASE_URL = "contacts.db"

def init_database():
    """Initialize the database with the Contact table"""
    conn = sqlite3.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Contact (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phoneNumber TEXT,
            email TEXT,
            linkedId INTEGER,
            linkPrecedence TEXT CHECK(linkPrecedence IN ('primary', 'secondary')),
            createdAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            deletedAt TIMESTAMP,
            FOREIGN KEY (linkedId) REFERENCES Contact (id)
        )
    ''')
    
    conn.commit()
    conn.close()

@contextmanager
def get_db_connection():
    """Context manager for database connections"""
    conn = sqlite3.connect(DATABASE_URL)
    conn.row_factory = sqlite3.Row  # Enable accessing columns by name
    try:
        yield conn
    finally:
        conn.close()

# Pydantic models
class IdentifyRequest(BaseModel):
    email: Optional[str] = None
    phoneNumber: Optional[str] = None

class ContactResponse(BaseModel):
    primaryContatctId: int  # Note: keeping the typo as per requirements
    emails: List[str]
    phoneNumbers: List[str]
    secondaryContactIds: List[int]

class IdentifyResponse(BaseModel):
    contact: ContactResponse

def get_contacts_by_email_or_phone(email: Optional[str], phone_number: Optional[str]) -> List[dict]:
    """Get all contacts that match the given email or phone number"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        query = '''
            SELECT * FROM Contact 
            WHERE deletedAt IS NULL 
            AND (email = ? OR phoneNumber = ?)
            ORDER BY createdAt ASC
        '''
        
        cursor.execute(query, (email, phone_number))
        return [dict(row) for row in cursor.fetchall()]

def get_all_linked_contacts(primary_id: int) -> List[dict]:
    """Get all contacts linked to a primary contact"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Get the primary contact and all secondary contacts
        query = '''
            SELECT * FROM Contact 
            WHERE deletedAt IS NULL 
            AND (id = ? OR linkedId = ?)
            ORDER BY createdAt ASC
        '''
        
        cursor.execute(query, (primary_id, primary_id))
        return [dict(row) for row in cursor.fetchall()]

def find_primary_contact_id(contacts: List[dict]) -> int:
    """Find the primary contact ID from a list of contacts"""
    # Look for existing primary contact
    for contact in contacts:
        if contact['linkPrecedence'] == 'primary':
            return contact['id']
    
    # If no primary found, return the oldest contact's ID
    return min(contacts, key=lambda x: x['createdAt'])['id']

def create_contact(email: Optional[str], phone_number: Optional[str], 
                  linked_id: Optional[int] = None, 
                  link_precedence: str = 'primary') -> int:
    """Create a new contact and return its ID"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        query = '''
            INSERT INTO Contact (phoneNumber, email, linkedId, linkPrecedence, createdAt, updatedAt)
            VALUES (?, ?, ?, ?, ?, ?)
        '''
        
        now = datetime.now()
        cursor.execute(query, (phone_number, email, linked_id, link_precedence, now, now))
        conn.commit()
        
        return cursor.lastrowid

def update_contact_to_secondary(contact_id: int, primary_id: int):
    """Update a contact to be secondary to another primary contact"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        query = '''
            UPDATE Contact 
            SET linkedId = ?, linkPrecedence = 'secondary', updatedAt = ?
            WHERE id = ?
        '''
        
        cursor.execute(query, (primary_id, datetime.now(), contact_id))
        conn.commit()

def consolidate_contacts(primary_id: int) -> ContactResponse:
    """Get consolidated contact information"""
    all_contacts = get_all_linked_contacts(primary_id)
    
    # Separate primary and secondary contacts
    primary_contact = None
    secondary_contacts = []
    
    for contact in all_contacts:
        if contact['id'] == primary_id:
            primary_contact = contact
        else:
            secondary_contacts.append(contact)
    
    # Collect all unique emails and phone numbers
    emails = []
    phone_numbers = []
    
    # Add primary contact info first
    if primary_contact:
        if primary_contact['email'] and primary_contact['email'] not in emails:
            emails.append(primary_contact['email'])
        if primary_contact['phoneNumber'] and primary_contact['phoneNumber'] not in phone_numbers:
            phone_numbers.append(primary_contact['phoneNumber'])
    
    # Add secondary contact info
    for contact in secondary_contacts:
        if contact['email'] and contact['email'] not in emails:
            emails.append(contact['email'])
        if contact['phoneNumber'] and contact['phoneNumber'] not in phone_numbers:
            phone_numbers.append(contact['phoneNumber'])
    
    return ContactResponse(
        primaryContatctId=primary_id,
        emails=emails,
        phoneNumbers=phone_numbers,
        secondaryContactIds=[c['id'] for c in secondary_contacts]
    )

@app.post("/identify", response_model=IdentifyResponse)
async def identify(request: IdentifyRequest):
    """
    Identify and consolidate customer contacts based on email and phone number
    """
    if not request.email and not request.phoneNumber:
        raise HTTPException(status_code=400, detail="Either email or phoneNumber must be provided")
    
    # Find existing contacts with matching email or phone
    existing_contacts = get_contacts_by_email_or_phone(request.email, request.phoneNumber)
    
    if not existing_contacts:
        # No existing contacts, create a new primary contact
        new_contact_id = create_contact(request.email, request.phoneNumber)
        contact_response = consolidate_contacts(new_contact_id)
        return IdentifyResponse(contact=contact_response)
    
    # Check if we have an exact match (same email AND phone)
    exact_match = None
    for contact in existing_contacts:
        if (contact['email'] == request.email and contact['phoneNumber'] == request.phoneNumber):
            exact_match = contact
            break
    
    if exact_match:
        # Exact match found, return consolidated info
        primary_id = exact_match['linkedId'] if exact_match['linkedId'] else exact_match['id']
        contact_response = consolidate_contacts(primary_id)
        return IdentifyResponse(contact=contact_response)
    
    # Get all contacts that are linked to any of the existing contacts
    all_related_contacts = set()
    primary_ids = set()
    
    for contact in existing_contacts:
        if contact['linkPrecedence'] == 'primary':
            primary_ids.add(contact['id'])
            related = get_all_linked_contacts(contact['id'])
        else:
            primary_ids.add(contact['linkedId'])
            related = get_all_linked_contacts(contact['linkedId'])
        
        for rel_contact in related:
            all_related_contacts.add(rel_contact['id'])
    
    # If we have multiple primary contacts, we need to merge them
    if len(primary_ids) > 1:
        # Find the oldest primary contact
        primary_contacts = []
        with get_db_connection() as conn:
            cursor = conn.cursor()
            for pid in primary_ids:
                cursor.execute("SELECT * FROM Contact WHERE id = ?", (pid,))
                primary_contacts.append(dict(cursor.fetchone()))
        
        oldest_primary = min(primary_contacts, key=lambda x: x['createdAt'])
        
        # Update other primaries to be secondary
        for primary in primary_contacts:
            if primary['id'] != oldest_primary['id']:
                update_contact_to_secondary(primary['id'], oldest_primary['id'])
        
        primary_id = oldest_primary['id']
    else:
        primary_id = list(primary_ids)[0]
    
    # Check if we need to create a new secondary contact
    has_new_info = False
    
    # Get all existing info for this primary contact
    all_contacts = get_all_linked_contacts(primary_id)
    existing_emails = {c['email'] for c in all_contacts if c['email']}
    existing_phones = {c['phoneNumber'] for c in all_contacts if c['phoneNumber']}
    
    # Check if the request contains new information
    new_email = request.email and request.email not in existing_emails
    new_phone = request.phoneNumber and request.phoneNumber not in existing_phones
    
    if new_email or new_phone:
        # Create a new secondary contact with the new information
        create_contact(request.email, request.phoneNumber, primary_id, 'secondary')
    
    # Return consolidated contact information
    contact_response = consolidate_contacts(primary_id)
    return IdentifyResponse(contact=contact_response)

@app.get("/")
async def root():
    """Health check endpoint"""
    return {"message": "Bitespeed Identity Reconciliation Service is running"}

@app.get("/contacts")
async def get_all_contacts():
    """Debug endpoint to view all contacts"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM Contact WHERE deletedAt IS NULL ORDER BY createdAt ASC")
        contacts = [dict(row) for row in cursor.fetchall()]
    return {"contacts": contacts}

# Initialize the database when the app starts
@app.on_event("startup")
async def startup_event():
    init_database()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)