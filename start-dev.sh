#!/bin/bash

# Game Design Team - Development Startup Script

echo "🎮 Starting Game Design Team Application"
echo "========================================"

# Check if Python virtual environment exists
if [ ! -d ".venv" ]; then
    echo "❌ Virtual environment not found. Please run:"
    echo "   python -m venv .venv"
    echo "   source .venv/bin/activate"
    echo "   pip install -r design_team/requirements.txt"
    exit 1
fi

# Function to cleanup background processes
cleanup() {
    echo "🛑 Shutting down services..."
    kill $BACKEND_PID 2>/dev/null
    kill $FRONTEND_PID 2>/dev/null
    exit 0
}

# Set up signal handlers
trap cleanup SIGINT SIGTERM

echo "🚀 Starting backend server..."
# Start the Python backend
.venv/bin/python -m uvicorn design_team.server:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

# Wait a moment for backend to start
sleep 3

echo "🌐 Starting frontend development server..."
# Start the frontend (assuming pnpm is installed)
cd frontend

# Check if node_modules exists
if [ ! -d "node_modules" ]; then
    echo "📦 Installing frontend dependencies..."
    pnpm install
fi

# Start frontend dev server
pnpm dev &
FRONTEND_PID=$!

cd ..

echo "✅ Services started successfully!"
echo ""
echo "🔗 Application URLs:"
echo "   Frontend: http://localhost:5173"
echo "   Backend:  http://localhost:8000"
echo "   API Docs: http://localhost:8000/docs"
echo ""
echo "📊 Database: design_team_sessions.db"
echo ""
echo "Press Ctrl+C to stop all services"

# Wait for either process to exit
wait
