from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user = db.Column(db.String(100), nullable=False)
    message_type = db.Column(db.String(20), default="text")
    content = db.Column(db.Text, nullable=False)
    filename = db.Column(db.String(255))
    ip_address = db.Column(db.String(50))
    timestamp = db.Column(
        db.DateTime,
        default=datetime.utcnow
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
        default=datetime.utcnow
    )