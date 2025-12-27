from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nickname = db.Column(db.String(50), unique=True, nullable=False)
    username = db.Column(db.String(50), nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    avatar = db.Column(db.String(100), default='default.svg')
    bio = db.Column(db.Text, nullable=True)
    age = db.Column(db.Integer, nullable=True)
    gender = db.Column(db.String(20), nullable=True)
    goals = db.Column(db.Text, nullable=True)
    tasks = db.relationship('Task', backref='author', lazy=True, cascade="all, delete-orphan")

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    deadline = db.Column(db.DateTime, nullable=True)
    completed = db.Column(db.Boolean, default=False)
    is_public = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    steps = db.relationship('TaskStep', backref='task', cascade="all, delete-orphan", lazy=True)

class TaskStep(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.String(100), nullable=False)
    completed = db.Column(db.Boolean, default=False)
    task_id = db.Column(db.ForeignKey('task.id'), nullable=False)