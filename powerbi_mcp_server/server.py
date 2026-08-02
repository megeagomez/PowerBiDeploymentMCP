"""
Main MCP Server Entry Point

This module implements the Power BI MCP server that exposes tools for managing
Power BI assets including semantic models and reports.
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, CallToolResult

from powerbi_mcp_server.logging_config import setup_logging
from powerbi_mcp_server.metadata import MetadataManager
from powerbi_mcp_server.tools import TOOL_SCHEMAS, ToolHandlers
from powerbi_mcp_server.resources import ResourceProviders, RESOURCE_TEMPLATES
from powerbi_mcp_server.prompts import PromptHandlers, PROMPTS
from powerbi_mcp_server.auth import get_authenticator
from powerbi_mcp_server.auth.authenticator import AuthenticationRequired

logger = logging.getLogger(__name__)


class PowerBIMCPServer:
    """Power BI MCP Server implementation"""
    
    def __init__(self):
        log_file = Path.home() / ".powerbi-mcp-deployment" / "logs" / "server.log"
        setup_logging(log_file=log_file)
        self.server = Server("powerbi-mcp-deployment")
        self.metadata_manager = MetadataManager()
        self.tool_handlers = ToolHandlers(self.metadata_manager)
        self.auth_manager = get_authenticator()
        self.resource_providers = ResourceProviders(self.metadata_manager, self.auth_manager)
        self.prompt_handlers = PromptHandlers(self.metadata_manager, self.tool_handlers)
        logger.info("Power BI MCP Server created")
    
    async def initialize(self) -> None:
        """Initialize the server and register tools, resources, and prompts"""
        logger.info("Initializing Power BI MCP Server")

        # Initialize metadata database
        await self.metadata_manager.initialize()

        # Register tools, resources and prompts
        self._register_tools()
        self._register_resources()
        self._register_prompts()

        logger.info("Power BI MCP Server initialization complete")

    def _register_tools(self) -> None:
        """Register all MCP tools using the 1.x list_tools/call_tool API"""

        @self.server.list_tools()
        async def list_tools():
            tools = []
            for tool_name, schema in TOOL_SCHEMAS.items():
                tools.append(Tool(
                    name=schema["name"],
                    description=schema["description"],
                    inputSchema=schema["inputSchema"],
                ))
            logger.info(f"Listed {len(tools)} tools")
            return tools

        @self.server.call_tool()
        async def call_tool(name: str, arguments: Dict[str, Any]):
            logger.info(f"Executing tool: {name}")
            logger.debug(f"Arguments: {arguments}")

            # Only registered tools are callable — never dispatch arbitrary
            # attribute names (e.g. private handler methods) via getattr
            if name not in TOOL_SCHEMAS:
                msg = f"Unknown tool: {name}"
                logger.error(msg)
                return [TextContent(type="text", text=json.dumps({"success": False, "error": msg}))]

            try:
                handler_method = getattr(self.tool_handlers, name)
                result = await handler_method(arguments or {})
                logger.info(f"Tool {name} completed successfully")
                return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]
            except AttributeError:
                msg = f"Unknown tool: {name}"
                logger.error(msg)
                return [TextContent(type="text", text=json.dumps({"success": False, "error": msg}))]
            except AuthenticationRequired as e:
                logger.info(f"Tool {name} requires authentication")
                return [TextContent(type="text", text=json.dumps({
                    "success": False,
                    "error": str(e),
                    "action_required": "Llama a la herramienta `authenticate` para iniciar sesión con Microsoft."
                }))]
            except Exception as e:
                logger.error(f"Tool {name} failed: {e}", exc_info=True)
                return [TextContent(type="text", text=json.dumps({
                    "success": False, "error": str(e), "error_type": type(e).__name__
                }))]

        logger.info(f"Registered {len(TOOL_SCHEMAS)} tools")
    
    def _register_resources(self) -> None:
        """Register all MCP resources"""
        @self.server.list_resources()
        async def list_resources():
            """List available resources"""
            resources = []
            for key, template in RESOURCE_TEMPLATES.items():
                resources.append({
                    'uri': template['uri'],
                    'name': template['name'],
                    'description': template['description'],
                    'mimeType': template['mimeType']
                })
            logger.info(f"Listed {len(resources)} resources")
            return resources
        
        @self.server.read_resource()
        async def read_resource(uri: str):
            """Read a specific resource"""
            logger.info(f"Reading resource: {uri}")
            
            try:
                # Server config
                if uri == 'config://server':
                    content = self.resource_providers.get_server_config()
                    return json.dumps(content, indent=2, default=str)
                
                # Auth status
                elif uri == 'auth://status':
                    content = self.resource_providers.get_auth_status()
                    return json.dumps(content, indent=2, default=str)
                
                # Metadata stats
                elif uri == 'metadata://stats':
                    content = self.resource_providers.get_metadata_stats()
                    return json.dumps(content, indent=2, default=str)
                
                # Recent deployments
                elif uri == 'deployments://recent':
                    content = self.resource_providers.get_recent_deployments()
                    return json.dumps(content, indent=2, default=str)
                
                # Workspace summary
                elif uri == 'workspaces://summary':
                    content = self.resource_providers.get_workspace_summary()
                    return json.dumps(content, indent=2, default=str)
                
                # Deployment configs
                elif uri == 'config://deployments':
                    content = self.resource_providers.get_deployment_configs()
                    return json.dumps(content, indent=2, default=str)
                
                # Deployment history for workspace
                elif uri.startswith('deployments://'):
                    workspace_name = uri.replace('deployments://', '')
                    content = self.resource_providers.get_deployment_history(workspace_name)
                    return json.dumps(content, indent=2, default=str)
                
                else:
                    raise ValueError(f"Unknown resource URI: {uri}")
                    
            except Exception as e:
                logger.error(f"Error reading resource {uri}: {e}")
                return json.dumps({'error': str(e)}, indent=2)
        
        logger.info("Registered resources")
    
    def _register_prompts(self) -> None:
        """Register all MCP prompts"""
        @self.server.list_prompts()
        async def list_prompts():
            """List available prompts"""
            prompts = []
            for prompt_key, prompt_def in PROMPTS.items():
                prompts.append({
                    'name': prompt_def['name'],
                    'description': prompt_def['description'],
                    'arguments': prompt_def.get('arguments', [])
                })
            logger.info(f"Listed {len(prompts)} prompts")
            return prompts
        
        @self.server.get_prompt()
        async def get_prompt(name: str, arguments: Dict[str, Any] = None):
            """Get a specific prompt with arguments"""
            logger.info(f"Getting prompt: {name}")
            
            if arguments is None:
                arguments = {}
            
            try:
                # Map prompt name to handler method
                if name == 'backup-workspace':
                    content = await self.prompt_handlers.backup_workspace(arguments)
                elif name == 'deploy-workspace':
                    content = await self.prompt_handlers.deploy_workspace(arguments)
                elif name == 'sync-local-to-cloud':
                    content = await self.prompt_handlers.sync_local_to_cloud(arguments)
                elif name == 'migrate-report':
                    content = await self.prompt_handlers.migrate_report(arguments)
                elif name == 'deployment-pipeline':
                    content = await self.prompt_handlers.deployment_pipeline(arguments)
                elif name == 'configure-deployment':
                    content = await self.prompt_handlers.configure_deployment(arguments)
                else:
                    raise ValueError(f"Unknown prompt: {name}")
                
                return {
                    'description': PROMPTS[name]['description'],
                    'messages': [
                        {
                            'role': 'user',
                            'content': {
                                'type': 'text',
                                'text': content
                            }
                        }
                    ]
                }
                
            except Exception as e:
                logger.error(f"Error getting prompt {name}: {e}")
                return {
                    'description': f"Error: {str(e)}",
                    'messages': [
                        {
                            'role': 'user',
                            'content': {
                                'type': 'text',
                                'text': f"Error generating prompt: {str(e)}"
                            }
                        }
                    ]
                }
        
        logger.info("Registered prompts")
    
    async def cleanup(self) -> None:
        """Cleanup resources before server shutdown"""
        logger.info("Cleaning up Power BI MCP Server")
        await self.metadata_manager.close()


async def run_server():
    """Async entry point for the Power BI MCP Server"""
    server_instance = PowerBIMCPServer()
    await server_instance.initialize()

    try:
        async with stdio_server() as (read_stream, write_stream):
            logger.info("Power BI MCP Server started on stdio")
            await server_instance.server.run(
                read_stream,
                write_stream,
                server_instance.server.create_initialization_options()
            )
    finally:
        await server_instance.cleanup()
        logger.info("Power BI MCP Server stopped")


def main():
    """Synchronous entry point for console_scripts/uvx"""
    asyncio.run(run_server())


if __name__ == "__main__":
    main()
