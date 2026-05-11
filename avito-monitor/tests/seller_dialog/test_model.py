"""Verify SellerDialog model wires up correctly."""
import uuid
from datetime import datetime

from app.db.models import SellerDialog


def test_seller_dialog_construct_minimal():
    sd = SellerDialog(
        id=uuid.uuid4(),
        profile_id=uuid.uuid4(),
        listing_id=uuid.uuid4(),
        stage="contact",
        opened_at=datetime.utcnow(),
    )
    assert sd.stage == "contact"
    assert sd.operator_mode is False or sd.operator_mode is None
    assert sd.channel_id is None
    assert sd.closed_at is None


def test_messenger_message_has_dialog_id_field():
    from app.db.models import MessengerMessage
    cols = {c.name for c in MessengerMessage.__table__.columns}
    assert "dialog_id" in cols
