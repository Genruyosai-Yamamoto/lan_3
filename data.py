from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, UTC

db = SQLAlchemy()

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user = db.Column(db.String(100), nullable=False)
    message_type = db.Column(db.String(20), default="text")
    content = db.Column(db.Text, nullable=False)
    filename = db.Column(db.String(255))
    sender_sid = db.Column(db.String(255))
    ip_address = db.Column(db.String(50))
    timestamp = db.Column(
        db.DateTime,
        default=lambda: datetime.now(UTC)
    )
    edited = db.Column(
        db.Boolean,
        default=False
    )

    edited_at = db.Column(
        db.DateTime,
        nullable=True
    )
    deleted = db.Column(
        db.Boolean,
        default=False
    )

    deleted_at = db.Column(
        db.DateTime,
        nullable=True
    )

class Conversation(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    user1 = db.Column(db.String(100), nullable=False)
    user2 = db.Column(db.String(100), nullable=False)

    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(UTC)
    )


class PrivateMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    conversation_id = db.Column(
        db.Integer,
        db.ForeignKey("conversation.id"),
        nullable=False
    )

    sender = db.Column(db.String(100))
    receiver = db.Column(db.String(100))

    message_type = db.Column(db.String(20), default="text")

    content = db.Column(db.Text)

    timestamp = db.Column(
        db.DateTime,
        default=lambda: datetime.now(UTC)
    )

    edited = db.Column(db.Boolean, default=False)
    deleted = db.Column(db.Boolean, default=False)

class Reaction(db.Model):

    __tablename__ = "reactions"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    message_id = db.Column(
        db.Integer,
        db.ForeignKey("message.id"),
        nullable=False
    )

    user = db.Column(
        db.String(100),
        nullable=False
    )

    emoji = db.Column(
        db.String(20),
        nullable=False
    )

    timestamp = db.Column(
        db.DateTime,
        default=lambda: datetime.now(UTC)
    )

class UserKey(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    public_key = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC))

class PrivateReaction(db.Model):
    __tablename__ = "private_reactions"

    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(
        db.Integer,
        db.ForeignKey("private_message.id"),
        nullable=False
    )
    user = db.Column(db.String(100), nullable=False)
    emoji = db.Column(db.String(20), nullable=False)
    timestamp = db.Column(
        db.DateTime,
        default=lambda: datetime.now(UTC)
    )