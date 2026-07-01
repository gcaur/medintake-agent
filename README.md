# MedIntake Agent

Multi-step AI agent for automated patient intake. Built with Claude API tool-use, FastAPI, and SQLite.

**Built in ~4 hours as a demo for haelsi's AI Automation Engineer role.**

> "We want less CV, more artifacts." — This is the artifact.

---

## What It Does

Replaces the manual patient intake workflow that healthcare providers run through Make.com or n8n:

```
Patient message (email/Slack)
    → Extract: name, symptoms, contact info
    → Assess: urgency level (emergency/urgent/routine)
    → Check: available slots by department
    → Book: confirmed appointment
    → Notify: assigned doctor via Slack/email
    → Respond: patient gets confirmation + instructions
```

All orchestrated by Claude with function calling — the agent decides which tools to call and in what order.

---

## Architecture

```
                    Patient Message
                          |
                    [FastAPI]
                          |
              +-----------+-----------+
              |                       |
        [Claude API]           [SQLite Store]
        (tool use)              (appointments)
              |
    +---------+---------+---------+---------+
    |         |         |         |         |
urgency   calendar   booking   notify   patient
 check     lookup   creation   doctor   response
```

**Key design decisions:**
- **Claude Haiku** for cost-efficient inference (production agents need to be cheap at scale)
- **Tool-use / function calling** for multi-step reasoning, not prompt chaining
- **SQLite** for demo; production swaps to PostgreSQL + Notion API (haelsi already uses Notion)
- **Department routing** — General Practice, Cardiology, Dermatology with doctor assignment

---

## Live Demo

### Quick Start

```bash
# 1. Clone and setup
git clone https://github.com/gcaur/medintake-agent.git
cd medintake-agent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Add your Anthropic API key
cp .env.example .env
# Edit .env with your ANTHROPIC_API_KEY

# 3. Run
python medintake/agent.py

# 4. Test
curl -X POST http://localhost:8000/intake \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello, I have a fever and sore throat since yesterday. My name is Maria Schmidt. Can I get an appointment?"}'
```

### Example Intake Flow

**Input:**
```json
{
  "message": "I've been having severe chest pain and shortness of breath since this morning. My name is Thomas Weber."
}
```

**Agent thinking (tool calls):**
1. `check_urgency("severe chest pain and shortness of breath")` → EMERGENCY
2. Agent does NOT book — redirects to emergency services

**Output:**
```json
{
  "status": "success",
  "response": "Mr. Weber, your symptoms (severe chest pain and shortness of breath) require immediate emergency attention. Please call 144 (Austrian emergency services) or go to the nearest emergency room immediately. Do not wait for a routine appointment.",
  "timestamp": "2026-07-01T10:30:00"
}
```

**Another example — routine booking:**

**Input:** `{"message": "Hi, I'd like to book a checkup. I'm Lisa Mueller and I need a dermatology appointment for a skin rash on my arm."}`

**Agent thinking:**
1. `check_urgency("skin rash on arm")` → ROUTINE
2. `check_calendar("Dermatology")` → available slots
3. `book_appointment(...)` → confirmed booking with Dr. Mueller
4. `notify_doctor(...)` → alert sent
5. Responds to patient with confirmation

---

## Why This Architecture (vs Make.com/n8n)

| | Make.com/n8n | MedIntake Agent (Claude tool-use) |
|---|---|---|
| **Reasoning** | Linear, pre-defined paths | Dynamic, context-aware decisions |
| **Urgency handling** | Hardcoded if/else chains | Claude assesses nuance in symptoms |
| **Error recovery** | Fails on edge cases | Graceful handling with agent reasoning |
| **Scaling** | Per-workflow pricing | API calls scale linearly, ~$0.002/intake |
| **Maintenance** | Visual spaghetti | Clean Python, version controlled, testable |

---

## Tools Available to the Agent

| Tool | Purpose | When Called |
|---|---|---|
| `check_urgency` | Assess symptom severity | ALWAYS first — safety gate |
| `check_calendar` | Find available slots | After urgency assessment |
| `book_appointment` | Create confirmed booking | After patient confirms slot |
| `notify_doctor` | Alert medical team | After successful booking |

---

## Test Coverage

```bash
pytest tests/ -v
```

Tests cover:
- Urgency assessment (emergency/urgent/routine classification)
- Calendar lookup with seeded availability
- End-to-end booking + notification flow
- Agent integration with Claude API (requires API key)

---

## Built By

**Gagandeep Kaur** — AI Engineer · Agent Builder · Systems Architect

- Co-founder & CTO, iVoz AI (production voice agents with multi-step NLU pipelines)
- NASA HWO contributor (AI/ML for exoplanet survey optimization)
- SpaceTech MSc student at TU Graz (first module at ESA/ESOC Darmstadt)
- 9+ years shipping ML systems and data pipelines

**Portfolio:** [gcaur.github.io](https://gcaur.github.io/) | **GitHub:** [github.com/gcaur](https://github.com/gcaur)

---

## License

MIT — Built as a technical demonstration for haelsi's AI Automation Engineer role.
