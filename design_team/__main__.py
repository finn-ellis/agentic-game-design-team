import asyncio
import os
from design_team.app import call_agent_async, session_service, APP_NAME, USER_ID, SESSION_ID, init_database
from design_team.agents import root_agent
from google.adk.runners import Runner
from dotenv import load_dotenv
import chainlit as cl

async def main():
    """
    This is the entry point for the application.
    """
    
    load_dotenv()
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "False"
    
    # Initialize the database first
    print("Initializing database...")
    await init_database()
    
    try:
        session = await session_service.create_session(
            app_name=APP_NAME,
            user_id=USER_ID,
            session_id=SESSION_ID
        )
        print(f"Session created: App='{APP_NAME}', User='{USER_ID}', Session='{SESSION_ID}'")
    except Exception as e:
        print(f"Error creating session: {e}")
        print("Attempting to use existing session...")
        # If session creation fails, we can still try to use the session service

    print(f"Runner created for agent '{runner.agent.name}'.")

    user_input = input(">>> User Input: ")
    response = await call_agent_async(user_input,
                                       user_id=USER_ID,
                                       session_id=SESSION_ID)
    print(f"<<< Agent Response: {response}")


if __name__ == "__main__":
    asyncio.run(main())
