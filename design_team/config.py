class Configuration():
	worker_model: str = "gemini-2.0-flash"
	designer_model: str = "gemini-2.5-pro"
	max_gameplay_design_iterations: int = 5

config = Configuration()
APP_NAME = "game_design_team_app"