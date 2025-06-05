# Bitespeed Identity Reconciliation Service

A FastAPI-based web service that identifies and consolidates customer contacts based on email addresses and phone numbers. This service helps FluxKart.com track customer identities across multiple purchases with different contact information.

## Features

- **Identity Reconciliation**: Links contacts with common email addresses or phone numbers
- **Primary/Secondary Linking**: Maintains a hierarchy with the oldest contact as primary
- **Automatic Merging**: Converts primary contacts to secondary when linking is detected
- **RESTful API**: Clean HTTP POST endpoint for identity operations

## API Endpoints

### POST `/identify`

Identifies and consolidates customer contact information.

**Request Body:**
```json
{
  "email": "example@domain.com",
  "phoneNumber": "1234567890"
}
```

**Response:**
```json
{
  "contact": {
    "primaryContatctId": 1,
    "emails": ["primary@example.com", "secondary@example.com"],
    "phoneNumbers": ["1234567890", "0987654321"],
    "secondaryContactIds": [2, 3]
  }
}
```

### GET `/`

Health check endpoint.

### GET `/contacts`

Debug endpoint to view all contacts in the database.

## Setup and Installation

### Local Development

1. **Clone the repository:**
   ```bash
   git clone <your-repo-url>
   cd bitespeed-identity-reconciliation
   ```

2. **Create a virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the application:**
   ```bash
   python main.py
   ```

The service will be available at `http://localhost:8000`

### Using Uvicorn directly

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## Database Schema

The service uses SQLite with the following Contact table structure:

```sql
CREATE TABLE Contact (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phoneNumber TEXT,
    email TEXT,
    linkedId INTEGER,
    linkPrecedence TEXT CHECK(linkPrecedence IN ('primary', 'secondary')),
    createdAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deletedAt TIMESTAMP,
    FOREIGN KEY (linkedId) REFERENCES Contact (id)
);
```

## Business Logic

### Contact Linking Rules

1. **New Contact**: If no existing contacts match the email or phone, create a new primary contact
2. **Exact Match**: If both email and phone match an existing contact, return consolidated information
3. **Partial Match**: If email OR phone matches, create a secondary contact with new information
4. **Primary Merging**: When two primary contacts need to be linked, the older one remains primary

### Example Scenarios

#### Scenario 1: New Customer
**Request:**
```json
{"email": "doc@hillvalley.edu", "phoneNumber": "555-0123"}
```

**Result:** Creates a new primary contact.

#### Scenario 2: Returning Customer with New Email
**Existing:** `{id: 1, email: "doc@hillvalley.edu", phone: "555-0123"}`
**Request:**
```json
{"email": "emmett@hillvalley.edu", "phoneNumber": "555-0123"}
```

**Result:** Creates secondary contact linked to primary contact 1.

#### Scenario 3: Merging Two Primary Contacts
**Existing:**
- `{id: 1, email: "doc@hillvalley.edu", phone: "555-0123", primary}`
- `{id: 2, email: "emmett@hillvalley.edu", phone: "555-9876", primary}`

**Request:**
```json
{"email": "doc@hillvalley.edu", "phoneNumber": "555-9876"}
```

**Result:** Contact 2 becomes secondary to contact 1, new secondary contact created.

## Testing

### Manual Testing with curl

```bash
# Test new contact creation
curl -X POST "http://localhost:8000/identify" \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "phoneNumber": "1234567890"}'

# Test contact linking
curl -X POST "http://localhost:8000/identify" \
  -H "Content-Type: application/json" \
  -d '{"email": "test2@example.com", "phoneNumber": "1234567890"}'

# View all contacts
curl "http://localhost:8000/contacts"
```


## API Documentation

Once running, visit `http://localhost:8000/docs` for interactive API documentation powered by Swagger UI.

## License

MIT License - feel free to use this code for your projects.

---

**Live Endpoint**: `https://backend-service-xjsc.onrender.com/`

For questions or issues, please create a GitHub issue or contact me at tejavenkatballa@gmail.com.