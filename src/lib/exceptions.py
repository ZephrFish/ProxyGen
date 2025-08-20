"""
Custom exceptions for ProxyGen application.
Provides structured error handling with recovery suggestions.
"""

import logging
from typing import Optional, Dict, Any, List
from enum import Enum


class ErrorSeverity(Enum):
    """Error severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(Enum):
    """Error categories for better organization."""
    VALIDATION = "validation"
    NETWORK = "network"
    AUTHENTICATION = "authentication"
    CLOUD_PROVIDER = "cloud_provider"
    FILESYSTEM = "filesystem"
    CONFIGURATION = "configuration"
    SUBPROCESS = "subprocess"
    TERRAFORM = "terraform"
    ANSIBLE = "ansible"
    SSH = "ssh"
    DEPLOYMENT = "deployment"
    SECURITY = "security"


class ProxyGenError(Exception):
    """Base exception for all ProxyGen errors."""
    
    def __init__(
        self,
        message: str,
        category: ErrorCategory = ErrorCategory.VALIDATION,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        suggestions: Optional[List[str]] = None,
        error_code: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        original_error: Optional[Exception] = None
    ):
        super().__init__(message)
        self.message = message
        self.category = category
        self.severity = severity
        self.suggestions = suggestions or []
        self.error_code = error_code
        self.context = context or {}
        self.original_error = original_error
        
        # Log the error
        self._log_error()
    
    def _log_error(self):
        """Log the error with appropriate level."""
        logger = logging.getLogger(__name__)
        
        log_message = f"[{self.category.value.upper()}] {self.message}"
        if self.error_code:
            log_message = f"{self.error_code}: {log_message}"
        
        if self.severity == ErrorSeverity.CRITICAL:
            logger.critical(log_message, exc_info=self.original_error)
        elif self.severity == ErrorSeverity.HIGH:
            logger.error(log_message, exc_info=self.original_error)
        elif self.severity == ErrorSeverity.MEDIUM:
            logger.warning(log_message)
        else:
            logger.info(log_message)
    
    def get_user_message(self) -> str:
        """Get user-friendly error message with suggestions."""
        message = f"{self.message}"
        
        if self.suggestions:
            message += "\n\nSuggestions:"
            for i, suggestion in enumerate(self.suggestions, 1):
                message += f"\n  {i}. {suggestion}"
        
        return message
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary for structured logging."""
        return {
            "message": self.message,
            "category": self.category.value,
            "severity": self.severity.value,
            "error_code": self.error_code,
            "suggestions": self.suggestions,
            "context": self.context
        }


class ValidationError(ProxyGenError):
    """Raised when input validation fails."""
    
    def __init__(self, message: str, field: str = None, **kwargs):
        super().__init__(
            message,
            category=ErrorCategory.VALIDATION,
            severity=ErrorSeverity.MEDIUM,
            **kwargs
        )
        if field:
            self.context["field"] = field


class CloudProviderError(ProxyGenError):
    """Raised when cloud provider operations fail."""
    
    def __init__(self, message: str, provider: str = None, **kwargs):
        super().__init__(
            message,
            category=ErrorCategory.CLOUD_PROVIDER,
            severity=ErrorSeverity.HIGH,
            **kwargs
        )
        if provider:
            self.context["provider"] = provider


class TerraformError(ProxyGenError):
    """Raised when Terraform operations fail."""
    
    def __init__(self, message: str, command: str = None, **kwargs):
        super().__init__(
            message,
            category=ErrorCategory.TERRAFORM,
            severity=ErrorSeverity.HIGH,
            **kwargs
        )
        if command:
            self.context["terraform_command"] = command


class AnsibleError(ProxyGenError):
    """Raised when Ansible operations fail."""
    
    def __init__(self, message: str, playbook: str = None, **kwargs):
        super().__init__(
            message,
            category=ErrorCategory.ANSIBLE,
            severity=ErrorSeverity.HIGH,
            **kwargs
        )
        if playbook:
            self.context["playbook"] = playbook


class SSHError(ProxyGenError):
    """Raised when SSH operations fail."""
    
    def __init__(self, message: str, host: str = None, **kwargs):
        super().__init__(
            message,
            category=ErrorCategory.SSH,
            severity=ErrorSeverity.HIGH,
            **kwargs
        )
        if host:
            self.context["host"] = host


class NetworkError(ProxyGenError):
    """Raised when network operations fail."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            category=ErrorCategory.NETWORK,
            severity=ErrorSeverity.HIGH,
            **kwargs
        )


class AuthenticationError(ProxyGenError):
    """Raised when authentication fails."""
    
    def __init__(self, message: str, provider: str = None, **kwargs):
        super().__init__(
            message,
            category=ErrorCategory.AUTHENTICATION,
            severity=ErrorSeverity.HIGH,
            **kwargs
        )
        if provider:
            self.context["provider"] = provider


class ConfigurationError(ProxyGenError):
    """Raised when configuration is invalid."""
    
    def __init__(self, message: str, config_file: str = None, **kwargs):
        super().__init__(
            message,
            category=ErrorCategory.CONFIGURATION,
            severity=ErrorSeverity.HIGH,
            **kwargs
        )
        if config_file:
            self.context["config_file"] = config_file


class FilesystemError(ProxyGenError):
    """Raised when filesystem operations fail."""
    
    def __init__(self, message: str, path: str = None, **kwargs):
        super().__init__(
            message,
            category=ErrorCategory.FILESYSTEM,
            severity=ErrorSeverity.MEDIUM,
            **kwargs
        )
        if path:
            self.context["path"] = path


class SecurityError(ProxyGenError):
    """Raised when security violations are detected."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            category=ErrorCategory.SECURITY,
            severity=ErrorSeverity.CRITICAL,
            **kwargs
        )


class DeploymentError(ProxyGenError):
    """Raised when deployment operations fail."""
    
    def __init__(self, message: str, deployment_id: str = None, **kwargs):
        super().__init__(
            message,
            category=ErrorCategory.DEPLOYMENT,
            severity=ErrorSeverity.HIGH,
            **kwargs
        )
        if deployment_id:
            self.context["deployment_id"] = deployment_id


class SubprocessError(ProxyGenError):
    """Raised when subprocess operations fail."""
    
    def __init__(self, message: str, command: str = None, return_code: int = None, **kwargs):
        super().__init__(
            message,
            category=ErrorCategory.SUBPROCESS,
            severity=ErrorSeverity.HIGH,
            **kwargs
        )
        if command:
            self.context["command"] = command
        if return_code is not None:
            self.context["return_code"] = return_code


# Error recovery strategies
class ErrorRecovery:
    """Provides error recovery strategies and suggestions."""
    
    @staticmethod
    def get_recovery_suggestions(error: ProxyGenError) -> List[str]:
        """Get context-specific recovery suggestions."""
        suggestions = []
        
        if error.category == ErrorCategory.AUTHENTICATION:
            suggestions.extend([
                "Check your cloud provider credentials",
                "Verify your account has necessary permissions",
                "Try running './proxygen setup --credentials' to reconfigure",
                "Check if your credentials have expired"
            ])
        
        elif error.category == ErrorCategory.NETWORK:
            suggestions.extend([
                "Check your internet connection",
                "Verify firewall settings aren't blocking connections",
                "Try again in a few minutes (temporary network issue)",
                "Check if the target service is operational"
            ])
        
        elif error.category == ErrorCategory.TERRAFORM:
            suggestions.extend([
                "Check Terraform is installed and in PATH",
                "Verify Terraform state isn't locked",
                "Try running 'terraform init' in the provider directory",
                "Check if resources already exist in the cloud"
            ])
        
        elif error.category == ErrorCategory.SSH:
            suggestions.extend([
                "Verify the server is running and accessible",
                "Check SSH key permissions (should be 600)",
                "Ensure security groups allow SSH access (port 22)",
                "Try connecting manually with: ssh -i <key> ubuntu@<ip>"
            ])
        
        elif error.category == ErrorCategory.VALIDATION:
            suggestions.extend([
                "Check the format of your input parameters",
                "Verify all required arguments are provided",
                "Use --help to see correct command syntax",
                "Check examples in documentation"
            ])
        
        elif error.category == ErrorCategory.FILESYSTEM:
            suggestions.extend([
                "Check file/directory permissions",
                "Verify sufficient disk space",
                "Ensure the path exists and is accessible",
                "Check if file is locked by another process"
            ])
        
        elif error.category == ErrorCategory.CONFIGURATION:
            suggestions.extend([
                "Check configuration file syntax",
                "Verify all required configuration values are set",
                "Try regenerating configuration with default values",
                "Check configuration file permissions"
            ])
        
        return suggestions
    
    @staticmethod
    def suggest_next_steps(error: ProxyGenError) -> List[str]:
        """Suggest next steps based on error context."""
        steps = []
        
        if error.severity == ErrorSeverity.CRITICAL:
            steps.extend([
                "Stop current operations to prevent further issues",
                "Review error logs for detailed information",
                "Contact support if issue persists"
            ])
        
        elif error.severity == ErrorSeverity.HIGH:
            steps.extend([
                "Review the specific error message above",
                "Try the suggested recovery steps",
                "Check system status and retry if appropriate"
            ])
        
        elif error.severity == ErrorSeverity.MEDIUM:
            steps.extend([
                "Review input parameters and try again",
                "Check documentation for correct usage",
                "Use --help flag for command syntax"
            ])
        
        return steps


def handle_error(func):
    """Decorator for consistent error handling."""
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ProxyGenError:
            # Re-raise ProxyGen errors as-is
            raise
        except Exception as e:
            # Wrap other exceptions in ProxyGenError
            raise ProxyGenError(
                f"Unexpected error in {func.__name__}: {str(e)}",
                category=ErrorCategory.VALIDATION,
                severity=ErrorSeverity.HIGH,
                original_error=e,
                suggestions=["Check logs for detailed error information", "Retry the operation"]
            )
    return wrapper


def safe_execute(func, default=None, error_message="Operation failed"):
    """Safely execute a function and return default on error."""
    try:
        return func()
    except Exception as e:
        logging.error(f"{error_message}: {str(e)}")
        return default