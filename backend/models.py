# backend/models.py

from sqlalchemy import Column, Integer, String, Text, ForeignKey
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class Benchmark(Base):
    __tablename__ = "benchmarks"

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    benchmark_type = Column(String)

    rules = relationship("Rule", back_populates="benchmark", cascade="all, delete-orphan")
    remote_hosts = relationship("RemoteHost", back_populates="benchmark", cascade="all, delete-orphan")


class Rule(Base):
    __tablename__ = "rules"

    id = Column(Integer, primary_key=True)
    benchmark_id = Column(Integer, ForeignKey("benchmarks.id"), nullable=False)
    rule_id = Column(String, nullable=False)
    definition_id = Column(String)
    oval_path = Column(String)
    xccdf_path = Column(String)
    supported = Column(Integer)
    unsupported_probes = Column(Text)
    object_type = Column(String)
    manual = Column(Integer)
    excluded = Column(Integer, default=0)
    sensor_file_generated = Column(Integer, default=0)
    benchmark_type = Column(String)

    benchmark = relationship("Benchmark", back_populates="rules")
    vci_results = relationship("VCIResult", back_populates="rule", cascade="all, delete-orphan")
    unsupported_regex = relationship("UnsupportedRegex", back_populates="rule", cascade="all, delete-orphan")


class RemoteHost(Base):
    __tablename__ = "remote_hosts"

    id = Column(Integer, primary_key=True)
    benchmark_id = Column(Integer, ForeignKey("benchmarks.id"), nullable=False)
    ip_address = Column(String)
    username = Column(String)
    password_encrypted = Column(String)
    os_type = Column(String)
    benchmark = relationship("Benchmark", back_populates="remote_hosts")


class VCIResult(Base):
    __tablename__ = "vci_results"

    id = Column(Integer, primary_key=True)
    rule_id = Column(Integer, ForeignKey("rules.id"))
    json_output = Column(Text)
    rule = relationship("Rule", back_populates="vci_results")


class UnsupportedRegex(Base):
    __tablename__ = "unsupported_regex"

    id = Column(Integer, primary_key=True)
    rule_id = Column(Integer, ForeignKey("rules.id"))
    definition_id = Column(String)
    object_id = Column(String)
    pattern = Column(Text)
    reason = Column(Text)
    processed_pattern = Column(Text)    # NEW
    tests_json = Column(Text)           # NEW

    rule = relationship("Rule", back_populates="unsupported_regex")
