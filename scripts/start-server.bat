@echo off
REM Power BI MCP Deployment Server Startup Script for Windows

echo Starting Power BI MCP Deployment Server...

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo Error: Python is not installed or not in PATH
    exit /b 1
)

REM Check if powerbi-mcp-deployment is installed
python -c "import powerbi_mcp_server" >nul 2>&1
if errorlevel 1 (
    echo Error: powerbi-mcp-deployment package is not installed
    echo Run: pip install powerbi-mcp-deployment
    exit /b 1
)

REM Start the server
python -m powerbi_mcp_server.server

if errorlevel 1 (
    echo Server stopped with error
    exit /b 1
)

echo Server stopped
