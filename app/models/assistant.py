"""Assistant Claude (lot AG9b, claudedocs/design_assistant_agricole.md § 7) : conversations, messages (blocs
de l'API conservés tels quels, en ajout seulement) et propositions en brouillon."""
from __future__ import annotations

from datetime import datetime

from app.extensions import db

PROPOSAL_STATUSES = ("open", "accepted", "ignored")


class AssistantConversation(db.Model):
    __tablename__ = "assistant_conversations"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False, index=True)          # utilisateur de la méta-base
    title = db.Column(db.String(200), nullable=False, default="Nouvelle conversation")
    fiscal_year_id = db.Column(db.Integer, db.ForeignKey("fiscal_years.id", ondelete="SET NULL"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    messages = db.relationship("AssistantMessage", cascade="all, delete-orphan", order_by="AssistantMessage.id")


class AssistantMessage(db.Model):
    """Un message de l'historique envoyé à l'API : user (texte ou résultats d'outils), assistant (blocs complets),
    system (contexte de page, en cours de conversation)."""
    __tablename__ = "assistant_messages"

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey("assistant_conversations.id", ondelete="CASCADE"),
                                nullable=False, index=True)
    role = db.Column(db.String(10), nullable=False)
    content_json = db.Column(db.Text, nullable=False)
    kind = db.Column(db.String(12), nullable=False, default="text", server_default="text")  # text | tool_results | context
    model = db.Column(db.String(40))
    stop_reason = db.Column(db.String(20))
    input_tokens = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    output_tokens = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    cache_read_tokens = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    cache_creation_tokens = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)


class AssistantProposal(db.Model):
    """Proposition en brouillon (écriture, appel MSA, échéance, navigation) : jamais exécutée par l'assistant."""
    __tablename__ = "assistant_proposals"

    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.Integer, db.ForeignKey("assistant_messages.id", ondelete="CASCADE"), nullable=False,
                           index=True)
    kind = db.Column(db.String(20), nullable=False)
    payload_json = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(10), nullable=False, default="open", server_default="open")
    result_ref = db.Column(db.String(60))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
