import logging
import os
import re
import textwrap

import httpx
from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    RunContext,
    TurnHandlingOptions,
    cli,
    function_tool,
    inference,
    room_io,
)
from livekit.plugins import ai_coustics

logger = logging.getLogger("agent")

load_dotenv(".env")

BACKEND = os.environ.get("BACKEND_URL", "http://localhost:8000")
BACKEND_DOWN = "I couldn't reach the case system right now, please try again later."
ISSUE_TYPES = "missed_pickup, pothole, streetlight, water, animal, other"


def digits(phone: str) -> str:
    return re.sub(r"\D", "", phone)


class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            # LiveKit Inference model (no provider key needed). Starter default is
            # google/gemma-4-31b-it; gpt-4.1-mini chosen for reliable tool calling.
            llm=inference.LLM(model="openai/gpt-4.1-mini"),
            instructions=textwrap.dedent(
                f"""\
                You are the City services phone line. You only do three things: file a new
                service request, look up an existing case by phone number, or add a note to a
                case. Politely decline anything else.

                To file a request, collect one at a time: the caller's name, their phone
                number (read the digits back and confirm), the issue type, and a one-sentence
                description. Map what the caller says onto exactly one of: {ISSUE_TYPES}.
                Then call create_case and read the case ID back slowly, character by character.

                If the caller asks about an existing case, ask for their phone number and call
                lookup_case. To add a note, call add_note with the case ID and the note.

                This is a voice call: plain text only, one or two short sentences per reply,
                spell out numbers. Never invent a case status or ID; only repeat what a tool
                returned. If a tool says the system is unreachable, tell the caller that.
                """
            ),
        )

    @function_tool
    async def create_case(
        self,
        context: RunContext,
        name: str,
        phone: str,
        issue_type: str,
        description: str,
    ) -> str:
        """File a new service request. Only call after the caller has confirmed all four fields.

        Args:
            name: caller's full name
            phone: caller's phone number
            issue_type: exactly one of missed_pickup, pothole, streetlight, water, animal, other
            description: one-sentence description of the problem
        """
        body = {
            "name": name,
            "phone": digits(phone),
            "issue_type": issue_type,
            "description": description,
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.post(f"{BACKEND}/cases", json=body)
                r.raise_for_status()
                return f"Created case {r.json()['id']}"
        except Exception:  # never raise: the agent must say the failure, not crash
            logger.exception("create_case failed")
            return BACKEND_DOWN

    @function_tool
    async def lookup_case(self, context: RunContext, phone: str) -> str:
        """Find the most recent case filed under a phone number.

        Args:
            phone: caller's phone number
        """
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(f"{BACKEND}/cases", params={"phone": digits(phone)})
                r.raise_for_status()
                cases = r.json()
        except Exception:
            logger.exception("lookup_case failed")
            return BACKEND_DOWN
        if not cases:
            return "No case found for that number."
        c = cases[0]  # backend returns newest first
        return (
            f"Case {c['id']}, {c['issue_type']}, status {c['status']}, "
            f"description {c['description']}"
        )

    @function_tool
    async def add_note(self, context: RunContext, case_id: str, note: str) -> str:
        """Append a note to an existing case.

        Args:
            case_id: the case ID, like C-1001
            note: the note to add
        """
        case_id = case_id.strip().upper()
        if not case_id.startswith("C-"):  # caller may say "1001" or "c 1001"
            case_id = "C-" + digits(case_id)
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(f"{BACKEND}/cases/{case_id}")
                if r.status_code == 404:
                    return f"No case found with ID {case_id}."
                r.raise_for_status()
                # PATCH notes replaces the field, so append client-side (per CONTRACT.md)
                notes = (r.json()["notes"] + "\n" + note).strip()
                r = await client.patch(f"{BACKEND}/cases/{case_id}", json={"notes": notes})
                r.raise_for_status()
                return f"Note added to case {case_id}"
        except Exception:
            logger.exception("add_note failed")
            return BACKEND_DOWN


server = AgentServer()


@server.rtc_session(agent_name="city-services")
async def city_services(ctx: JobContext):
    ctx.log_context_fields = {"room": ctx.room.name}

    # Voice pipeline as shipped by the starter: AssemblyAI STT, Fish Audio TTS,
    # LiveKit turn detector (supplies VAD), all via LiveKit Inference.
    session = AgentSession(
        stt=inference.STT(model="assemblyai/universal-3-5-pro", language="en"),
        tts=inference.TTS(
            model="fishaudio/s2.1-pro", voice="fa4c9eb3dccc4806b382b40d61c6b10a"
        ),
        turn_handling=TurnHandlingOptions(
            turn_detection=inference.TurnDetector(),
            interruption={"mode": "adaptive"},
            preemptive_generation={"enabled": True},
        ),
        expressive=True,
    )

    await session.start(
        agent=Assistant(),
        room=ctx.room,
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(
                noise_cancellation=ai_coustics.audio_enhancement(
                    model=ai_coustics.EnhancerModel.QUAIL_VF_S
                ),
            ),
        ),
    )

    await ctx.connect()

    await session.generate_reply(
        instructions="Greet the caller as the City services line and ask how you can help."
    )


if __name__ == "__main__":
    cli.run_app(server)
