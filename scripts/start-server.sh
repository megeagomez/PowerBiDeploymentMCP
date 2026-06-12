#!/bin/bash
# Power BI MCP Deployment Server Startup Script for Unix/Linux/macOS

echo "Starting Power BI MCP Deployment Server..."

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed or not in PATH"
    exit 1
fi

# Check if powerbi-mcp-deployment is installed
python3 -c "import powerbi_mcp_server" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "Error: powerbi-mcp-deployment package is not installed"
    echo "Run: pip install powerbi-mcp-deployment"
    exit 1
fi

# Start the server
python3 -m powerbi_mcp_server.server

if [ $? -ne 0 ]; then
    echo "Server stopped with error"
    exit 1
fi

echo "Server stopped"
