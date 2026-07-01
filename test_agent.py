"""Tests for MedIntake Agent."""

import pytest
from medintake.agent import MedIntakeAgent, AgentTools, UrgencyLevel


class TestAgentTools:
    """Test the tool implementations."""

    def test_check_urgency_emergency(self):
        tools = AgentTools(db_path=":memory:")
        result = tools.check_urgency("severe chest pain and difficulty breathing")
        assert "EMERGENCY" in result
        assert "144" in result

    def test_check_urgency_urgent(self):
        tools = AgentTools(db_path=":memory:")
        result = tools.check_urgency("high fever and bad infection")
        assert "URGENT" in result

    def test_check_urgency_routine(self):
        tools = AgentTools(db_path=":memory:")
        result = tools.check_urgency("annual checkup and prescription refill")
        assert "ROUTINE" in result

    def test_calendar_returns_slots(self):
        tools = AgentTools(db_path=":memory:")
        result = tools.check_calendar("General Practice")
        assert "Dr." in result  # Should contain doctor names
        assert "Available" in result or "No available" in result

    def test_book_and_notify(self):
        tools = AgentTools(db_path=":memory:")
        # Book an appointment
        result = tools.book_appointment(
            patient_name="Test Patient",
            datetime_str="2025-07-15T10:00:00",
            department="General Practice",
            urgency="routine",
            symptoms_summary="Test symptoms"
        )
        assert "CONFIRMED" in result
        assert "appt_" in result

        # Extract appointment ID
        appt_id = [line for line in result.split("\n") if "ID:" in line][0].split(":")[1].strip()

        # Notify doctor
        notify_result = tools.notify_doctor(appt_id, "Test notification")
        assert "NOTIFICATION SENT" in notify_result


class TestMedIntakeAgent:
    """Test the main agent (requires ANTHROPIC_API_KEY)."""

    @pytest.mark.skipif(
        not pytest.importorskip("os").environ.get("ANTHROPIC_API_KEY"),
        reason="No ANTHROPIC_API_KEY set"
    )
    def test_process_intake(self):
        """End-to-end test with real Claude API."""
        agent = MedIntakeAgent()
        result = agent.process_intake(
            "Hello, I have been having headaches and need a checkup. My name is Anna."
        )
        assert "response" in result
        assert result["response"]  # Non-empty response
