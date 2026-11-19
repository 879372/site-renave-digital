import uuid

from django.db import models


class TimeStampedModel(models.Model):
    """Base: id interno sequencial + id público UUID (nunca exponha o sequencial)."""

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
