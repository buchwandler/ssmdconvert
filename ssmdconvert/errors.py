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


class EnrichmentError(SSMDConvertError):
    """Optional semantic enrichment failed."""
