class SSMDConvertError(Exception):
    """Base error."""


class UnsupportedInputError(SSMDConvertError):
    """No input adapter accepts the source."""


class BookError(SSMDConvertError):
    """A book inspection or conversion failed."""


class UnsupportedBookSourceError(BookError):
    """The book API does not support this source format."""


class ChapterSelectionError(BookError):
    """A chapter selection is malformed or unavailable."""


class BookBundleError(BookError):
    """A book bundle could not be read or written."""


class BookBundleValidationError(BookBundleError):
    """A book bundle has invalid structure or content."""


class MissingDependencyError(SSMDConvertError):
    """An optional adapter/enricher dependency is not installed."""


class AnalysisError(SSMDConvertError):
    """An SSMD-specific analysis operation failed."""


class AnalysisSourceError(AnalysisError):
    """An SSMD analysis source could not be loaded or validated."""


class MappingError(AnalysisError):
    """A prepared change could not be mapped safely to SSMD source."""


class MaterializationError(AnalysisError):
    """SSMD speech substitutions could not be written safely."""


class ProjectionError(AnalysisError):
    """A prepared plain-text projection could not be reconstructed safely."""


class AnalysisCacheError(AnalysisError):
    """A persistent analysis cache is missing, unsafe, or malformed."""


class ContextLookupError(AnalysisError):
    """A cached change context could not be found or is stale."""
