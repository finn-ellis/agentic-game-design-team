import os
import asyncio
from google.adk.agents import Agent
# from google.adk.models.lite_llm import LiteLlm # For multi-model support
from google.adk.sessions import InMemorySessionService, DatabaseSessionService
from google.adk.runners import Runner
from google.genai import types # For creating message Content/Parts
import logging
from dotenv import load_dotenv
import chainlit as cl
from starlette.datastructures import Headers
from chainlit.types import ThreadDict
from googleadk_database_layer import GoogleADKDataLayer
from typing import Optional
from agents import root_agent
import sqlite3
from config import APP_NAME

# __all__ = ["root_agent"]


load_dotenv()
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "False"

# session_service = InMemorySessionService()
db_url = os.environ["DB_URL"] or "sqlite:///design_team_sessions.db" # Using synchronous SQLite for session service
session_service = DatabaseSessionService(db_url=db_url)

async def init_database():
    """Initialize the database with required tables."""
    try:
        # The DatabaseSessionService handles table creation automatically
        # We just need to ensure the database file can be created
        
        # Test basic database connectivity
        db_path = "design_team_sessions.db"
        conn = sqlite3.connect(db_path)
        conn.execute("SELECT 1")  # Simple test query
        conn.close()
        
        print("Database connection successful!")
        return True
    except Exception as e:
        print(f"Database initialization error: {e}")
        print("This is normal if the database doesn't exist yet - it will be created automatically.")
        return True  # Continue anyway, as the service will create tables as needed

# Run DB initialization at startup
asyncio.run(init_database())

# Define constants for identifying the interaction context
# USER_ID = "user_1"
# SESSION_ID = "session_001" # Using a fixed ID for simplicity

runner = Runner(
    agent=root_agent, # The agent we want to run
    app_name=APP_NAME,   # Associates runs with our app
    session_service=session_service # Uses our session manager
)
print(f"Runner created for agent '{runner.agent.name}'.")


@cl.header_auth_callback
async def header_auth_callback(headers: Headers) -> Optional[cl.User]:
  # Verify the signature of a token in the header (ex: jwt token)
  # or check that the value is matching a row from your database
  print('logging in', Headers)
  return cl.User(identifier="default_user", metadata={"role": "DEV", "provider": "header"})
#   if headers.get("test-header") == "test-value":
#     return cl.User(identifier="admin", metadata={"role": "admin", "provider": "header"})
#   else:
#     return None

data_layer = GoogleADKDataLayer(db_url)
@cl.data_layer
def get_data_layer():
    print("data layer")
    return data_layer

@cl.step(type="tool")
async def tool():
    # Simulate a running task
    await cl.sleep(2)

    return "Response from the tool!"

# New chat started:
@cl.on_chat_start
async def on_chat_start():
    print("A new chat session has started!")
    
    user = cl.user_session.get("user")
    user_id = user and user.identifier or "default_user"
    session_id = cl.user_session.get("id") # Use the same for simplicity
    
    try:
        session = await session_service.create_session(
            app_name=APP_NAME,
            user_id=user_id,
            session_id=session_id
        )
        print(f"Session created: App='{APP_NAME}', User='{user_id}', Session='{session_id}'")
        cl.user_session.set("session_id", session_id)
        cl.user_session.set("user_id", user_id)
        await cl.Message(content="Your personal **Game Design Team**, here to help! \n\nTo get started, *describe your game idea.*").send()
    except Exception as e:
        print(f"Error creating session: {e}")
        print("Attempting to use existing session...")

# New message received from user:
@cl.on_message
async def on_message(msg: cl.Message):
    print("The user sent: ", msg.content)
    session_id = cl.user_session.get("session_id")
    user_id = cl.user_session.get("user_id") #msg.thread_id?
    if not session_id or not user_id:
        print("No session or user ID found. Cannot process message.")
        await cl.Message(content="Error: No active session or user ID found.").send()
        return

    content = types.Content(role='user', parts=[types.Part(text=msg.content)])

    # Key Concept: run_async executes the agent logic and yields Events.
    # We iterate through events to find the final answer.
    async for event in runner.run_async(user_id=user_id, session_id=session_id, new_message=content):
        # You can uncomment the line below to see *all* events during execution
        # print(f"  [Event] Author: {event.author}, Type: {type(event).__name__}, Final: {event.is_final_response()}, Content: {event.content}")
        steps, elements = data_layer._convert_event_to_chainlit(session_id, event)
        for step in steps:
            await cl.Step(
                name = step.get("name", "default_step"),
                type = step.get("type", "run"),
                id = step.get("id", None),
                parent_id = step.get("parentId", None),
                # elements = step.get("elements", []),
                metadata = step.get("metadata", {}),
                # tags: Optional[List[str]] = None,
                # language: Optional[str] = None,
                default_open = False,
                show_input = step.get("showInput", False),
                thread_id = step.get("threadId", session_id),
            ).send()

        # Key Concept: is_final_response() marks the concluding message for the turn.
        # if event.actions and event.actions.escalate: # Handle potential errors/escalations
        #     await response.stream_token("\n\n[Escalation: " + str(event) + "]")

# Task cancelled (stop button pressed):
@cl.on_stop
def on_stop():
    print("The user wants to stop the task!")

# Chat ended (disconnect/switched chat session)
@cl.on_chat_end
async def on_chat_end():
    print("The user disconnected!")
    # If the session is empty, do not persist/delete it:
    session_id = cl.user_session.get("session_id")
    user_id = cl.user_session.get("user_id") #msg.thread_id?
    if not session_id or not user_id:
        print("No session or user ID found. Cannot stop.")
        return
    try:
        # This will persist the session state to the database
        session = await session_service.get_session(app_name=APP_NAME, user_id=user_id, session_id=session_id)
        if session:
            print(f"Session ended: App='{APP_NAME}', User='{user_id}', Session='{str(session)}'")
            if not session.events:
                print("Session is empty, deleting.")
                await session_service.delete_session(app_name=APP_NAME, user_id=user_id, session_id=session_id)
        else:
            print(f"No active session found for App='{APP_NAME}', User='{user_id}', Session='{session_id}'")
    except Exception as e:
        print(f"Error retrieving session: {e}")
        return


# Resumed (only works with chainlit authentication & data persistence)
@cl.on_chat_resume
async def on_chat_resume(thread: ThreadDict):
    print("The user resumed a previous chat session!", thread.get("id"))
    user = cl.user_session.get("user")
    user_id = user and user.identifier or "default_user"
    session_id = thread.get("id") # Use the same for simplicity
    
    try:
        session = await session_service.get_session(
            app_name=APP_NAME,
            user_id=user_id,
            session_id=session_id
        )
        print(f"Session retrieved: App='{APP_NAME}', User='{user_id}', Session='{session_id}'")
        cl.user_session.set("session_id", session_id)
        cl.user_session.set("user_id", user_id)
    except Exception as e:
        print(f"Error resuming session: {e}")

