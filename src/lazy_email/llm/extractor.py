"""LLM extraction service for job application data.

This module uses Ollama with Qwen 2.5 3B to extract structured job application
information (company name, role, status) from email content.
"""

import json
import logging
from typing import Optional

import ollama
from ollama import ResponseError

from lazy_email.config import get_settings
from lazy_email.models.email import (
    DEFAULT_COMPANY_NAME,
    DEFAULT_ROLE,
    ApplicationStatus,
    EmailMessage,
    JobApplication,
    LLMExtractionResult,
    is_unknown_value,
)

logger = logging.getLogger(__name__)


class LLMExtractorError(Exception):
    """Raised when LLM extraction fails."""

    pass


# Mapping from common LLM outputs to ApplicationStatus enum values
STATUS_MAPPINGS: dict[str, ApplicationStatus] = {
    # Submitted variations
    "submitted": ApplicationStatus.SUBMITTED,
    "application received": ApplicationStatus.SUBMITTED,
    "application submitted": ApplicationStatus.SUBMITTED,
    "pending": ApplicationStatus.SUBMITTED,
    "under review": ApplicationStatus.SUBMITTED,
    "received": ApplicationStatus.SUBMITTED,
    "confirmed": ApplicationStatus.SUBMITTED,
    "applied": ApplicationStatus.SUBMITTED,
    # Rejected variations
    "rejected": ApplicationStatus.REJECTED,
    "not selected": ApplicationStatus.REJECTED,
    "unsuccessful": ApplicationStatus.REJECTED,
    "declined": ApplicationStatus.REJECTED,
    "not moving forward": ApplicationStatus.REJECTED,
    "position filled": ApplicationStatus.REJECTED,
    "closed": ApplicationStatus.REJECTED,
    # Interview variations
    "interview": ApplicationStatus.INTERVIEW,
    "interview scheduled": ApplicationStatus.INTERVIEW,
    "phone screen": ApplicationStatus.INTERVIEW,
    "technical interview": ApplicationStatus.INTERVIEW,
    "onsite": ApplicationStatus.INTERVIEW,
    "final round": ApplicationStatus.INTERVIEW,
    "hiring manager": ApplicationStatus.INTERVIEW,
    # OA Invite variations
    "oa": ApplicationStatus.OA_INVITE,
    "oa invite": ApplicationStatus.OA_INVITE,
    "online assessment": ApplicationStatus.OA_INVITE,
    "coding challenge": ApplicationStatus.OA_INVITE,
    "assessment": ApplicationStatus.OA_INVITE,
    "hackerrank": ApplicationStatus.OA_INVITE,
    "codility": ApplicationStatus.OA_INVITE,
    "codesignal": ApplicationStatus.OA_INVITE,
    "take home": ApplicationStatus.OA_INVITE,
    "technical assessment": ApplicationStatus.OA_INVITE,
    # N/A variations
    "n/a": ApplicationStatus.NA,
    "na": ApplicationStatus.NA,
    "unknown": ApplicationStatus.NA,
    "unclear": ApplicationStatus.NA,
    "other": ApplicationStatus.NA,
}


EXTRACTION_PROMPT = """You are a data extraction assistant. Extract job application information from this email.

RULES (MUST FOLLOW):
1. You MUST extract a company name. Look at the sender email domain, subject line, and email body.
2. You MUST extract a job role. If unclear, default to "SWE Default".
3. NEVER respond with "unknown", "n/a", "not specified", "not found", or similar for company_name or role.
4. If you truly cannot find the company name, use exactly: "DEFAULT (INPUT MANUALLY)"
5. If you truly cannot find the role, use exactly: "SWE Default"

Extract these fields:
1. company_name: The employer name (check sender email like "@google.com" → "Google", or email signature/header)
2. role: The job title (e.g., "Software Engineer", "Data Scientist", "SWE Intern")
3. status: One of:
   - "submitted" - Application received/confirmed
   - "rejected" - Application declined
   - "interview" - Interview invitation
   - "oa_invite" - Online assessment/coding challenge
   - "n/a" - Cannot determine status (ONLY use for status, never for company/role)

SUBJECT: {subject}
FROM: {sender}

EMAIL CONTENT:
{email_content}

Respond with ONLY valid JSON:
{{"company_name": "...", "role": "...", "status": "..."}}"""


def _map_status_to_enum(status_raw: str) -> ApplicationStatus:
    """Map raw LLM status output to ApplicationStatus enum.

    Performs case-insensitive matching against known status variations.

    Args:
        status_raw: Raw status string from LLM output.

    Returns:
        Matching ApplicationStatus enum value, defaults to NA.
    """
    status_lower = status_raw.lower().strip()

    # Direct match
    if status_lower in STATUS_MAPPINGS:
        return STATUS_MAPPINGS[status_lower]

    # Partial match - check if any key is contained in the status
    for key, value in STATUS_MAPPINGS.items():
        if key in status_lower or status_lower in key:
            return value

    # Default to N/A
    return ApplicationStatus.NA


def _parse_llm_response(response_text: str) -> LLMExtractionResult:
    """Parse LLM JSON response to LLMExtractionResult.

    Handles common JSON formatting issues from LLM output.

    Args:
        response_text: Raw text response from LLM.

    Returns:
        Parsed LLMExtractionResult with extracted fields.

    Raises:
        LLMExtractorError: If JSON parsing fails.
    """
    # Clean up response - remove markdown code blocks if present
    text = response_text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        data = json.loads(text)
        company = data.get("company_name", "")
        role = data.get("role", "")
        status = data.get("status", "n/a")

        # Handle case where LLM returns a list instead of string
        if isinstance(company, list):
            company = company[0] if company else ""
        if isinstance(role, list):
            role = role[0] if role else ""
        if isinstance(status, list):
            status = status[0] if status else "n/a"

        # Ensure string types
        company = str(company) if company else ""
        role = str(role) if role else ""
        status = str(status) if status else "n/a"

        # Apply default fallbacks for unknown values
        if is_unknown_value(company):
            company = DEFAULT_COMPANY_NAME
        if is_unknown_value(role):
            role = DEFAULT_ROLE

        return LLMExtractionResult(
            company_name=company,
            role=role,
            status_raw=status,
        )
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse LLM response as JSON: {e}")
        logger.debug(f"Raw response: {response_text}")
        # Return defaults on parse failure
        return LLMExtractionResult()


class JobApplicationExtractor:
    """Extracts job application data from emails using a local LLM.

    Uses Ollama with a configurable model (default: Qwen 2.5 3B) to analyze
    email content and extract company name, role, and application status.

    Attributes:
        model: Ollama model name to use for extraction.
        host: Ollama server URL.
    """

    def __init__(
        self,
        model: Optional[str] = None,
        host: Optional[str] = None,
    ) -> None:
        """Initialize the extractor.

        Args:
            model: Ollama model name. Defaults to settings.ollama_model.
            host: Ollama server URL. Defaults to settings.ollama_host.
        """
        settings = get_settings()
        self.model = model or settings.ollama_model
        self.host = host or settings.ollama_host

        # Configure Ollama client
        self._client = ollama.Client(host=self.host)

    def _check_model_available(self) -> bool:
        """Check if the configured model is available in Ollama.

        Returns:
            True if model is available, False otherwise.
        """
        try:
            response = self._client.list()
            # response.models is a list of Model objects
            model_list = response.models if hasattr(response, 'models') else response.get("models", [])
            
            for m in model_list:
                # Handle both dict and object formats
                model_name = m.model if hasattr(m, 'model') else m.get("model", "")
                # Check both full name and base name (without tag)
                if model_name == self.model or model_name.split(":")[0] == self.model.split(":")[0]:
                    return True
            return False
        except Exception as e:
            logger.warning(f"Failed to check model availability: {e}")
            return False

    def _call_llm(self, prompt: str) -> str:
        """Call the LLM with a prompt and return the response.

        Args:
            prompt: The prompt to send to the LLM.

        Returns:
            The LLM's response text.

        Raises:
            LLMExtractorError: If the LLM call fails.
        """
        try:
            response = self._client.chat(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a data extraction assistant. Always respond with valid JSON only.",
                    },
                    {"role": "user", "content": prompt},
                ],
                format="json",
            )
            return response["message"]["content"]
        except ResponseError as e:
            raise LLMExtractorError(f"Ollama API error: {e}") from e
        except Exception as e:
            raise LLMExtractorError(f"Failed to call LLM: {e}") from e

    def extract_from_content(
        self, content: str, subject: str = "", sender: str = ""
    ) -> LLMExtractionResult:
        """Extract job application data from email content.

        Args:
            content: Email body text content.
            subject: Email subject line.
            sender: Sender email address.

        Returns:
            LLMExtractionResult with extracted fields.

        Raises:
            LLMExtractorError: If extraction fails.
        """
        prompt = EXTRACTION_PROMPT.format(
            email_content=content,
            subject=subject or "(no subject)",
            sender=sender or "(unknown sender)",
        )
        response_text = self._call_llm(prompt)
        return _parse_llm_response(response_text)

    def extract_from_email(self, email: EmailMessage) -> JobApplication:
        """Extract job application data from an EmailMessage.

        Combines LLM extraction with email metadata to create a
        complete JobApplication record.

        Args:
            email: EmailMessage to extract data from.

        Returns:
            JobApplication with extracted and mapped data.

        Raises:
            LLMExtractorError: If extraction fails.
        """
        # Extract using LLM with subject and sender context
        extraction = self.extract_from_content(
            content=email.content,
            subject=email.subject,
            sender=email.sender,
        )

        # Map status to enum
        status = _map_status_to_enum(extraction.status_raw)

        # Build JobApplication
        return JobApplication(
            company_name=extraction.company_name,
            role=extraction.role,
            status=status,
            date_submitted=email.date_sent.strftime("%Y-%m-%d"),
            email_link=email.email_link,
        )

    def extract_batch(self, emails: list[EmailMessage]) -> list[JobApplication]:
        """Extract job application data from multiple emails.

        Processes emails sequentially and logs any failures.

        Args:
            emails: List of EmailMessage objects to process.

        Returns:
            List of successfully extracted JobApplication objects.
        """
        results: list[JobApplication] = []

        for email in emails:
            try:
                application = self.extract_from_email(email)
                results.append(application)
                logger.info(f"Extracted: {application.company_name} - {application.role}")
            except LLMExtractorError as e:
                logger.error(f"Failed to extract from email {email.message_id}: {e}")
                # Create a fallback record with default values
                results.append(
                    JobApplication(
                        company_name=DEFAULT_COMPANY_NAME,
                        role=DEFAULT_ROLE,
                        status=ApplicationStatus.NA,
                        date_submitted=email.date_sent.strftime("%Y-%m-%d"),
                        email_link=email.email_link,
                    )
                )

        return results

    def verify_connection(self) -> bool:
        """Verify connection to Ollama server and model availability.

        Returns:
            True if connection is successful and model is available.
        """
        try:
            if not self._check_model_available():
                print(f"\n⚠ Model '{self.model}' not found in Ollama.")
                print(f"Please run: ollama pull {self.model}")
                return False

            # Test with a simple prompt
            self._call_llm("Respond with: {\"test\": \"ok\"}")
            return True
        except LLMExtractorError:
            print(f"\n⚠ Cannot connect to Ollama at {self.host}")
            print("Please ensure Ollama is running: ollama serve")
            return False
