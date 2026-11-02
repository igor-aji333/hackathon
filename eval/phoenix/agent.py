import asyncio
import os
import sys
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv
from langchain.agents import create_agent
from contextlib import AsyncExitStack
from mcp import StdioServerParameters
from langchain.mcp import MCPAdapter
from langchain_openai import ChatOpenAI
from openinference.instrumentation.langchain import LangChainInstrumentor
import phoenix.otel

from mcp import StdioServerParameters
from langchain.mcp import MCPAdapter
from airport_mcp.server import mcp as airport_server_app

_OTEL_INITIALIZED = False

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
        global _OTEL_INITIALIZED
        if not _OTEL_INITIALIZED:
            # Instrument Phoenix OpenTelemetry once for the whole experiment
            tracer_provider = phoenix.otel.register(
                project_name=self.project_name,
                endpoint=self.endpoint,
            )
            LangChainInstrumentor().instrument(tracer_provider=tracer_provider)
            _OTEL_INITIALIZED = True

        # Launch the MCP server in-memory to bypass stdio transport inference bugs
        self.stack = AsyncExitStack()
        self.adapter = await self.stack.enter_async_context(MCPAdapter(airport_server_app))
        tools = await self.adapter.list_tools()
        
        # Remove these lines:
        # base_url = os.getenv("USAI_BASE_URL", "").rstrip("/")
        # if base_url and not base_url.endswith("/api/v1"):
        #     base_url = f"{base_url}/api/v1"
        
        # Replace with:
        base_url = os.getenv("USAI_BASE_URL", "").rstrip("/")

        llm = ChatOpenAI(
            model=os.getenv("AGENT_MODEL", "llama3.1"),
            api_key=os.getenv("USAI_API_KEY", "ollama"),
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
            
        try:
            result = await self.agent_executor.ainvoke({"messages": [("user", query)]})
            
            # Extract the last message output
            messages = result.get("messages", [])
            if messages:
                return messages[-1].content
            return str(result)
        finally:
            # Gracefully shut down the in-memory MCP server before the event loop closes
            if hasattr(self, "stack") and self.stack:
                await self.stack.aclose()
                
    def create_experiment_task(self):
        """Returns a synchronous execution closure required by Phoenix experiments."""
        def task(example: Any) -> Dict[str, Any]:
            query = example.input.get("query")
            
            # Create a fresh agent instance for this thread's event loop
            local_agent = AirportAgent(
                system_prompt_version=self.version,
                project_name=self.project_name,
                endpoint=self.endpoint,
            )
            
            output_text = asyncio.run(local_agent.run(query))
            return {"responses": output_text}
        return task
    
if __name__ == "__main__":
    async def _test():
        agent = AirportAgent(system_prompt_version="v1")
        await agent.initialize()
        resp = await agent.run("What is the length of runway 04L/22R at JFK?")
        print("Response:", resp)

    asyncio.run(_test())
