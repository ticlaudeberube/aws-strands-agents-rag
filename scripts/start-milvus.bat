@echo off
REM Quick start script for AWS Strands Agents RAG (Windows)

echo ======================================
echo AWS Strands Agents RAG - Quick Start
echo ======================================
echo.

echo Starting Milvus services...
docker-compose -f docker/docker-compose.yml up -d

echo Waiting for Milvus to be ready...
timeout /t 5 /nobreak

echo.
echo ======================================
echo Milvus Started Successfully!
echo ======================================
echo.
echo Next: Start Ollama in a new terminal
echo.
echo Download and run Ollama from: https://ollama.ai
echo.
echo Then pull models (in new terminal):
echo   ollama pull qwen2.5:0.5b
echo   ollama pull nomic-embed-text:v1.5
echo.
echo Finally, test the setup:
echo   python main.py
echo.
echo Run examples:
echo   python examples/basic_rag.py
echo   python examples/interactive_chat.py
echo.
echo To stop services:
echo   docker-compose -f docker/docker-compose.yml down
echo.
pause
