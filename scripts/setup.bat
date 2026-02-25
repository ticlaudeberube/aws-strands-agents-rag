@echo off
REM Setup script for AWS Strands Agents RAG (Windows)

echo ===================================
echo AWS Strands Agents RAG Setup
echo ===================================
echo.

REM Check Python version
echo Checking Python version...
python --version
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set python_version=%%i

REM Check Docker
echo.
echo Checking Docker installation...
where docker >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo Error: Docker is not installed
    exit /b 1
)
echo Docker is installed

REM Check Docker Compose
echo Checking Docker Compose...
where docker-compose >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    docker compose version >nul 2>nul
    if %ERRORLEVEL% NEQ 0 (
        echo Error: Docker Compose is not installed
        exit /b 1
    )
    set DOCKER_COMPOSE_CMD=docker compose
) else (
    set DOCKER_COMPOSE_CMD=docker-compose
)
echo Docker Compose is available: %DOCKER_COMPOSE_CMD%

REM Check Ollama
echo.
echo Checking Ollama installation...
where ollama >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo Warning: Ollama is not in PATH
    echo Please download from https://ollama.ai and install
) else (
    echo Ollama is installed
)

REM Setup Python environment
echo.
echo Setting up Python environment...
pip install -e .

echo.
echo Installing development dependencies...
pip install -e ".[dev]"

REM Create .env file if it doesn't exist
echo.
if not exist .env (
    echo Creating .env file from template...
    copy .env.example .env
    echo Created .env (update with your configuration)
) else (
    echo .env file already exists
)

REM Summary
echo.
echo ===================================
echo Setup Complete!
echo ===================================
echo.
echo Next steps:
echo 1. Start Milvus:
echo    %DOCKER_COMPOSE_CMD% -f docker/docker-compose.yml up -d
echo.
echo 2. Start Ollama (in a separate terminal):
echo    ollama serve
echo.
echo 3. Pull Ollama models (in another terminal):
echo    ollama pull mistral
echo    ollama pull all-minilm
echo.
echo 4. Run examples:
echo    python examples/basic_rag.py
echo    python examples/interactive_chat.py
echo.
echo Documentation: see README.md
echo.
