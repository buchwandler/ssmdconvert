class SSMDConvertError(Exception):
    """Base error."""


class UnsupportedInputError(SSMDConvertError):
    """No input adapter accepts the source."""


class MissingDependencyError(SSMDConvertError):
    """An optional adapter/enricher dependency is not installed."""


class EnrichmentError(SSMDConvertError):
    """Optional semantic enrichment failed."""
