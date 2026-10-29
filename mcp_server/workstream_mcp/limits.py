"""Shared transport limits for MCP guide-document operations."""

GUIDE_DOCUMENT_MAX_BYTES = 64 * 1024 * 1024
GUIDE_DOCUMENT_MAX_BASE64_CHARS = 4 * ((GUIDE_DOCUMENT_MAX_BYTES + 2) // 3)
SUBMISSION_BUNDLE_MAX_BYTES = 64 * 1024 * 1024
SUBMISSION_BUNDLE_MAX_BASE64_CHARS = 4 * ((SUBMISSION_BUNDLE_MAX_BYTES + 2) // 3)
TASK_IMPORT_SOURCE_MAX_BYTES = 8 * 1024 * 1024
TASK_IMPORT_SOURCE_MAX_BASE64_CHARS = 4 * ((TASK_IMPORT_SOURCE_MAX_BYTES + 2) // 3)
MCP_MAX_REQUEST_BYTES = 96 * 1024 * 1024

GUIDE_DOCUMENT_MEDIA_TYPES = (
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/markdown",
)
