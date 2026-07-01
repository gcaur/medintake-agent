"""
MedIntake Agent — Multi-step AI agent for patient intake automation.

This agent demonstrates multi-step reasoning with tool use, built for
healthcare intake workflows. It reads patient messages, extracts key
information, checks availability, assesses urgency, and books appointments.

Architecture: Claude API (tool use) → FastAPI endpoint → local SQLite store
"""

import os
import json
import sqlite3
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass, asdict
from enum import Enum

from anthropic import Anthropic
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

class UrgencyLevel(str, Enum):
    EMERGENCY = "emergency"      # Redirect to emergency services
    URGENT = "urgent"            # Same-day or next-day appointment
    ROUTINE = "routine"          # Standard booking window
    FOLLOW_UP = "follow_up"      # Existing patient follow-up


@dataclass
class PatientInfo:
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    symptoms: Optional[str] = None
    urgency: Optional[UrgencyLevel] = None
    preferred_date: Optional[str] = None
    notes: Optional[str] = None


@dataclass  
class Appointment:
    id: str
    patient_name: str
    datetime: str
    department: str
    urgency: str
    symptoms_summary: str
    doctor_name: str
    status: str = "confirmed"


# ---------------------------------------------------------------------------
# Tools (functions the agent can call)
# ---------------------------------------------------------------------------

class AgentTools:
    """Collection of tools the MedIntake agent can use.

    In production, these would connect to:
    - Practice management system (calendar)
    - Triage database (urgency scoring)
    - Booking system (appointment creation)
    - Notification service (Slack/email to doctors)
    """

    def __init__(self, db_path: str = "appointments.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize local SQLite store for demo purposes."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS appointments (
                    id TEXT PRIMARY KEY,
                    patient_name TEXT,
                    datetime TEXT,
                    department TEXT,
                    urgency TEXT,
                    symptoms_summary TEXT,
                    doctor_name TEXT,
                    status TEXT DEFAULT 'confirmed',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS availability (
                    slot_id TEXT PRIMARY KEY,
                    datetime TEXT UNIQUE,
                    doctor_name TEXT,
                    department TEXT,
                    is_available INTEGER DEFAULT 1
                )
            """)
            # Seed demo availability
            self._seed_availability(conn)

    def _seed_availability(self, conn: sqlite3.Connection):
        """Create realistic demo availability for the next 7 days."""
        cursor = conn.execute("SELECT COUNT(*) FROM availability")
        if cursor.fetchone()[0] > 0:
            return

        doctors = [
            ("Dr. Schmidt", "General Practice"),
            ("Dr. Weber", "Cardiology"),
            ("Dr. Mueller", "Dermatology"),
        ]

        base = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        slot_id = 0
        for day_offset in range(1, 8):  # Next 7 days
            for hour in [9, 10, 11, 14, 15, 16]:  # Working hours
                for doctor, dept in doctors:
                    dt = base + timedelta(days=day_offset, hours=hour)
                    conn.execute(
                        "INSERT OR IGNORE INTO availability (slot_id, datetime, doctor_name, department, is_available) VALUES (?, ?, ?, ?, 1)",
                        (f"slot_{slot_id}", dt.isoformat(), doctor, dept)
                    )
                    slot_id += 1

    def check_calendar(self, department: str = "General Practice", days_ahead: int = 7) -> str:
        """Check available appointment slots for a department."""
        cutoff = (datetime.now() + timedelta(days=days_ahead)).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT datetime, doctor_name FROM availability 
                   WHERE department = ? AND datetime < ? AND is_available = 1
                   ORDER BY datetime LIMIT 10""",
                (department, cutoff)
            ).fetchall()

        if not rows:
            return f"No available slots in {department} for the next {days_ahead} days."

        slots = [f"{r['doctor_name']}: {r['datetime'][:16]}" for r in rows]
        return f"Available slots in {department}:\n" + "\n".join(slots)

    def check_urgency(self, symptoms: str) -> str:
        """Assess urgency level based on symptoms described."""
        symptoms_lower = symptoms.lower()

        emergency_keywords = ["chest pain", "can't breathe", "unconscious", 
                              "severe bleeding", "heart attack", "stroke"]
        urgent_keywords = ["fever", "infection", "severe pain", "injury",
                           "allergic reaction", "swelling"]

        if any(k in symptoms_lower for k in emergency_keywords):
            return (f"URGENCY: EMERGENCY — Patient describes symptoms requiring "
                    f"immediate emergency care ({symptoms}). "
                    f"RECOMMENDATION: Direct to emergency services (144) immediately. "
                    f"Do NOT book a routine appointment.")

        if any(k in symptoms_lower for k in urgent_keywords):
            return (f"URGENCY: URGENT — Symptoms ({symptoms}) suggest need for "
                    f"same-day or next-day evaluation. Recommend scheduling "
                    f"within 24-48 hours.")

        return (f"URGENCY: ROUTINE — Symptoms ({symptoms}) appear non-urgent. "
                f"Standard booking window (within 1-2 weeks) is appropriate.")

    def book_appointment(self, patient_name: str, datetime_str: str, 
                         department: str, urgency: str, 
                         symptoms_summary: str) -> str:
        """Book an appointment and mark slot as unavailable."""
        import uuid
        appt_id = f"appt_{uuid.uuid4().hex[:8]}"

        # Assign doctor based on department
        dept_doctors = {
            "General Practice": "Dr. Schmidt",
            "Cardiology": "Dr. Weber",
            "Dermatology": "Dr. Mueller"
        }
        doctor = dept_doctors.get(department, "Dr. Schmidt")

        with sqlite3.connect(self.db_path) as conn:
            # Book appointment
            conn.execute(
                """INSERT INTO appointments (id, patient_name, datetime, department, 
                    urgency, symptoms_summary, doctor_name) 
                    VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (appt_id, patient_name, datetime_str, department, 
                 urgency, symptoms_summary, doctor)
            )
            # Mark slot unavailable
            conn.execute(
                "UPDATE availability SET is_available = 0 WHERE datetime = ? AND doctor_name = ?",
                (datetime_str, doctor)
            )

        return (f"APPOINTMENT CONFIRMED:\n"
                f"  ID: {appt_id}\n"
                f"  Patient: {patient_name}\n"
                f"  Date/Time: {datetime_str}\n"
                f"  Doctor: {doctor} ({department})\n"
                f"  Urgency: {urgency}\n"
                f"  Status: confirmed")

    def notify_doctor(self, appointment_id: str, notes: str = "") -> str:
        """Send notification to the assigned doctor."""
        # In production: sends Slack message / email via haelsi's internal comms
        # For demo: returns the notification payload
        return (f"NOTIFICATION SENT to doctor:\n"
                f"  Appointment: {appointment_id}\n"
                f"  Notes: {notes or "New patient intake — see appointment details"}\n"
                f"  Timestamp: {datetime.now().isoformat()}\n"
                f"  Channel: Slack #medical-alerts (production: real Slack API call)")


# ---------------------------------------------------------------------------
# The Agent
# ---------------------------------------------------------------------------

class MedIntakeAgent:
    """Multi-step AI agent for automated patient intake.

    Uses Claude's tool-use capabilities to orchestrate a workflow:
    1. Parse patient message → extract structured info
    2. Assess urgency → determine care pathway
    3. Check calendar → find available slots
    4. Book appointment → create confirmed booking
    5. Notify doctor → send alert to medical team

    This replaces the manual Make.com workflow that haelsi currently uses
    for patient intake routing across their 3 Vienna health centers.
    """

    SYSTEM_PROMPT = """You are MedIntake, an AI agent that handles patient 
intake for a healthcare provider with 3 health centers in Vienna.

Your job is to process incoming patient messages, assess their needs, 
and book appropriate appointments. You work step by step, using tools 
to complete each part of the workflow.

Rules:
- Always assess urgency FIRST before booking
- For EMERGENCY symptoms, direct to emergency services (144) — do NOT book
- For URGENT symptoms, prioritize same-day or next-day slots
- Collect patient name and contact info if not provided
- After booking, always notify the assigned doctor
- Respond in a warm, professional tone in the same language as the patient
- Default to German responses if the patient writes in German

Available departments: General Practice, Cardiology, Dermatology"""

    TOOLS_SCHEMA = [
        {
            "name": "check_urgency",
            "description": "Assess urgency level based on patient symptoms. Must be called BEFORE booking.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "symptoms": {"type": "string", "description": "Description of symptoms from patient message"}
                },
                "required": ["symptoms"]
            }
        },
        {
            "name": "check_calendar",
            "description": "Check available appointment slots for a department.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "department": {"type": "string", "description": "Department to check (General Practice, Cardiology, Dermatology)"},
                    "days_ahead": {"type": "integer", "description": "How many days ahead to check (default 7)"}
                },
                "required": ["department"]
            }
        },
        {
            "name": "book_appointment",
            "description": "Book a confirmed appointment. Only call after checking urgency and calendar.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "patient_name": {"type": "string"},
                    "datetime_str": {"type": "string", "description": "ISO datetime string for the appointment"},
                    "department": {"type": "string"},
                    "urgency": {"type": "string"},
                    "symptoms_summary": {"type": "string"}
                },
                "required": ["patient_name", "datetime_str", "department", "urgency", "symptoms_summary"]
            }
        },
        {
            "name": "notify_doctor",
            "description": "Send notification to the assigned doctor about a new appointment.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "appointment_id": {"type": "string"},
                    "notes": {"type": "string", "description": "Additional context for the doctor"}
                },
                "required": ["appointment_id"]
            }
        }
    ]

    def __init__(self, api_key: Optional[str] = None):
        self.client = Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))
        self.tools = AgentTools()
        self.conversation_history = []

    def process_intake(self, patient_message: str, thread_id: Optional[str] = None) -> dict:
        """Process a patient intake message end-to-end.

        This is the main entry point. It sends the message to Claude with
tool access, lets Claude decide which tools to call and in what order,
        and returns the final response to the patient.
        """
        messages = [{"role": "user", "content": patient_message}]

        # Get Claude's response with tool use
        response = self.client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=2000,
            system=self.SYSTEM_PROMPT,
            messages=messages,
            tools=self.TOOLS_SCHEMA
        )

        # Handle tool calls
        while response.stop_reason == "tool_use":
            tool_results = self._execute_tool_calls(response)
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

            response = self.client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=2000,
                system=self.SYSTEM_PROMPT,
                messages=messages,
                tools=self.TOOLS_SCHEMA
            )

        return {
            "response": response.content[0].text,
            "thread_id": thread_id or f"thread_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "timestamp": datetime.now().isoformat()
        }

    def _execute_tool_calls(self, response) -> list:
        """Execute all tool calls in a Claude response and return results."""
        results = []
        for block in response.content:
            if block.type == "tool_use":
                tool_name = block.name
                tool_input = block.input
                tool_id = block.id

                # Execute the tool
                result = self._call_tool(tool_name, tool_input)
                results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": result
                })
        return results

    def _call_tool(self, name: str, params: dict) -> str:
        """Route tool call to the appropriate method."""
        try:
            if name == "check_urgency":
                return self.tools.check_urgency(params["symptoms"])
            elif name == "check_calendar":
                return self.tools.check_calendar(
                    params.get("department", "General Practice"),
                    params.get("days_ahead", 7)
                )
            elif name == "book_appointment":
                return self.tools.book_appointment(**params)
            elif name == "notify_doctor":
                return self.tools.notify_doctor(**params)
            else:
                return f"Unknown tool: {name}"
        except Exception as e:
            return f"Tool error ({name}): {str(e)}"


# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------

app = FastAPI(title="MedIntake Agent", version="1.0.0")
agent = MedIntakeAgent()


class IntakeRequest(BaseModel):
    message: str
    thread_id: Optional[str] = None


@app.post("/intake")
async def handle_intake(request: IntakeRequest):
    """Process a patient intake message.

    Example request:
    {
        "message": "Hello, I have a fever and sore throat since yesterday. 
                    My name is Maria Schmidt. Can I get an appointment?"
    }
    """
    try:
        result = agent.process_intake(request.message, request.thread_id)
        return {"status": "success", **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    return {"status": "ok", "agent": "MedIntake v1.0.0"}


@app.get("/appointments")
async def list_appointments():
    """List all booked appointments (for demo/monitoring)."""
    with sqlite3.connect(agent.tools.db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM appointments ORDER BY created_at DESC LIMIT 50"
        ).fetchall()
    return {"appointments": [dict(r) for r in rows]}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
