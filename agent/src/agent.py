import asyncio
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
    ConversationItemAddedEvent,
    JobContext,
    RunContext,
    TurnHandlingOptions,
    cli,
    function_tool,
    inference,
    room_io,
)
from livekit.agents.llm import ChatContext, ChatMessage
from livekit.plugins import ai_coustics

logger = logging.getLogger("agent")

load_dotenv(".env")

BACKEND = os.environ.get("BACKEND_URL", "http://localhost:8000")
BACKEND_DOWN = "I couldn't reach the case system right now, please try again later."
ISSUE_TYPES = "missed_pickup, pothole, streetlight, water, animal, other"
HEADERS = {"X-Source": "voice"}  # audit log attributes these writes to the voice agent
SUMMARY_PROMPT = (
    "Summarize this City services call for staff in at most two sentences: what the "
    "resident wanted, what was actually done (case created/found, note added), and any "
    "follow-up needed. State only what the transcript shows; if the call ended before a "
    "case was created or found, say so plainly. Transcript:\n"
)


def digits(phone: str) -> str:
    return re.sub(r"\D", "", phone)


def valid_phone(phone: str) -> bool:
    # STT sometimes splits a number across turns ("25" + "7062"); refuse to file a partial one
    return len(digits(phone)) == 10


def clean_text(text: str) -> str:
    # expressive TTS mode embeds <expr .../> tags in agent text; the dashboard shouldn't see them
    return re.sub(r"\s+", " ", re.sub(r"<expr[^>]*/>", "", text)).strip()


# Call-record helpers. call_id is None when the backend was down at session start:
# every helper then no-ops, so the voice call keeps working without the dashboard.
async def start_call(room: str | None = None) -> str | None:
    try:
        async with httpx.AsyncClient(timeout=5, headers=HEADERS) as client:
            r = await client.post(f"{BACKEND}/calls", json={"room": room})
            r.raise_for_status()
            return r.json()["id"]
    except Exception:
        logger.warning("could not create call record; transcript will not be streamed")
        return None


async def post_line(call_id: str | None, role: str, text: str) -> None:
    if call_id is None or not text:
        return
    try:
        async with httpx.AsyncClient(timeout=5, headers=HEADERS) as client:
            r = await client.post(
                f"{BACKEND}/calls/{call_id}/transcript", json={"role": role, "text": text}
            )
            r.raise_for_status()
    except Exception:
        logger.warning("post_line failed", exc_info=True)


async def patch_call(call_id: str | None, body: dict) -> bool:
    if call_id is None:
        return False
    try:
        async with httpx.AsyncClient(timeout=5, headers=HEADERS) as client:
            r = await client.patch(f"{BACKEND}/calls/{call_id}", json=body)
            r.raise_for_status()
            return True
    except Exception:
        logger.warning("patch_call failed", exc_info=True)
        return False


async def end_call(call_id: str | None) -> None:
    await patch_call(call_id, {"status": "ended"})


def history_text(items) -> str:
    # the ChatContext also holds tool calls and their outputs; only spoken turns summarize well
    turns = []
    for item in items:
        if isinstance(item, ChatMessage) and item.role in ("user", "assistant"):
            text = clean_text(item.text_content or "")
            if text:
                turns.append(f"{'Caller' if item.role == 'user' else 'Agent'}: {text}")
    return "\n".join(turns) if len(turns) >= 2 else ""  # one turn is just the greeting


async def summarize(session: AgentSession) -> str | None:
    transcript = history_text(session.history.items)
    if not transcript:
        return None

    async def run() -> str:
        llm = inference.LLM(model="openai/gpt-4.1-mini")
        chat_ctx = ChatContext.empty()
        chat_ctx.add_message(role="user", content=SUMMARY_PROMPT + transcript)
        parts = []
        async with llm.chat(chat_ctx=chat_ctx) as stream:
            async for chunk in stream:
                if chunk.delta and chunk.delta.content:
                    parts.append(chunk.delta.content)
        return "".join(parts).strip()

    try:
        return await asyncio.wait_for(run(), timeout=15) or None
    except Exception:  # a missing summary must never keep the call from being marked ended
        logger.warning("summarize failed", exc_info=True)
        return None


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

                To file a request, collect one at a time: the caller's name, then their phone
                number. If the caller spells their name letter by letter, use exactly the
                spelled version and drop what you heard before. Only the phone number needs
                confirming: read the digits back. As soon as the phone number is confirmed,
                call create_case with the name and phone, then ask what the issue is. Do not
                mention the case ID yet. The moment you can map what the caller says onto
                exactly one of {ISSUE_TYPES}, call update_case with that issue_type, then ask
                for a one-sentence description and call update_case with the description. Do
                not ask the caller to confirm the name, issue type, or description; just move
                on. Only after the description is saved, read the case ID back slowly,
                character by character.

                If the caller asks about an existing case, call lookup_case with the phone
                number they already gave on this call; only ask for it if you don't have it. To add a note, call add_note with the case ID and the note.

                This is a voice call: plain text only, one or two short sentences per reply,
                spell out numbers. Never invent a case status or ID; only repeat what a tool
                returned. If a tool says the system is unreachable, tell the caller that. If asked why
                you need something, say you need it to file or find the case; don't cite policies.
                """
            ),
        )
        self.call_id: str | None = None  # set by the entrypoint once POST /calls succeeds
        # the case this call created (one Assistant per job, so no reset needed);
        # update_case uses it so the LLM never has to repeat the ID
        self.case_id: str | None = None
        self.call_linked = False  # PATCH /calls/{id} case_id succeeded; retried until it does

    async def _link_call(self) -> None:
        # idempotent: a failed link right after create_case is retried on the next tool call,
        # so a transient backend error can't leave the case detached from its call for good
        if self.case_id and not self.call_linked:
            self.call_linked = await patch_call(self.call_id, {"case_id": self.case_id})

    @function_tool
    async def create_case(self, context: RunContext, name: str, phone: str) -> str:
        """Open a new service request. Call as soon as you have the caller's name and their
        confirmed phone number, before asking about the issue.

        Args:
            name: caller's full name
            phone: caller's phone number
        """
        if self.case_id:  # the LLM occasionally re-calls a tool; keep one case per call
            await self._link_call()
            return f"Case {self.case_id} is already open for this call."
        if not valid_phone(phone):
            n = len(digits(phone))
            return f"That number has {n} digits; a phone number should have ten. Could you say it again?"
        # issue_type/description are filled in by update_case as the caller explains
        body = {"name": name, "phone": digits(phone), "issue_type": "other", "description": ""}
        try:
            async with httpx.AsyncClient(timeout=10, headers=HEADERS) as client:
                r = await client.post(f"{BACKEND}/cases", json=body)
                r.raise_for_status()
                case_id = r.json()["id"]
        except Exception:  # never raise: the agent must say the failure, not crash
            logger.exception("create_case failed")
            return BACKEND_DOWN
        self.case_id = case_id
        await self._link_call()
        return f"Started case {case_id}"

    @function_tool
    async def update_case(
        self,
        context: RunContext,
        issue_type: str | None = None,
        description: str | None = None,
    ) -> str:
        """Fill in the issue type or description on the case opened by create_case.
        Call it as soon as you know each one; you can call it twice.

        Args:
            issue_type: exactly one of missed_pickup, pothole, streetlight, water, animal, other
            description: one-sentence description of the problem
        """
        if not self.case_id:
            return "No case is open yet; call create_case with the name and phone first."
        body = {}
        if issue_type is not None:
            if issue_type not in ISSUE_TYPES.split(", "):
                return f"issue_type must be exactly one of: {ISSUE_TYPES}"
            body["issue_type"] = issue_type
        if description is not None:
            body["description"] = description
        if not body:
            return "Nothing to update."
        try:
            async with httpx.AsyncClient(timeout=10, headers=HEADERS) as client:
                r = await client.patch(f"{BACKEND}/cases/{self.case_id}", json=body)
                r.raise_for_status()
        except Exception:  # never raise: the agent must say the failure, not crash
            logger.exception("update_case failed")
            return BACKEND_DOWN
        await self._link_call()
        return f"Updated case {self.case_id}"

    @function_tool
    async def lookup_case(self, context: RunContext, phone: str) -> str:
        """Find the most recent case filed under a phone number.

        Args:
            phone: caller's phone number
        """
        try:
            async with httpx.AsyncClient(timeout=10, headers=HEADERS) as client:
                r = await client.get(f"{BACKEND}/cases", params={"phone": digits(phone)})
                r.raise_for_status()
                cases = r.json()
        except Exception:
            logger.exception("lookup_case failed")
            return BACKEND_DOWN
        if not cases:
            return "No case found for that number."
        c = cases[0]  # backend returns newest first
        await patch_call(self.call_id, {"case_id": c["id"]})  # link live call to its case
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
            async with httpx.AsyncClient(timeout=10, headers=HEADERS) as client:
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


# no agent_name: the worker is auto-dispatched to every new room, so the browser
# client only needs a token (explicit dispatch would need a second API call)
@server.rtc_session()
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

    agent = Assistant()
    await session.start(
        agent=agent,
        room=ctx.room,
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(
                noise_cancellation=ai_coustics.audio_enhancement(
                    model=ai_coustics.EnhancerModel.QUAIL_VF_S
                ),
            ),
        ),
    )

    agent.call_id = await start_call(ctx.room.name)

    # session.on handlers must be sync, so HTTP work runs in a task; the set keeps a
    # strong reference until done (asyncio only holds tasks weakly, so they could be GC'd)
    tasks: set[asyncio.Task] = set()

    def spawn(coro):
        t = asyncio.create_task(coro)
        tasks.add(t)
        t.add_done_callback(tasks.discard)

    @session.on("conversation_item_added")
    def _on_item(ev: ConversationItemAddedEvent):
        # one line per committed turn for both roles (per-segment STT events would
        # split "925." / "915-7062." into separate lines); assistant items arrive after playout
        if isinstance(ev.item, ChatMessage) and ev.item.role in ("user", "assistant"):
            role = "user" if ev.item.role == "user" else "agent"
            spawn(post_line(agent.call_id, role, clean_text(ev.item.text_content or "")))

    # shutdown callbacks are awaited by the job runner (a session "close" handler isn't), so the
    # process waits for the summary and the call is reliably marked ended even on Ctrl-C;
    # end_call always runs, even when summarize fails
    async def on_shutdown():
        summary = await summarize(session)
        if summary:
            await patch_call(agent.call_id, {"summary": summary})
        await end_call(agent.call_id)

    ctx.add_shutdown_callback(on_shutdown)

    await ctx.connect()

    await session.generate_reply(
        instructions="Greet the caller as the City services line and ask how you can help."
    )


if __name__ == "__main__":
    cli.run_app(server)
