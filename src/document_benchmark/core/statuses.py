"""Status enums and string constants for the document benchmark pipeline."""

from enum import Enum


class ExecutionMode(str, Enum):
    CORRECTNESS = "correctness"
    PERFORMANCE = "performance"
    BOTH = "both"


class OutputKind(str, Enum):
    DOCUMENT_IR = "document_ir"
    SCHEMA_JSON = "schema_json"


class EngineStatus(str, Enum):
    PENDING = "PENDING"
    PREPARING = "PREPARING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    OUT_OF_MEMORY = "OUT_OF_MEMORY"
    UNAVAILABLE = "UNAVAILABLE"
    CANCELLED = "CANCELLED"


class CachePolicy(str, Enum):
    COLD_CLEAN = "cold_clean"
    WARM_MODEL = "warm_model"
    WARM_FULL = "warm_full"
    EXISTING_CACHE = "existing_cache"


class Severity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class DocumentFamily(str, Enum):
    INVOICE = "invoice"
    OFFICE_SUPPLY_REQUEST = "office_supply_request"
    SOFTWARE_PROPOSAL = "software_proposal"
    INTERNAL_FORM = "internal_form"
    UNKNOWN = "unknown"


class DocumentSubtype(str, Enum):
    E_INVOICE = "e_invoice"
    UTILITY_INVOICE = "utility_invoice"
    LOGISTICS_INVOICE = "logistics_invoice"
    OFFICE_SUPPLY_INVOICE = "office_supply_invoice"
    OFFICE_SUPPLY_REQUEST = "office_supply_request"
    SOFTWARE_PROPOSAL = "software_proposal"
    INTERNAL_FORM = "internal_form"
    UNKNOWN = "unknown"
