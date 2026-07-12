"""
Environmental Context Engine

Represents the user's actual development environment: operating system,
IDE, cloud providers, repositories, databases, deployment targets, and
integrations — drawn from DEVICE/SERVICE/REPOSITORY/TECHNOLOGY world
entities already extracted by `EntityExtractor`, organized into a
structured summary that enables smarter, environment-aware assistance.
"""
import logging
from typing import Dict
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import WorldEntity, WorldEntityTypeEnum

logger = logging.getLogger(__name__)

DATABASE_TECH_NAMES = {"postgresql", "mysql", "mongodb", "redis", "sqlite", "elasticsearch"}
DEPLOYMENT_SERVICE_NAMES = {"aws", "gcp", "azure", "vercel", "heroku", "netlify", "cloudflare"}
IDE_DEVICE_NAMES = {"vs code", "vim", "neovim", "pycharm", "intellij", "xcode", "cursor"}
OS_DEVICE_NAMES = {"macos", "windows", "ubuntu", "linux"}


class EnvironmentalContextEngine:
    """Summarizes the user's development environment from world entities."""

    def __init__(self, session: Session):
        self.session = session

    def get_environment(self, user_id: UUID) -> Dict:
        devices = self.session.query(WorldEntity).filter(
            WorldEntity.user_id == user_id, WorldEntity.entity_type == WorldEntityTypeEnum.DEVICE,
        ).all()
        services = self.session.query(WorldEntity).filter(
            WorldEntity.user_id == user_id, WorldEntity.entity_type == WorldEntityTypeEnum.SERVICE,
        ).all()
        technologies = self.session.query(WorldEntity).filter(
            WorldEntity.user_id == user_id, WorldEntity.entity_type == WorldEntityTypeEnum.TECHNOLOGY,
        ).all()
        repositories = self.session.query(WorldEntity).filter(
            WorldEntity.user_id == user_id, WorldEntity.entity_type == WorldEntityTypeEnum.REPOSITORY,
        ).all()

        operating_system = [d.entity_name for d in devices if d.entity_name.lower() in OS_DEVICE_NAMES]
        ide = [d.entity_name for d in devices if d.entity_name.lower() in IDE_DEVICE_NAMES]
        cloud_providers = [s.entity_name for s in services if s.entity_name.lower() in DEPLOYMENT_SERVICE_NAMES]
        integrations = [s.entity_name for s in services if s.entity_name.lower() not in DEPLOYMENT_SERVICE_NAMES]
        databases = [t.entity_name for t in technologies if t.entity_name.lower() in DATABASE_TECH_NAMES]

        return {
            "operating_system": operating_system,
            "ide": ide,
            "cloud_providers": cloud_providers,
            "integrations": integrations,
            "databases": databases,
            "repositories": [r.entity_name for r in repositories],
            "deployment_targets": cloud_providers,
        }
