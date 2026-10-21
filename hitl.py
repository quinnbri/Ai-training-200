"""Human-in-the-Loop (HITL) Verification Hooks for Cloud FinOps Copilot.

Manages review queues for high-impact SRE & FinOps recommendations (e.g., GPU
autoscaler caps, BigQuery partition enforcement, or GKE deployment rollbacks).
Requires explicit sign-off from a human SRE/FinOps lead before execution.
"""

import time
import uuid
from typing import Any, Dict, List, Optional


class HITLController:
    """Manages pending human review workflows and SRE/FinOps sign-offs."""

    def __init__(self) -> None:
        self.pending_reviews: Dict[str, Dict[str, Any]] = {}
        self.approved_reviews: Dict[str, Dict[str, Any]] = {}
        self.rejected_reviews: Dict[str, Dict[str, Any]] = {}

    def submit_for_review(
        self, recommendation: Dict[str, Any], run_id: Optional[str] = None
    ) -> str:
        """Places a high-impact FinOps remediation into the HITL pending queue."""
        review_id = f"HITL-{uuid.uuid4().hex[:8].upper()}"
        payload = dict(recommendation)
        payload["review_id"] = review_id
        payload["run_id"] = run_id or "ACTIVE_RUN"
        payload["submitted_at"] = time.time()
        payload["review_status"] = "PENDING_HUMAN_REVIEW"
        self.pending_reviews[review_id] = payload
        return review_id

    def approve_recommendation(
        self,
        review_id: str,
        reviewer_id: str = "Principal_FinOps_SRE_Lead",
        comment: str = "Approved for production rollout.",
    ) -> Optional[Dict[str, Any]]:
        """Approves a pending FinOps review item."""
        if review_id not in self.pending_reviews:
            return None
        item = self.pending_reviews.pop(review_id)
        item["review_status"] = "APPROVED"
        item["reviewed_by"] = reviewer_id
        item["reviewer_comment"] = comment
        item["reviewed_at"] = time.time()
        self.approved_reviews[review_id] = item
        return item

    def reject_recommendation(
        self,
        review_id: str,
        reviewer_id: str = "Principal_FinOps_SRE_Lead",
        reason: str = "Deferred until post-peak traffic freeze window.",
    ) -> Optional[Dict[str, Any]]:
        """Rejects a pending FinOps review item."""
        if review_id not in self.pending_reviews:
            return None
        item = self.pending_reviews.pop(review_id)
        item["review_status"] = "REJECTED"
        item["reviewed_by"] = reviewer_id
        item["rejection_reason"] = reason
        item["reviewed_at"] = time.time()
        self.rejected_reviews[review_id] = item
        return item

    def get_pending_reviews(self) -> List[Dict[str, Any]]:
        """Returns all pending remediations awaiting human sign-off."""
        return list(self.pending_reviews.values())

    def get_all_status(self) -> Dict[str, int]:
        return {
            "pending_count": len(self.pending_reviews),
            "approved_count": len(self.approved_reviews),
            "rejected_count": len(self.rejected_reviews),
        }

    def clear(self) -> None:
        self.pending_reviews.clear()
        self.approved_reviews.clear()
        self.rejected_reviews.clear()


# Global default HITL controller
global_hitl_controller = HITLController()
