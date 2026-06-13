#!/bin/bash

# NeuroWeave Quick Start Script
set -e

echo "🚀 NeuroWeave - Quick Start Setup"
echo "=================================="

# Check prerequisites
check_prerequisites() {
    echo "Checking prerequisites..."
    
    # Check Python
    if ! command -v python3 &> /dev/null; then
        echo "❌ Python 3 is not installed"
        exit 1
    fi
    echo "✓ Python 3: $(python3 --version)"
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        echo "❌ Docker is not installed"
        exit 1
    fi
    echo "✓ Docker: $(docker --version)"
    
    # Check Docker Compose
    if ! command -v docker-compose &> /dev/null; then
        echo "❌ Docker Compose is not installed"
        exit 1
    fi
    echo "✓ Docker Compose: $(docker-compose --version)"
}

# Setup environment
setup_environment() {
    echo ""
    echo "Setting up environment..."
    
    if [ ! -f .env ]; then
        echo "Creating .env from template..."
        cp .env.example .env
        echo "⚠️  Please update .env with your OpenAI API key"
        echo ""
        read -p "Enter your OpenAI API key: " api_key
        sed -i "s/OPENAI_API_KEY=.*/OPENAI_API_KEY=$api_key/" .env
        echo "✓ Environment configured"
    else
        echo "✓ .env already exists"
    fi
}

# Install dependencies
install_dependencies() {
    echo ""
    echo "Installing Python dependencies..."
    pip install -r requirements.txt
    echo "✓ Dependencies installed"
}

# Start services
start_services() {
    echo ""
    echo "Starting Docker services..."
    docker-compose up -d
    
    echo "⏳ Waiting for services to be healthy..."
    sleep 15
    
    # Check health
    if ! docker-compose exec -T neuroweave curl -s http://localhost:8000/health &> /dev/null; then
        echo "⚠️  API not responding yet, waiting..."
        sleep 5
    fi
    
    echo "✓ Services started"
}

# Run migrations
run_migrations() {
    echo ""
    echo "Running database migrations..."
    docker-compose exec -T neuroweave alembic upgrade head
    echo "✓ Migrations completed"
}

# Verify installation
verify_installation() {
    echo ""
    echo "Verifying installation..."
    
    # Check API health
    if curl -s http://localhost:8000/health > /dev/null; then
        echo "✓ API is healthy"
    else
        echo "❌ API health check failed"
        exit 1
    fi
    
    # Check database
    if docker-compose exec -T postgres psql -U neuroweave -d neuroweave -c "SELECT 1" &> /dev/null; then
        echo "✓ Database is accessible"
    else
        echo "❌ Database check failed"
        exit 1
    fi
    
    # Check Redis
    if docker-compose exec -T redis redis-cli ping &> /dev/null; then
        echo "✓ Redis is accessible"
    else
        echo "❌ Redis check failed"
        exit 1
    fi
}

# Main execution
main() {
    check_prerequisites
    setup_environment
    install_dependencies
    start_services
    run_migrations
    verify_installation
    
    echo ""
    echo "=================================="
    echo "✅ NeuroWeave is ready!"
    echo "=================================="
    echo ""
    echo "📚 Quick Links:"
    echo "  - API Documentation: http://localhost:8000/docs"
    echo "  - Health Check: http://localhost:8000/health"
    echo "  - PostgreSQL: localhost:5432"
    echo "  - Redis: localhost:6379"
    echo ""
    echo "📖 Documentation:"
    echo "  - README.md - Project overview"
    echo "  - ARCHITECTURE.md - Design decisions"
    echo "  - DEPLOYMENT.md - Production deployment"
    echo "  - examples.py - API examples"
    echo ""
    echo "🚀 Next Steps:"
    echo "  1. Review examples.py for API usage"
    echo "  2. Try POST /memory/ingest endpoint"
    echo "  3. Try POST /memory/retrieve endpoint"
    echo ""
    echo "💡 Tips:"
    echo "  - View logs: docker-compose logs -f neuroweave"
    echo "  - Stop services: docker-compose down"
    echo "  - Run tests: pytest"
    echo ""
}

main
