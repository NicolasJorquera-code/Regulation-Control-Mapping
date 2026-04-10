"""Core foundation layer for ControlNexus.

Re-exports the key types that consumers need most frequently so that
dependent modules can write ``from controlnexus.core import DomainConfig``
instead of reaching into sub-modules.
"""

from controlnexus.core.domain_config import DomainConfig  # noqa: F401
from controlnexus.core.events import EventEmitter, PipelineEvent  # noqa: F401
from controlnexus.core.models import RunConfig, SectionProfile, TaxonomyCatalog  # noqa: F401
from controlnexus.core.state import FinalControlRecord, GapReport, HierarchyNode  # noqa: F401
