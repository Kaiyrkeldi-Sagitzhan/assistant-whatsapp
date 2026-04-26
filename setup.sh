#!/bin/bash
set -e

echo "🚀 Task Assistant — Local Development Setup"
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo "📝 Creating .env from .env.example..."
    cp .env.example .env
    echo "⚠️  Please edit .env with your actual credentials (Gemini API key, WhatsApp tokens)."
fi

echo ""
echo "📦 Starting Docker services..."
docker compose up --build -d

echo ""
echo "⏳ Waiting for PostgreSQL..."
sleep 5

echo ""
echo "🗄️  Running database migrations..."
docker compose exec -T api alembic upgrade head

echo ""
echo "✅ Setup complete!"
echo ""
echo "📻 Available endpoints:"
echo "  • API: http://localhost:8000"
echo "  • Health check: http://localhost:8000/healthz"
echo "  • API docs: http://localhost:8000/docs"
echo ""
echo "📋 To see logs:"
echo "  docker compose logs -f api"
echo "  docker compose logs -f worker"
echo ""
echo "🛑 To stop:"
echo "  docker compose down"
