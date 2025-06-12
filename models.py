from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, ForeignKey, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()

class Meeting(Base):
    __tablename__ = 'meetings'
    
    id = Column(Integer, primary_key=True)
    channel_id = Column(String, nullable=False)
    start_time = Column(DateTime, default=datetime.utcnow)
    end_time = Column(DateTime)
    chair_id = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    
    messages = relationship("Message", back_populates="meeting")
    action_items = relationship("ActionItem", back_populates="meeting")
    co_chairs = relationship("CoChair", back_populates="meeting")

class Message(Base):
    __tablename__ = 'messages'
    
    id = Column(Integer, primary_key=True)
    meeting_id = Column(Integer, ForeignKey('meetings.id'))
    user_id = Column(String, nullable=False)
    content = Column(String, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    meeting = relationship("Meeting", back_populates="messages")

class ActionItem(Base):
    __tablename__ = 'action_items'
    
    id = Column(Integer, primary_key=True)
    meeting_id = Column(Integer, ForeignKey('meetings.id'))
    assigned_to = Column(String, nullable=False)
    task = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed = Column(Boolean, default=False)
    
    meeting = relationship("Meeting", back_populates="action_items")

class CoChair(Base):
    __tablename__ = 'co_chairs'
    
    id = Column(Integer, primary_key=True)
    meeting_id = Column(Integer, ForeignKey('meetings.id'))
    user_id = Column(String, nullable=False)
    
    meeting = relationship("Meeting", back_populates="co_chairs")

class SpeakerStats(Base):
    __tablename__ = 'speaker_stats'
    
    id = Column(Integer, primary_key=True)
    meeting_id = Column(Integer, ForeignKey('meetings.id'))
    user_id = Column(String, nullable=False)
    message_count = Column(Integer, default=0)
    total_words = Column(Integer, default=0)
    speaking_time_seconds = Column(Float, default=0.0)

class UserKarma(Base):
    __tablename__ = 'user_karma'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(String, nullable=False)
    points = Column(Integer, default=0)
    last_updated = Column(DateTime, default=datetime.utcnow)
    
    def increment(self):
        self.points += 1
        self.last_updated = datetime.utcnow

def init_db():
    engine = create_engine('sqlite:///meetbot.db')
    Base.metadata.create_all(engine) 