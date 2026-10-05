# db/models.py
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import String, Integer, Float, ForeignKey, DateTime, Text, Boolean
from datetime import datetime
from typing import List, Optional


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    password_hash: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(20), default="operator")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    boards: Mapped[List["BoardUnit"]] = relationship("BoardUnit", back_populates="operator")
    test_runs: Mapped[List["TestRun"]] = relationship("TestRun", back_populates="operator")

    def __repr__(self):
        return f"User(id={self.id}, username='{self.username}', role='{self.role}')"


class BoardModel(Base):
    __tablename__ = "board_models"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    version: Mapped[str] = mapped_column(String(50))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    manufacturer: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    equipment: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    voltage: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    boards: Mapped[List["BoardUnit"]] = relationship("BoardUnit", back_populates="board_model")
    plans: Mapped[List["TestPlan"]] = relationship("TestPlan", back_populates="board_model", cascade="all, delete-orphan")
    components: Mapped[List["Component"]] = relationship("Component", back_populates="board_model", cascade="all, delete-orphan")

    def __repr__(self):
        return f"BoardModel(id={self.id}, name='{self.name}', version='{self.version}')"


class Machine(Base):
    """Máquina/equipamento que agrupa as placas que ela possui."""
    __tablename__ = "machines"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    image_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Sem cascade de exclusão: apagar a máquina NÃO apaga as placas (elas ficam "sem máquina")
    boards: Mapped[List["BoardUnit"]] = relationship("BoardUnit", back_populates="machine")

    def __repr__(self):
        return f"Machine(id={self.id}, name='{self.name}')"


class BoardUnit(Base):
    __tablename__ = "board_units"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    model: Mapped[str] = mapped_column(String(50))
    version: Mapped[str] = mapped_column(String(50))
    serial_number: Mapped[str] = mapped_column(String(100), unique=True)
    client: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    service_order: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    reported_defect: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    diagnosis: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    model_id: Mapped[int] = mapped_column(ForeignKey("board_models.id"))
    operator_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    machine_id: Mapped[Optional[int]] = mapped_column(ForeignKey("machines.id"), nullable=True)

    board_model: Mapped["BoardModel"] = relationship("BoardModel", back_populates="boards")
    machine: Mapped[Optional["Machine"]] = relationship("Machine", back_populates="boards")
    operator: Mapped["User"] = relationship("User", back_populates="boards")

    images: Mapped[List["BoardImage"]] = relationship("BoardImage", back_populates="board", cascade="all, delete-orphan")
    test_points: Mapped[List["TestPoint"]] = relationship("TestPoint", back_populates="board", cascade="all, delete-orphan")
    test_runs: Mapped[List["TestRun"]] = relationship("TestRun", back_populates="board", cascade="all, delete-orphan")

    def __repr__(self):
        return f"BoardUnit(id={self.id}, name='{self.name}', serial='{self.serial_number}')"


class BoardImage(Base):
    __tablename__ = "board_images"

    id: Mapped[int] = mapped_column(primary_key=True)
    path: Mapped[str] = mapped_column(String(500))
    description: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    board_id: Mapped[int] = mapped_column(ForeignKey("board_units.id"))
    board: Mapped["BoardUnit"] = relationship("BoardUnit", back_populates="images")

    def __repr__(self):
        return f"BoardImage(id={self.id}, path='{self.path}')"


class TestPoint(Base):
    __tablename__ = "test_points"

    id: Mapped[int] = mapped_column(primary_key=True)
    refdes: Mapped[str] = mapped_column(String(50))
    x: Mapped[int] = mapped_column(Integer)
    y: Mapped[int] = mapped_column(Integer)

    expected_voltage_v: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    expected_current_a: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    expected_frequency_hz: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    expected_waveform: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    tolerance_voltage_v: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    tolerance_current_a: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    tolerance_frequency_hz: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Aparência do marcador no scanner. Novos pontos sempre nascem vermelhos.
    marker_color: Mapped[str] = mapped_column(String(7), default="#E53935", nullable=False)

    # Última captura do osciloscópio. Os valores esperados do ponto permanecem
    # separados das medições reais. O histórico completo fica em
    # oscilloscope_captures.
    last_scope_channel: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    last_scope_vpp_v: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_scope_vrms_v: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_scope_frequency_hz: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_scope_duty_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_scope_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_oscilloscope_id: Mapped[Optional[str]] = mapped_column(String(250), nullable=True)

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    board_id: Mapped[int] = mapped_column(ForeignKey("board_units.id"))
    board: Mapped["BoardUnit"] = relationship("BoardUnit", back_populates="test_points")
    oscilloscope_captures: Mapped[List["OscilloscopeCapture"]] = relationship(
        "OscilloscopeCapture",
        back_populates="test_point",
        cascade="all, delete-orphan",
        order_by="OscilloscopeCapture.timestamp.desc()",
    )

    def __repr__(self):
        return f"TestPoint(id={self.id}, refdes='{self.refdes}', x={self.x}, y={self.y})"


class OscilloscopeCapture(Base):
    """Histórico de capturas do Rigol/SCPI vinculadas a um ponto da placa."""

    __tablename__ = "oscilloscope_captures"

    id: Mapped[int] = mapped_column(primary_key=True)
    test_point_id: Mapped[int] = mapped_column(
        ForeignKey("test_points.id", ondelete="CASCADE"), index=True
    )
    channel: Mapped[int] = mapped_column(Integer)
    vpp_v: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    vrms_v: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    vmax_v: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    vmin_v: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    vavg_v: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    frequency_hz: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    period_s: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    duty_cycle_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    vertical_offset_v: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    oscilloscope_id: Mapped[Optional[str]] = mapped_column(String(250), nullable=True)
    raw_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    waveform_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    test_point: Mapped["TestPoint"] = relationship(
        "TestPoint", back_populates="oscilloscope_captures"
    )

    def __repr__(self):
        return (
            f"OscilloscopeCapture(id={self.id}, point={self.test_point_id}, "
            f"channel=CH{self.channel}, vpp={self.vpp_v})"
        )


class TestPlan(Base):
    __tablename__ = "test_plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    version: Mapped[str] = mapped_column(String(50))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    board_model_id: Mapped[int] = mapped_column(ForeignKey("board_models.id"))
    board_model: Mapped["BoardModel"] = relationship("BoardModel", back_populates="plans")

    steps: Mapped[List["TestStep"]] = relationship("TestStep", back_populates="plan", cascade="all, delete-orphan")

    def __repr__(self):
        return f"TestPlan(id={self.id}, name='{self.name}', version='{self.version}')"


class TestStep(Base):
    __tablename__ = "test_steps"

    id: Mapped[int] = mapped_column(primary_key=True)
    description: Mapped[str] = mapped_column(Text)
    test_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    desired_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    tolerance: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    min_limit: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_limit: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    plan_id: Mapped[int] = mapped_column(ForeignKey("test_plans.id"))
    plan: Mapped["TestPlan"] = relationship("TestPlan", back_populates="steps")

    test_point_id: Mapped[Optional[int]] = mapped_column(ForeignKey("test_points.id"), nullable=True)
    test_point: Mapped[Optional["TestPoint"]] = relationship("TestPoint")

    def __repr__(self):
        return f"TestStep(id={self.id}, description='{self.description}', unit='{self.unit}')"


class TestRun(Base):
    __tablename__ = "test_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    start_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    end_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="running")  # running, completed, failed, cancelled
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    board_id: Mapped[int] = mapped_column(ForeignKey("board_units.id"))
    operator_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    plan_id: Mapped[Optional[int]] = mapped_column(ForeignKey("test_plans.id"), nullable=True)

    board: Mapped["BoardUnit"] = relationship("BoardUnit", back_populates="test_runs")
    operator: Mapped["User"] = relationship("User", back_populates="test_runs")
    plan: Mapped[Optional["TestPlan"]] = relationship("TestPlan")

    measurements: Mapped[List["Measurement"]] = relationship("Measurement", back_populates="test_run", cascade="all, delete-orphan")

    def __repr__(self):
        return f"TestRun(id={self.id}, board_id={self.board_id}, status='{self.status}')"


class Measurement(Base):
    __tablename__ = "measurements"

    id: Mapped[int] = mapped_column(primary_key=True)
    value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    min_limit: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_limit: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    passed: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    test_run_id: Mapped[int] = mapped_column(ForeignKey("test_runs.id"))
    step_id: Mapped[int] = mapped_column(ForeignKey("test_steps.id"))

    test_run: Mapped["TestRun"] = relationship("TestRun", back_populates="measurements")
    step: Mapped["TestStep"] = relationship("TestStep")

    def __repr__(self):
        return f"Measurement(id={self.id}, value={self.value}, passed={self.passed})"


class Component(Base):
    __tablename__ = "components"

    id: Mapped[int] = mapped_column(primary_key=True)
    refdes: Mapped[str] = mapped_column(String(50))
    type: Mapped[str] = mapped_column(String(50))
    value: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    part_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    x: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    y: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    board_model_id: Mapped[int] = mapped_column(ForeignKey("board_models.id"))
    board_model: Mapped["BoardModel"] = relationship("BoardModel", back_populates="components")
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"Component(id={self.id}, refdes='{self.refdes}')"


class Instrument(Base):
    __tablename__ = "instruments"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    type: Mapped[str] = mapped_column(String(50))
    visa_address: Mapped[str] = mapped_column(String(100), unique=True)
    manufacturer: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    serial_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"Instrument(id={self.id}, name='{self.name}')"


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    action: Mapped[str] = mapped_column(String(100))
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    user: Mapped["User"] = relationship("User")

    def __repr__(self):
        return f"AuditLog(id={self.id}, action='{self.action}')"