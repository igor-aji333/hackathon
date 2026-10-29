import asyncio
import os
import sys
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI
from openinference.instrumentation.langchain import LangChainInstrumentor
import phoenix.otel

# Load environment walking up to root
load_dotenv()

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


class AirportAgent:
    """Agent connected to the Airport MCP server over stdio."""

    def __init__(
        self,
        system_prompt_version: str = "v1",
        project_name: str = "airport-mcp-eval",
        endpoint: str = "http://localhost:4317",
    ):
        self.version = system_prompt_version
        self.project_name = project_name
        self.endpoint = endpoint
        self.client: MultiServerMCPClient | None = None
        self.agent_executor = None

    def _load_system_prompt(self) -> str:
        prompt_path = (
            Path(__file__).parent / "prompts" / f"system_prompt_{self.version}.txt"
        )
        if not prompt_path.exists():
            raise FileNotFoundError(f"Prompt file not found: {prompt_path}")
        return prompt_path.read_text(encoding="utf-8")

    async def initialize(self) -> None:
        # Instrument Phoenix OpenTelemetry
        tracer_provider = phoenix.otel.register(
            project_name=self.project_name,
            endpoint=self.endpoint,
        )
        LangChainInstrumentor().instrument(tracer_provider=tracer_provider)

        # Launch the MCP server over stdio
        self.client = MultiServerMCPClient({
            "airport_server": {
                "transport": "stdio",
                "command": sys.executable,
                "args": ["-m", "airport_mcp.server"],
                "cwd": REPO_ROOT,
            }
        })

        tools = await self.client.get_tools()

        base_url = os.getenv("USAI_BASE_URL", "").rstrip("/")
        if base_url and not base_url.endswith("/api/v1"):
            base_url = f"{base_url}/api/v1"

        llm = ChatOpenAI(
            model=os.getenv("AGENT_MODEL", "gpt-4o"),
            api_key=os.getenv("USAI_API_KEY"),
            base_url=base_url if base_url else None,
            temperature=0.0,
        )

        self.agent_executor = create_agent(
            model=llm,
            tools=tools,
            system_prompt=self._load_system_prompt(),
        )

    async def run(self, query: str) -> str:
        if not self.agent_executor:
            await self.initialize()

        result = await self.agent_executor.ainvoke({"messages": [("user", query)]})
        # Extract the last message output
        messages = result.get("messages", [])
        if messages:
            return messages[-1].content
        return str(result)

    def create_experiment_task(self):
        """Returns a synchronous execution closure required by Phoenix experiments."""
        def task(example: Any) -> Dict[str, Any]:
            # Handles Phoenix Example schema where input dict keys map to query
            query = example.input.get("query")
            output_text = asyncio.run(self.run(query))
            return {"responses": output_text}

        return task


if __name__ == "__main__":
    async def _test():
        agent = AirportAgent(system_prompt_version="v1")
        await agent.initialize()
        resp = await agent.run("What is the length of runway 04L/22R at JFK?")
        print("Response:", resp)

    asyncio.run(_test())
