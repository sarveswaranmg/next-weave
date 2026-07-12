"""
Dream Scheduler

Decides when to run offline consolidation and for which users — respecting
a per-user cooldown, idle-activity detection, and a bounded compute budget
per tick, so dream sessions never compete with live inference latency.
"""
import logging
from datetime import datetime, timedelta
from typing import List
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.models import Memory, DreamSession, DreamSessionStatusEnum, PredictiveRecallLog, ContextSnapshot
from app.core.config import settings

logger = logging.getLogger(__name__)

EPOCH = datetime(2000, 1, 1)  # "beginning of time" for growth-score comparisons


class DreamScheduler:
    """Selects which users are eligible for a dream session right now."""

    def __init__(self, session: Session):
        self.session = session

    def eligible_users(self, trigger: str = "manual", limit: int = None) -> List[UUID]:
        """
        Args:
            trigger: "hourly", "daily", "weekly", "idle", or "manual"
            limit: Max users to return this tick (compute budget)

        Returns:
            User IDs eligible for a dream session, prioritized by how much
            new memory they've accumulated since their last completed session.
        """
        limit = limit or settings.dream_max_users_per_scheduler_tick

        candidate_ids = [row[0] for row in self.session.query(Memory.user_id).distinct().all()]

        eligible = []
        for user_id in candidate_ids:
            if not self._cooldown_elapsed(user_id):
                continue
            if trigger == "idle" and not self._is_idle(user_id):
                continue
            eligible.append(user_id)

        eligible.sort(key=lambda uid: self._growth_score(uid), reverse=True)
        return eligible[:limit]

    def is_running(self, user_id: UUID) -> bool:
        """Whether a dream session is currently in-flight for this user
        (prevents overlapping sessions for the same user)."""
        running = self.session.query(DreamSession).filter(
            DreamSession.user_id == user_id,
            DreamSession.status == DreamSessionStatusEnum.RUNNING,
        ).first()
        return running is not None

    def _cooldown_elapsed(self, user_id: UUID) -> bool:
        last = self.session.query(DreamSession).filter(
            DreamSession.user_id == user_id,
        ).order_by(DreamSession.started_at.desc()).first()
        if not last:
            return True
        if last.status == DreamSessionStatusEnum.RUNNING:
            return False
        cooldown = timedelta(hours=settings.dream_min_hours_between_sessions)
        return (datetime.utcnow() - last.started_at) >= cooldown

    def _is_idle(self, user_id: UUID) -> bool:
        """No live retrieval/composition activity in the idle window."""
        cutoff = datetime.utcnow() - timedelta(minutes=settings.dream_idle_minutes_threshold)
        recent_recall = self.session.query(PredictiveRecallLog).filter(
            PredictiveRecallLog.user_id == user_id, PredictiveRecallLog.created_at >= cutoff,
        ).first()
        if recent_recall:
            return False
        recent_context = self.session.query(ContextSnapshot).filter(
            ContextSnapshot.user_id == user_id, ContextSnapshot.created_at >= cutoff,
        ).first()
        return recent_context is None

    def _growth_score(self, user_id: UUID) -> int:
        last = self.session.query(DreamSession).filter(
            DreamSession.user_id == user_id, DreamSession.status == DreamSessionStatusEnum.COMPLETED,
        ).order_by(DreamSession.started_at.desc()).first()
        since = last.finished_at if (last and last.finished_at) else EPOCH
        return self.session.query(func.count(Memory.id)).filter(
            Memory.user_id == user_id, Memory.created_at >= since,
        ).scalar() or 0
