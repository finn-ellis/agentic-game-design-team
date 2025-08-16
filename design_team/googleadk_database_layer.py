import asyncio
import atexit
import json
import signal
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

import aiosqlite
import aiofiles
from chainlit.data.base import BaseDataLayer
from chainlit.data.storage_clients.base import BaseStorageClient
from chainlit.data.utils import queue_until_user_message
from chainlit.element import ElementDict
from chainlit.logger import logger
from chainlit.step import StepDict
from chainlit.types import (
    Feedback,
    FeedbackDict,
    PageInfo,
    PaginatedResponse,
    Pagination,
    ThreadDict,
    ThreadFilter,
)
from chainlit.user import PersistedUser, User
from google.adk.events import Event
import os
from google.adk.sessions import InMemorySessionService, DatabaseSessionService, Session
from config import APP_NAME
from google.genai.types import Content


# TODO: convert to read from google database

if TYPE_CHECKING:
    from chainlit.element import Element, ElementDict
    from chainlit.step import StepDict

ISO_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"

db_url = os.environ["DB_URL"] or "sqlite:///design_team_sessions.db" # Using synchronous SQLite for session service
session_service = DatabaseSessionService(db_url=db_url)

class GoogleADKDataLayer(BaseDataLayer):
    def __init__(
        self,
        database_url: str,
        storage_client: Optional[BaseStorageClient] = None,
        show_logger: bool = False,
    ):
        self.database_url = database_url.replace("sqlite:///", "")
        self.storage_client = storage_client
        self.show_logger = show_logger

        # Register cleanup handlers for application termination
        atexit.register(self._sync_cleanup)
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, self._signal_handler)

    async def get_current_timestamp(self) -> datetime:
        return datetime.now()

    async def execute_query(
        self, query: str, params: Union[Dict, None] = None
    ) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.database_url) as db:
            db.row_factory = aiosqlite.Row
            try:
                async with db.execute(query, list(params.values()) if params else []) as cursor:
                    records = await cursor.fetchall()
                    return [dict(record) for record in records]
            except Exception as e:
                logger.error(f"Database error: {e!s}")
                raise

    async def get_user(self, identifier: str) -> Optional[PersistedUser]:
        query = """
        SELECT user_id, MIN(create_time) as created_at 
        FROM sessions 
        WHERE user_id = ?
        GROUP BY user_id
        """
        result = await self.execute_query(query, {"identifier": identifier})
        if not result or len(result) == 0:
            return None
        row = result[0]

        return PersistedUser(
            id=str(row.get("user_id")),
            identifier=str(row.get("user_id")),
            createdAt=row.get("created_at") or "",
            metadata={},
        )

    async def create_user(self, user: User) -> Optional[PersistedUser]:
        # Read-only
        return PersistedUser(
            id=str(uuid.uuid4()),
            identifier=user.identifier,
            createdAt=(await self.get_current_timestamp()).isoformat(),
            metadata=user.metadata,
        )

    async def delete_feedback(self, feedback_id: str) -> bool:
        # Read-only
        return True

    async def upsert_feedback(self, feedback: Feedback) -> str:
        # Read-only
        return feedback.id or str(uuid.uuid4())

    @queue_until_user_message()
    async def create_element(self, element: "Element"):
        # Read-only
        pass

    async def get_element(
        self, thread_id: str, element_id: str
    ) -> Optional[ElementDict]:
        # Not directly supported by ADK schema in a simple way
        return None

    @queue_until_user_message()
    async def delete_element(self, element_id: str, thread_id: Optional[str] = None):
        # Read-only
        pass

    @queue_until_user_message()
    async def create_step(self, step_dict: StepDict):
        # Read-only
        pass

    @queue_until_user_message()
    async def update_step(self, step_dict: StepDict):
        # Read-only
        pass

    @queue_until_user_message()
    async def delete_step(self, step_id: str):
        # Read-only
        pass

    async def get_thread_author(self, thread_id: str) -> str:
        query = """
        SELECT user_id 
        FROM sessions
        WHERE id = ?
        """
        results = await self.execute_query(query, {"thread_id": thread_id})
        if not results:
            raise ValueError(f"Thread {thread_id} not found")
        return results[0]["user_id"]

    async def delete_thread(self, thread_id: str):
        # kind of inefficient
        author = await self.get_thread_author(thread_id)
        await session_service.delete_session(
            app_name=APP_NAME,
            user_id=author, # need to fetch
            session_id=thread_id
        )

    async def list_threads(
        self, pagination: Pagination, filters: ThreadFilter
    ) -> PaginatedResponse[ThreadDict]:
        query = """
        SELECT 
            s.id,
            s.create_time as "createdAt",
            s.id as name,
            s.user_id as "userId",
            s.user_id as user_identifier,
            s.state as metadata
        FROM sessions s
        WHERE 1=1
        """
        params: Dict[str, Any] = {}
        param_count = 1

        if filters.search:
            query += f" AND s.id ILIKE ?"
            params[f"param_{param_count}"] = f"%{filters.search}%"
            param_count += 1

        if filters.userId:
            query += f' AND s.user_id = ?'
            params[f"param_{param_count}"] = filters.userId
            param_count += 1

        if pagination.cursor:
            query += f' AND s.create_time < (SELECT create_time FROM sessions WHERE id = ?)'
            params[f"param_{param_count}"] = pagination.cursor
            param_count += 1

        query += f' ORDER BY s.create_time DESC LIMIT ?'
        params[f"param_{param_count}"] = pagination.first + 1

        results = await self.execute_query(query, params)
        threads = results

        has_next_page = len(threads) > pagination.first
        if has_next_page:
            threads = threads[:-1]

        thread_dicts = []
        for thread in threads:
            thread_dict = ThreadDict(
                id=str(thread["id"]),
                createdAt=thread["createdAt"],
                name=thread["name"],
                userId=str(thread["userId"]) if thread["userId"] else None,
                userIdentifier=thread["user_identifier"],
                metadata=json.loads(thread["metadata"] or '{}'),
                steps=[],
                elements=[],
                tags=[],
            )
            thread_dicts.append(thread_dict)

        return PaginatedResponse(
            pageInfo=PageInfo(
                hasNextPage=has_next_page,
                startCursor=thread_dicts[0]["id"] if thread_dicts else None,
                endCursor=thread_dicts[-1]["id"] if thread_dicts else None,
            ),
            data=thread_dicts,
        )

    async def get_thread(self, thread_id: str) -> Optional[ThreadDict]:
        query = """
        SELECT id, create_time as "createdAt", id as name, user_id, state as metadata
        FROM sessions
        WHERE id = ?
        """
        results = await self.execute_query(query, {"thread_id": thread_id})

        if not results:
            return None

        thread = results[0]
        user_id = thread.get("user_id")
        if not user_id:
            raise ValueError(f"Thread {thread_id} not found or has no user_id")
        session = await session_service.get_session(
            app_name=APP_NAME,
            user_id=user_id,
            session_id=thread_id
        )
        if not session:
            raise ValueError(f"Session for thread {thread_id} not found")

        steps, elements = self._convert_events_to_chainlit(session)
        return ThreadDict(
            id=str(thread["id"]),
            createdAt=thread["createdAt"],
            name=thread["name"],
            userId=str(thread["user_id"]) if thread["user_id"] else None,
            userIdentifier=str(thread["user_id"]) if thread["user_id"] else None,
            metadata={},
            steps=steps,
            elements=elements,
            tags=[],
        )

    async def update_thread(
        self,
        thread_id: str,
        name: Optional[str] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
        tags: Optional[List[str]] = None,
    ):
        # Read-only
        pass

    def _extract_feedback_dict_from_step_row(self, row: Dict) -> Optional[FeedbackDict]:
        return None

    def _convert_event_to_chainlit(self, session_id, event: Event) -> tuple[list[StepDict], list[ElementDict]]:
        steps = []
        elements = []
        function_call_steps = {}
        print("\n\n")
        print(event)
        print("\n\n")
        event_text = ""
        pId = 0

        if event.error_code:
            steps.append(StepDict(
                id=event.id,
                threadId=session_id,
                parentId=None,  # Not available in ADK
                name=event.author,
                type="system_message",
                input="",
                output=f"`{event.error_code}`]`: {event.error_message}",
                metadata=event.custom_metadata or {},
                createdAt=str(event.timestamp),
                showInput=False,
                isError=True,
                feedback=None,
            ))
            return steps, elements
        if not event.content:
            return steps, elements
        if not event.content.parts:
            return steps, elements
        if not event.actions.state_delta:
            steps.append(StepDict(
                id=event.id + "_stupd",
                threadId=session_id,
                parentId=event.id,
                name=event.author,
                type="system_message",
                input="",
                output="*State updated.*",
                metadata=event.custom_metadata or {},
                createdAt=str(event.timestamp),
                showInput=False,
                isError=False,
                feedback=None,
            ))
        for part in event.content.parts:
            pId += 1
            part_id = f"{event.id}_{pId}"
            if part.function_call:
                call_step = StepDict(
                    id=part_id,
                    threadId=session_id,
                    parentId=event.id,
                    name=part.function_call.name or "(unknown)",
                    type="tool",
                    input=str(part.function_call.args),
                    output="(ERROR)",
                    metadata=event.custom_metadata or {},
                    createdAt=str(event.timestamp),
                    showInput=True,
                    isError=False,
                    feedback=None,
                )
                function_call_steps[part.function_call.id] = call_step
                steps.append(call_step)
            if part.function_response:
                if part.function_response.id in function_call_steps:
                    # Link the function response to the function call step
                    call_step = function_call_steps[part.function_response.id]
                    call_step.update({
                        "output": str(part.function_response.response),
                        "isError": False,  # TODO: Handle errors if needed
                    })
                    # if part.function_response.error:
                    #     call_step.feedback = FeedbackDict(
                    #         id=str(uuid.uuid4()),
                    #         type="error",
                    #         text=part.function_response.error,
                    #     )
            if part.text:
                event_text += part.text
        if event_text:
            steps.append(StepDict(
                    id=event.id,
                    threadId=session_id,
                    parentId=None,  # Not available in ADK
                    name=event.author,
                    type="user_message" if event.content.role == "user" else "assistant_message",
                    input="",
                    output=event_text,
                    metadata=event.custom_metadata or {},
                    createdAt=str(event.timestamp),
                    showInput=False,
                    isError=False,
                    feedback=None,
                ))
        return steps, elements

    def _convert_events_to_chainlit(self, session: Session) -> tuple[list[StepDict], list[ElementDict]]:
        steps = []
        elements = []
        for event in session.events:
            event_steps, event_elements = self._convert_event_to_chainlit(session.id, event)
            steps.extend(event_steps)
            elements.extend(event_elements)
        return steps, elements

    def _convert_element_row_to_dict(self, row: Dict) -> ElementDict:
        # Not implemented as ADK schema does not map directly to elements
        raise NotImplementedError

    async def build_debug_url(self) -> str:
        return ""

    async def cleanup(self):
        """Cleanup database connections"""
        pass

    def _sync_cleanup(self):
        """Cleanup database connections in a synchronous context."""
        pass

    def _signal_handler(self, sig, frame):
        """Handle signals for graceful shutdown."""
        logger.info(f"Received signal {sig}, cleaning up connection pool.")
        self._sync_cleanup()
        # Re-raise the signal after cleanup
        signal.default_int_handler(sig, frame)


def truncate(text: Optional[str], max_length: int = 255) -> Optional[str]:
    return None if text is None else text[:max_length]
