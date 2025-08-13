import asyncio
import os
from design_team.main import call_agent_async, session_service, APP_NAME, USER_ID, SESSION_ID
from design_team.agents import root_agent
from google.adk.runners import Runner
from dotenv import load_dotenv

async def main():
    """
    This is the entry point for the application.
    """
    
    load_dotenv()
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "False"
    
    session = await session_service.create_session(
        app_name=APP_NAME,
        user_id=USER_ID,
        session_id=SESSION_ID
    )
    print(f"Session created: App='{APP_NAME}', User='{USER_ID}', Session='{SESSION_ID}'")

    runner = Runner(
        agent=root_agent, # The agent we want to run
        app_name=APP_NAME,   # Associates runs with our app
        session_service=session_service # Uses our session manager
    )
    print(f"Runner created for agent '{runner.agent.name}'.")

    user_input = input(">>> User Input: ")
    response = await call_agent_async(user_input,
                                       runner=runner,
                                       user_id=USER_ID,
                                       session_id=SESSION_ID)
    print(f"<<< Agent Response: {response}")

if __name__ == "__main__":
    asyncio.run(main())
