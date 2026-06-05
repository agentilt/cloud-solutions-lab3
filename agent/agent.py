"""Strands Agent deployed to Bedrock AgentCore Runtime.

Replace SYSTEM_PROMPT and the tools in tools.py with the group's chosen use case.
"""
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from strands import Agent

from tools import lookup_record, record_event

SYSTEM_PROMPT = (
    "You are a helpful assistant. Use the provided tools to look up information "
    "and record events when relevant. Be concise and explain your reasoning when "
    "the user asks. If a tool call fails, explain what went wrong rather than "
    "fabricating an answer."
)

agent = Agent(
    system_prompt=SYSTEM_PROMPT,
    tools=[lookup_record, record_event],
)

app = BedrockAgentCoreApp()


@app.entrypoint
def invoke(payload: dict) -> dict:
    prompt = payload.get("prompt", "")
    result = agent(prompt)
    return {"response": str(result)}


if __name__ == "__main__":
    app.run()
