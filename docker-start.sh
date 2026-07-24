#!/bin/bash
set -e

echo "Starting NeuroWeave stack..."

# Load environment
if [ ! -f .env ]; then
    echo "Creating .env file from template..."
    cp .env.example .env
    echo "⚠️  Please update .env with your OpenAI API key"
fi

# Start services
docker-compose up -d

echo "⏳ Waiting for services to be healthy..."
sleep 10

# Run migrations
echo "Running database migrations..."
docker-compose exec -T neuroweave alembic -c migrations/alembic.ini upgrade head

echo "✅ NeuroWeave is running!"
echo "📚 API Documentation: http://localhost:8000/docs"
echo "❤️  Health Check: http://localhost:8000/health"
