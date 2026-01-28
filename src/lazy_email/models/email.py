"""Pydantic models for email and job application data.

This module defines the data structures used throughout the application
for representing email messages and extracted job application information.
"""

import re
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


# Default values for unknown fields
DEFAULT_COMPANY_NAME = "DEFAULT (INPUT MANUALLY)"
DEFAULT_ROLE = "SWE Default"


def is_unknown_value(value: str) -> bool:
    """Check if a value is considered 'unknown' or invalid.

    Args:
        value: The extracted value to check.

    Returns:
        True if the value should be treated as unknown.
    """
    if not value:
        return True
    # Handle case where LLM returns a list instead of string
    if isinstance(value, list):
        value = value[0] if value else ""
    if not isinstance(value, str):
        value = str(value)
    lower = value.lower().strip()
    unknown_patterns = [
        "unknown",
        "n/a",
        "na",
        "not specified",
        "not found",
        "not in email",
        "not mentioned",
        "cannot determine",
        "could not determine",
        "unclear",
        "none",
        "null",
        "not available",
        "",
    ]
    # Check exact matches and partial matches
    if lower in unknown_patterns:
        return True
    # Check if any pattern is contained in the value
    for pattern in ["not in email content", "cannot be determined", "not provided"]:
        if pattern in lower:
            return True
    return False


class ApplicationStatus(str, Enum):
    """Application status options matching the Google Sheet dropdown.

    These values must exactly match the dropdown options in the spreadsheet.
    """

    SUBMITTED = "Submitted Application - Pending Response"
    REJECTED = "Rejected"
    INTERVIEW = "Interview"
    OA_INVITE = "OA Invite"
    NA = "N/A"


# Status priority for determining which status "wins" when merging duplicates
# Higher number = higher priority (more advanced in the application process)
STATUS_PRIORITY: dict[ApplicationStatus, int] = {
    ApplicationStatus.NA: 0,           # Unknown - never overwrites
    ApplicationStatus.SUBMITTED: 1,    # Initial state
    ApplicationStatus.OA_INVITE: 2,    # Further along than submitted
    ApplicationStatus.INTERVIEW: 3,    # Further along than OA
    ApplicationStatus.REJECTED: 4,     # Final outcome - always keep
}


def should_update_status(existing: ApplicationStatus, new: ApplicationStatus) -> bool:
    """Determine if a new status should replace an existing status.

    Args:
        existing: The current status in the spreadsheet.
        new: The newly extracted status from an email.

    Returns:
        True if the new status should replace the existing one.
    """
    return STATUS_PRIORITY.get(new, 0) > STATUS_PRIORITY.get(existing, 0)


def normalize_company_name(name: str) -> str:
    """Normalize company name for fuzzy matching.

    Handles variations like:
    - "Google" vs "Google LLC" vs "Google Inc" vs "Google, Inc."
    - Case differences
    - Extra whitespace

    Args:
        name: Raw company name.

    Returns:
        Normalized company name for comparison.
    """
    if not name:
        return ""

    # Convert to lowercase
    normalized = name.lower().strip()

    # Remove common suffixes
    suffixes_to_remove = [
        r",?\s*inc\.?$",
        r",?\s*llc\.?$",
        r",?\s*ltd\.?$",
        r",?\s*corp\.?$",
        r",?\s*corporation$",
        r",?\s*company$",
        r",?\s*co\.?$",
        r",?\s*incorporated$",
        r",?\s*limited$",
        r",?\s*gmbh$",
        r",?\s*plc\.?$",
    ]

    for suffix in suffixes_to_remove:
        normalized = re.sub(suffix, "", normalized, flags=re.IGNORECASE)

    # Remove extra whitespace and punctuation
    normalized = re.sub(r"[^\w\s]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()

    return normalized


def normalize_role(role: str) -> str:
    """Normalize job role/title for fuzzy matching.

    Handles variations like:
    - "Software Engineer" vs "SWE" vs "Software Engineering"
    - "Intern" vs "Internship"
    - Case and whitespace differences

    Args:
        role: Raw role/title.

    Returns:
        Normalized role for comparison.
    """
    if not role:
        return ""

    # Convert to lowercase
    normalized = role.lower().strip()

    # Common abbreviation expansions
    abbreviations = {
        r"\bswe\b": "software engineer",
        r"\bsde\b": "software development engineer",
        r"\bml\b": "machine learning",
        r"\bai\b": "artificial intelligence",
        r"\bfe\b": "frontend",
        r"\bbe\b": "backend",
        r"\bqa\b": "quality assurance",
        r"\bui\b": "user interface",
        r"\bux\b": "user experience",
    }

    for abbrev, expansion in abbreviations.items():
        normalized = re.sub(abbrev, expansion, normalized)

    # Normalize intern/internship
    normalized = re.sub(r"\binternship\b", "intern", normalized)

    # Remove year references (e.g., "Summer 2026", "2025")
    normalized = re.sub(r"\b(summer|fall|spring|winter)\s*\d{4}\b", "", normalized)
    normalized = re.sub(r"\b20\d{2}\b", "", normalized)

    # Remove extra whitespace
    normalized = re.sub(r"\s+", " ", normalized).strip()

    return normalized


class EmailMessage(BaseModel):
    """Represents a Gmail email message with relevant metadata.

    Attributes:
        message_id: The unique Gmail message ID.
        subject: The email subject line.
        content: The email body content (plain text).
        date_sent: The date and time the email was sent.
        email_link: A direct link to the email in Gmail.
        sender: The sender's email address.
    """

    message_id: str = Field(..., description="Unique Gmail message ID")
    subject: str = Field(default="", description="Email subject line")
    content: str = Field(..., description="Email body content (plain text)")
    date_sent: datetime = Field(..., description="Date and time the email was sent")
    email_link: str = Field(..., description="Direct link to the email in Gmail")
    sender: str = Field(default="", description="Sender's email address")


class JobApplication(BaseModel):
    """Represents extracted job application data from an email.

    Attributes:
        company_name: The name of the employer/company.
        role: The job title or role applied for.
        status: The application status (mapped to dropdown options).
        date_submitted: The date the application-related email was received.
        email_link: A direct link to the source email in Gmail.
    """

    company_name: str = Field(..., description="Name of the employer/company")
    role: str = Field(..., description="Job title or role applied for")
    status: ApplicationStatus = Field(
        default=ApplicationStatus.NA,
        description="Application status matching spreadsheet dropdown",
    )
    date_submitted: str = Field(..., description="Date in YYYY-MM-DD format")
    email_link: str = Field(..., description="Direct link to the source email")


class LLMExtractionResult(BaseModel):
    """Raw extraction result from the LLM before mapping to ApplicationStatus.

    Attributes:
        company_name: The extracted company/employer name.
        role: The extracted job title/role.
        status_raw: The raw status string from the LLM.
    """

    company_name: str = Field(default=DEFAULT_COMPANY_NAME, description="Extracted company name")
    role: str = Field(default=DEFAULT_ROLE, description="Extracted job role")
    status_raw: str = Field(
        default="N/A",
        description="Raw status string before mapping to ApplicationStatus",
    )
