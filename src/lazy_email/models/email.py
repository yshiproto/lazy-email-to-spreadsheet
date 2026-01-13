"""Pydantic models for email and job application data.

This module defines the data structures used throughout the application
for representing email messages and extracted job application information.
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ApplicationStatus(str, Enum):
    """Application status options matching the Google Sheet dropdown.

    These values must exactly match the dropdown options in the spreadsheet.
    """

    SUBMITTED = "Submitted Application - Pending Response"
    REJECTED = "Rejected"
    INTERVIEW = "Interview"
    OA_INVITE = "OA Invite"
    NA = "N/A"


class EmailMessage(BaseModel):
    """Represents a Gmail email message with relevant metadata.

    Attributes:
        message_id: The unique Gmail message ID.
        content: The email body content (plain text).
        date_sent: The date and time the email was sent.
        email_link: A direct link to the email in Gmail.
        sender: The sender's email address.
    """

    message_id: str = Field(..., description="Unique Gmail message ID")
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

    company_name: str = Field(default="Unknown", description="Extracted company name")
    role: str = Field(default="Unknown", description="Extracted job role")
    status_raw: str = Field(
        default="N/A",
        description="Raw status string before mapping to ApplicationStatus",
    )
