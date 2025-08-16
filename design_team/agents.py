import logging
from typing import AsyncGenerator, Literal
from google.adk.agents import LlmAgent, BaseAgent, LoopAgent, SequentialAgent, ParallelAgent
from google.adk.agents.invocation_context import InvocationContext
from google.genai import types
from google.adk.sessions import InMemorySessionService
from google.adk.runners import Runner
from google.adk.events import Event
from google.adk.planners import BuiltInPlanner, PlanReActPlanner
from google.adk.tools.agent_tool import AgentTool
from google.adk.events import Event, EventActions
from pydantic import BaseModel, Field
from google.genai import types
from config import config
from team_agreement import team_agreement

# --- Constants ---

# --- Structured Output Models ---
class Feedback(BaseModel):
    """Model for providing evaluation feedback on gameplay design quality."""

    grade: Literal["pass", "fail"] = Field(
        description="Evaluation result. 'pass' if the gameplay design is sufficient, 'fail' if it needs revision."
    )
    comment: str = Field(
        description="Detailed explanation of the evaluation, highlighting strengths and/or weaknesses of the gameplay."
    )
    follow_ups: list[str] | None = Field(
        default=None,
        description="A list of specific, targeted changes needed to fix gameplay issues. This should be null or empty if the grade is 'pass'.",
    )

# --- Agents ---
lead_game_designer = LlmAgent(
	name="LeadGameDesigner",
	model=config.designer_model,
	description="Generates or refines the existing game design plan.",
	instruction=f"""
	You are a game design expert. Your job is to create a game design overview.
	If there is an existing game overview, refine it based on user feedback.

    { team_agreement }
    
	GAME OVERVIEW (so far):
	{{ game_overview? }}

	**CORE ELEMENTS TO INCLUDE:**
	a. Two-sentence elevator pitch
	b. Game Vision
	c. Genre
	d. Core Fantasy
	e. Target Audience (self-determination theory, player types & archetype taxonomy)
	f. Design Pillars
    g. Extra comments, thoughts, direction
	""",
	include_contents='default',
    output_key="game_overview",
	planner=BuiltInPlanner(
        thinking_config=types.ThinkingConfig(
            include_thoughts=False, # irrelevant to the team?
            thinking_budget=1024,
        )
    ),
)

gameplay_designer = LlmAgent(
	name="GameplayDesigner",
	model=config.designer_model,
	description="Develops core mechanics, systems, and rules that empower the player's agency. Generates thorough plans and foresees contradictions.",
	instruction=f"""
    You are a highly capable and dilligent gameplay designer and psychologist.
    Your task is to generate a comprehensive plan for core gameplay & mechanics based on the `game_overview` state key.
    
    Analyze the psychology of the target audience using self-determination theory and player archetype taxonomy.
    Develop precise gameplay mechanics that cater to the identified player types.
    Ground these mechanics in tried-and-true methods before innovating.
    
	{ team_agreement }
    
    **Final Output:** A detailed plan of the:
    a. Core Loop
	b. Goals & Progression (short, medium, long term)
	c. All Core Systems
	d. Other Mechanics
	""",
    output_key="gameplay_plan",
	include_contents='default',
	planner=BuiltInPlanner(
        thinking_config=types.ThinkingConfig(
            include_thoughts=True, # irrelevant to the team?
            thinking_budget=1024,
        )
    ),
)

gameplay_evaluator = LlmAgent(
	name="GameplayDesignCritic",
	model=config.worker_model,
	description="Evaluates and provides feedback on gameplay mechanics, expected player experience, and design coherence.",
	instruction=f"""
	You are a meticulous, creative, veteran gameplay designer. Your task is to evaluate the gameplay overview in the `gameplay_plan` state key.
    Reference the game overview in the `game_overview` state key for alignment.
    
	{ team_agreement }

    
	**ENSURE:**
    - Core design principles integration: the gameplay must contribute to the game being clickable, social, replayable, and fun
    - The core gameplay loop must be clear, engaging, and targeted
	- The gameplay must be aligned with the core fantasy
	- The gameplay must fit the target audience
	- The gameplay must leverage successful tactics

    Your response must be a single, raw JSON object validating against the 'Feedback' schema.
	""",
	include_contents='default',
    output_schema=Feedback,
    disallow_transfer_to_parent=True,
    disallow_transfer_to_peers=True,
    output_key="gameplay_evaluation",
	# planner=BuiltInPlanner(
    #     thinking_config=types.ThinkingConfig(
    #         include_thoughts=False,
    #         thinking_budget=1024,
    #     )
    # ),
)

# --- Custom Agent for Loop Control ---
class EscalationChecker(BaseAgent):
    """Checks gameplay evaluation and escalates to stop the loop if grade is 'pass'."""

    def __init__(self, name: str):
        super().__init__(name=name)

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        evaluation_result = ctx.session.state.get("gameplay_evaluation")
        if evaluation_result and evaluation_result.get("grade") == "pass":
            logging.info(
                f"[{self.name}] Gameplay evaluation passed. Escalating to stop loop."
            )
            yield Event(author=self.name, actions=EventActions(escalate=True))
        else:
            logging.info(
                f"[{self.name}] Gameplay evaluation failed or not found. Loop will continue."
            )
            # Yielding an event without content or actions just lets the flow continue.
            yield Event(author=self.name)
	
gameplay_refiner = LlmAgent(
    model=config.worker_model,
    name="gameplay_refiner",
    description="Refines gameplay according to feedback.",
    # planner=BuiltInPlanner(
    #     thinking_config=types.ThinkingConfig(
    #         include_thoughts=False,
    #         thinking_budget=1024,
    #     )
    # ),
    instruction=f"""
    You are an expert gameplay designer executing a refinement pass.
    You have been activated because the previous gameplay evaluation was graded as 'fail'.

	{ team_agreement }

	
	**REVISE TO ENSURE:**
    - Core design principles integration: the gameplay must contribute to the game being clickable, social, replayable, and fun
    - The core gameplay loop must be clear, engaging, and targeted
	- The gameplay must be aligned with the core fantasy
	- The gameplay must fit the target audience
	- The gameplay must leverage successful tactics
    
    1. Familiarize yourself with the `game_overview` to understand the direction.
    2. Review 'gameplay_evaluation' state key to understand the feedback and required fixes.
    3. Make revisions to the 'gameplay_plan' based on EVERYTHING listed in 'follow_ups'.
    4. Your output MUST be the new, complete, and improved gameplay plan.
    """,
    output_key="gameplay_plan",
)

art_director = LlmAgent(
	name="NarrativeDesigner",
	model=config.designer_model,
	description="Imbues the existing game with rich artistic and narrative vision.",
	instruction=f"""
	You are a video game Art Director responsible for the visual and narrative aspects of the game. Your task is to ensure that the game's art style, character designs, and narrative elements are cohesive and enhance the overall player experience.
    
	{ team_agreement }

    
    ### TASK:
    1. Review the existing `{{game_overview}}` and `{{gameplay_plan}}`
    2. Generate a vision for the game world covering at least the following aspects:
		a. Narrative
		b. Aesthetic Vision
		c. Desired User Experience
	""",
	include_contents='default',
    output_key="art_narrative_plan",
    planner=BuiltInPlanner(
        thinking_config=types.ThinkingConfig(
            include_thoughts=False,
            thinking_budget=1024,
        )
    ),
)

marketing_director = LlmAgent(
	name="MarketingDirector",
	model=config.designer_model,
	description="Crafts the marketing strategy and messaging for the game.",
	instruction=f"""
	You are a relentless video game Marketing Director.
    Your task is to create a comprehensive marketing strategy that aligns with the game's vision and target audience.
    Discover intelligent moments during gameplay to place monetization.
    Analyze the target audience and tailor advertising to their preferences.

	{ team_agreement }
    
    ### TASK:
    1. Review the `{{game_overview}}`, `{{gameplay_plan}}`, and `{{art_narrative_plan}}`
    2. Generate a business strategy for the game covering monetization and marketing. Tailor this to the Roblox platform.

    ### Final Output:
    A comprehensive marketing strategy that includes:
    a. Monetization Strategy
    b. Marketing Plan
	""",
    output_key="marketing_strategy",
	include_contents='default',
	planner=BuiltInPlanner(
        thinking_config=types.ThinkingConfig(
            include_thoughts=False,
            thinking_budget=1024,
        )
    ),
)

producer = LlmAgent(
	name="Producer",
	model=config.designer_model,
	description="Plans a timeline and task list given a game design document.",
	instruction=f"""
	You are a meticulously organized video game producer. Review the information and develop a game plan for tackling all of the required tasks.

	{ team_agreement }

    ### INPUT DATA:
    *   Game Overview: `{{game_overview}}`
    *   Gameplay Plan: `{{gameplay_plan}}`
    *   Art and Narrative Plan: `{{art_narrative_plan}}`
    *   Marketing Strategy: `{{marketing_strategy}}`
    
    ### TASK:
    Your task is to use the provided information to generate a detailed project plan, including task list and timeline.

    ### Final Output:
    A comprehensive production plan that includes:
    a. Task List
    b. Timeline
    c. Milestones
    d. MVP Definition (conservative)
	""",
    output_key="production_plan",
	include_contents='default',
	planner=BuiltInPlanner(
        thinking_config=types.ThinkingConfig(
            include_thoughts=False,
            thinking_budget=1024,
        )
    ),
)

# Plan Synthesizer not very useful, best to just unify the sections with code at the end.. probably just have this agent call a tool
plan_synthesizer = LlmAgent(
	name="PlanSynthesizer",
	model=config.worker_model,
	description="Unifies all content into a coherent Game Design Document.",
	instruction="""
    Transform the provided information into a polished, professional, beautiful Game Design Document.
	### INPUT DATA:
    *   Game Overview: `{game_overview}`
    *   Gameplay Plan: `{gameplay_plan}`
    *   Art and Narrative Plan: `{art_narrative_plan}`
	*   Marketing Strategy: `{marketing_strategy}`
    *   Production Plan: `{production_plan}`
    
    ## Final Instructions:
    Generate a comprehensive Game Design Document that incorporates all the above elements. Return only this document.
	""",
	include_contents='default',
	# planner=BuiltInPlanner(
    #     thinking_config=types.ThinkingConfig(
    #         include_thoughts=False,
    #         thinking_budget=1024,
    #     )
    # ),
)

# Idea: Use LoopAgent with human-in-the-loop tool for iteration and refinement
project_pipeline = SequentialAgent(
	name="ProjectPipeline",
	sub_agents=[
        gameplay_designer,
		LoopAgent(
			name="gameplay_refinement_loop",
			max_iterations=config.max_gameplay_design_iterations,
			sub_agents=[
				gameplay_evaluator,
				EscalationChecker(name="escalation_checker"),
				gameplay_refiner,
			],
		),
		art_director,
		marketing_director,
        producer,
		# plan_synthesizer
	]
)



interactive_planner_agent = LlmAgent(
    name="interactive_planner_agent",
    model=config.worker_model,
    description="The primary game design agent. Collaborates with the directing user and then executes the project design.",
    instruction=f"""
    You are a game design assistant. Your primary function is to convert ANY user request into a game design overview.

    { team_agreement }
    
    **Tone:** Sophisticated, inquisitive, professional, creative.

    Your workflow is:
	1. **Discuss:** Collaborate with the user to gather requirements and understand their vision.
    1.  **Plan:** You MUST use `lead_game_designer` to create a game design overview and present it to the user (stored in the `game_overview` state key).
    2.  **Refine:** Incorporate user feedback until the plan is approved. ALWAYS call `lead_game_designer` to do this. Be sure to ask the user for confirmation when you are clear on the vision.
    3.  **Execute:** Once the user gives EXPLICIT approval (e.g., "looks good, run it"), you MUST delegate the task to the `project_pipeline` agent, passing the approved plan.

    Your job is to Plan, Refine, and Delegate. When a `game_overview` is generated, you MUST return it in your response.
    """,
    sub_agents=[project_pipeline],
    tools=[AgentTool(lead_game_designer)],
)

root_agent = interactive_planner_agent