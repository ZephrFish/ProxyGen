"""
Improved subprocess utilities with comprehensive error handling.
"""

import subprocess
import logging
import signal
import threading
import time
from pathlib import Path
from typing import Optional, Dict, Any, List, Union, Tuple
from contextlib import contextmanager

try:
    from .exceptions import SubprocessError, NetworkError, AuthenticationError, TerraformError, AnsibleError, SSHError
except ImportError:
    # For direct module loading
    from exceptions import SubprocessError, NetworkError, AuthenticationError, TerraformError, AnsibleError, SSHError


logger = logging.getLogger(__name__)


class SubprocessRunner:
    """Enhanced subprocess runner with timeout, logging, and error handling."""
    
    def __init__(self, timeout: int = 300, cwd: Optional[Path] = None):
        self.timeout = timeout
        self.cwd = cwd
        self.process = None
        self._output_buffer = []
        self._error_buffer = []
    
    def run(
        self,
        command: Union[str, List[str]],
        timeout: Optional[int] = None,
        capture_output: bool = True,
        check: bool = True,
        env: Optional[Dict[str, str]] = None,
        input_data: Optional[str] = None,
        log_output: bool = True,
        sensitive_args: Optional[List[str]] = None
    ) -> subprocess.CompletedProcess:
        """
        Run a subprocess command with enhanced error handling.
        
        Args:
            command: Command to run (string or list)
            timeout: Timeout in seconds (uses instance default if None)
            capture_output: Whether to capture stdout/stderr
            check: Whether to raise exception on non-zero exit
            env: Environment variables
            input_data: Input to send to process
            log_output: Whether to log command output
            sensitive_args: List of sensitive arguments to mask in logs
        
        Returns:
            CompletedProcess result
        
        Raises:
            SubprocessError: On command execution failure
        """
        timeout = timeout or self.timeout
        
        # Prepare command
        if isinstance(command, str):
            cmd_list = command.split()
        else:
            cmd_list = command
        
        # Log command (mask sensitive args)
        log_cmd = self._mask_sensitive_args(cmd_list, sensitive_args or [])
        logger.info(f"Executing: {' '.join(log_cmd)}")
        
        # Prepare environment
        full_env = dict(subprocess.os.environ)
        if env:
            full_env.update(env)
        
        try:
            # Start process
            process = subprocess.Popen(
                cmd_list,
                stdout=subprocess.PIPE if capture_output else None,
                stderr=subprocess.PIPE if capture_output else None,
                stdin=subprocess.PIPE if input_data else None,
                text=True,
                cwd=self.cwd,
                env=full_env
            )
            
            self.process = process
            
            # Run with timeout
            try:
                stdout, stderr = process.communicate(
                    input=input_data,
                    timeout=timeout
                )
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
                raise SubprocessError(
                    f"Command timed out after {timeout} seconds",
                    command=' '.join(cmd_list),
                    return_code=process.returncode,
                    suggestions=[
                        "Increase timeout value",
                        "Check if command is hanging",
                        "Verify network connectivity",
                        "Check for interactive prompts"
                    ]
                )
            
            # Create result
            result = subprocess.CompletedProcess(
                cmd_list,
                process.returncode,
                stdout,
                stderr
            )
            
            # Log output
            if log_output:
                if stdout:
                    logger.debug(f"Command stdout: {stdout}")
                if stderr:
                    logger.debug(f"Command stderr: {stderr}")
            
            # Check for errors
            if check and result.returncode != 0:
                self._handle_command_error(result, cmd_list)
            
            return result
            
        except FileNotFoundError:
            raise SubprocessError(
                f"Command not found: {cmd_list[0]}",
                command=' '.join(cmd_list),
                suggestions=[
                    f"Install {cmd_list[0]} and ensure it's in PATH",
                    "Check if the command name is correct",
                    "Verify the tool is properly configured"
                ]
            )
        except PermissionError:
            raise SubprocessError(
                f"Permission denied executing: {cmd_list[0]}",
                command=' '.join(cmd_list),
                suggestions=[
                    "Check file permissions",
                    "Run with appropriate privileges",
                    "Verify you have execute permissions"
                ]
            )
        except Exception as e:
            raise SubprocessError(
                f"Unexpected error running command: {str(e)}",
                command=' '.join(cmd_list),
                original_error=e,
                suggestions=[
                    "Check system resources",
                    "Verify command syntax",
                    "Check logs for more details"
                ]
            )
        finally:
            self.process = None
    
    def _mask_sensitive_args(self, cmd_list: List[str], sensitive_args: List[str]) -> List[str]:
        """Mask sensitive arguments in command for logging."""
        masked_cmd = cmd_list.copy()
        
        for i, arg in enumerate(masked_cmd):
            for sensitive in sensitive_args:
                if sensitive in arg:
                    masked_cmd[i] = arg.replace(sensitive, "***")
        
        return masked_cmd
    
    def _handle_command_error(self, result: subprocess.CompletedProcess, cmd_list: List[str]):
        """Handle command execution errors with specific error types."""
        command = ' '.join(cmd_list)
        stdout = result.stdout or ""
        stderr = result.stderr or ""
        
        # Determine specific error type based on command and output
        if cmd_list[0] == "terraform":
            self._handle_terraform_error(result, command, stdout, stderr)
        elif cmd_list[0] == "ansible-playbook":
            self._handle_ansible_error(result, command, stdout, stderr)
        elif cmd_list[0] == "ssh" or "ssh" in command:
            self._handle_ssh_error(result, command, stdout, stderr)
        else:
            self._handle_generic_error(result, command, stdout, stderr)
    
    def _handle_terraform_error(self, result: subprocess.CompletedProcess, command: str, stdout: str, stderr: str):
        """Handle Terraform-specific errors."""
        error_msg = stderr or stdout
        
        if "authentication" in error_msg.lower() or "credentials" in error_msg.lower():
            raise AuthenticationError(
                f"Terraform authentication failed: {error_msg}",
                suggestions=[
                    "Check cloud provider credentials",
                    "Verify account permissions",
                    "Run './proxygen setup --credentials'"
                ]
            )
        elif "state lock" in error_msg.lower():
            raise TerraformError(
                f"Terraform state is locked: {error_msg}",
                command=command,
                suggestions=[
                    "Wait for other operations to complete",
                    "Force unlock if safe: terraform force-unlock <lock-id>",
                    "Check for stale processes"
                ]
            )
        elif "already exists" in error_msg.lower():
            raise TerraformError(
                f"Resource already exists: {error_msg}",
                command=command,
                suggestions=[
                    "Use terraform import to manage existing resources",
                    "Choose different resource names",
                    "Destroy existing resources first"
                ]
            )
        else:
            raise TerraformError(
                f"Terraform command failed: {error_msg}",
                command=command,
                suggestions=[
                    "Check Terraform syntax",
                    "Verify provider configuration",
                    "Review Terraform logs for details"
                ]
            )
    
    def _handle_ansible_error(self, result: subprocess.CompletedProcess, command: str, stdout: str, stderr: str):
        """Handle Ansible-specific errors."""
        error_msg = stderr or stdout
        
        if "unreachable" in error_msg.lower():
            raise NetworkError(
                f"Ansible cannot reach host: {error_msg}",
                suggestions=[
                    "Check network connectivity",
                    "Verify host is running",
                    "Check firewall settings"
                ]
            )
        elif "permission denied" in error_msg.lower():
            raise AuthenticationError(
                f"Ansible authentication failed: {error_msg}",
                suggestions=[
                    "Check SSH key permissions",
                    "Verify SSH connection works manually",
                    "Check user permissions on target host"
                ]
            )
        else:
            raise AnsibleError(
                f"Ansible playbook failed: {error_msg}",
                suggestions=[
                    "Check playbook syntax",
                    "Verify target host configuration",
                    "Check Ansible logs for details"
                ]
            )
    
    def _handle_ssh_error(self, result: subprocess.CompletedProcess, command: str, stdout: str, stderr: str):
        """Handle SSH-specific errors."""
        error_msg = stderr or stdout
        
        if "connection refused" in error_msg.lower():
            raise NetworkError(
                f"SSH connection refused: {error_msg}",
                suggestions=[
                    "Check if SSH service is running on target",
                    "Verify port 22 is open",
                    "Check firewall settings"
                ]
            )
        elif "permission denied" in error_msg.lower():
            raise AuthenticationError(
                f"SSH authentication failed: {error_msg}",
                suggestions=[
                    "Check SSH key permissions (should be 600)",
                    "Verify public key is in authorized_keys",
                    "Try ssh-add to add key to agent"
                ]
            )
        elif "timeout" in error_msg.lower():
            raise NetworkError(
                f"SSH connection timeout: {error_msg}",
                suggestions=[
                    "Check network connectivity",
                    "Verify target host is reachable",
                    "Increase connection timeout"
                ]
            )
        else:
            raise SSHError(
                f"SSH command failed: {error_msg}",
                suggestions=[
                    "Check SSH configuration",
                    "Verify target host is accessible",
                    "Try connecting manually first"
                ]
            )
    
    def _handle_generic_error(self, result: subprocess.CompletedProcess, command: str, stdout: str, stderr: str):
        """Handle generic command errors."""
        error_msg = stderr or stdout or f"Command failed with exit code {result.returncode}"
        
        raise SubprocessError(
            f"Command failed: {error_msg}",
            command=command,
            return_code=result.returncode,
            suggestions=[
                "Check command syntax and arguments",
                "Verify all required tools are installed",
                "Check system resources and permissions"
            ]
        )
    
    def kill(self):
        """Kill the running process."""
        if self.process:
            try:
                self.process.kill()
                self.process.wait(timeout=5)
            except (subprocess.TimeoutExpired, ProcessLookupError):
                pass


@contextmanager
def timeout_context(seconds: int):
    """Context manager for operation timeouts."""
    def timeout_handler(signum, frame):
        raise TimeoutError(f"Operation timed out after {seconds} seconds")
    
    # Set up signal handler
    old_handler = signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(seconds)
    
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)


def run_with_retry(
    runner: SubprocessRunner,
    command: Union[str, List[str]],
    max_retries: int = 3,
    delay: float = 1.0,
    backoff_factor: float = 2.0,
    **kwargs
) -> subprocess.CompletedProcess:
    """
    Run command with retry logic.
    
    Args:
        runner: SubprocessRunner instance
        command: Command to run
        max_retries: Maximum number of retries
        delay: Initial delay between retries
        backoff_factor: Delay multiplier for each retry
        **kwargs: Additional arguments for runner.run()
    
    Returns:
        CompletedProcess result
    
    Raises:
        SubprocessError: After all retries failed
    """
    last_error = None
    current_delay = delay
    
    for attempt in range(max_retries + 1):
        try:
            return runner.run(command, **kwargs)
        except (NetworkError, SubprocessError) as e:
            last_error = e
            
            if attempt < max_retries:
                logger.warning(f"Command failed (attempt {attempt + 1}/{max_retries + 1}): {e}")
                logger.info(f"Retrying in {current_delay} seconds...")
                time.sleep(current_delay)
                current_delay *= backoff_factor
            else:
                logger.error(f"Command failed after {max_retries + 1} attempts")
    
    # Add retry context to the error
    if last_error:
        last_error.context["max_retries"] = max_retries
        last_error.context["total_attempts"] = max_retries + 1
        last_error.suggestions.append("The operation was retried multiple times")
    
    raise last_error


# Convenience functions
def run_command(
    command: Union[str, List[str]],
    timeout: int = 300,
    cwd: Optional[Path] = None,
    **kwargs
) -> subprocess.CompletedProcess:
    """Run a single command with error handling."""
    runner = SubprocessRunner(timeout=timeout, cwd=cwd)
    return runner.run(command, **kwargs)


def run_terraform(
    action: str,
    provider: str,
    region: str,
    terraform_dir: Path,
    timeout: int = 600,
    **kwargs
) -> subprocess.CompletedProcess:
    """Run Terraform command with specific error handling."""
    provider_dir = terraform_dir / provider
    
    if not provider_dir.exists():
        raise TerraformError(
            f"Terraform directory not found: {provider_dir}",
            suggestions=[
                "Check provider name is correct",
                "Verify Terraform files exist",
                "Initialize Terraform first"
            ]
        )
    
    runner = SubprocessRunner(timeout=timeout, cwd=provider_dir)
    
    # Build command
    if action == "init":
        command = ["terraform", "init"]
    elif action == "plan":
        command = ["terraform", "plan", f"-var-file=../../state/{provider}-{region}.tfvars.json"]
    elif action == "apply":
        command = ["terraform", "apply", "-auto-approve", f"-var-file=../../state/{provider}-{region}.tfvars.json"]
    elif action == "destroy":
        command = ["terraform", "destroy", "-auto-approve", f"-var-file=../../state/{provider}-{region}.tfvars.json"]
    else:
        command = ["terraform", action]
    
    return runner.run(command, **kwargs)


def run_ansible(
    playbook: str,
    inventory: Optional[str] = None,
    ansible_dir: Optional[Path] = None,
    timeout: int = 600,
    **kwargs
) -> subprocess.CompletedProcess:
    """Run Ansible playbook with specific error handling."""
    runner = SubprocessRunner(timeout=timeout, cwd=ansible_dir)
    
    command = ["ansible-playbook", playbook]
    if inventory:
        command.extend(["-i", inventory])
    
    return runner.run(command, **kwargs)


def run_ssh(
    host: str,
    command: str,
    key_file: Optional[Path] = None,
    user: str = "ubuntu",
    timeout: int = 30,
    **kwargs
) -> subprocess.CompletedProcess:
    """Run SSH command with specific error handling."""
    runner = SubprocessRunner(timeout=timeout)
    
    ssh_cmd = ["ssh"]
    
    # SSH options for security and reliability
    ssh_cmd.extend([
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "UserKnownHostsFile=~/.ssh/known_hosts.proxygen",
        "-o", "ConnectTimeout=10",
        "-o", "ServerAliveInterval=60",
        "-o", "ServerAliveCountMax=3"
    ])
    
    if key_file:
        ssh_cmd.extend(["-i", str(key_file)])
    
    ssh_cmd.append(f"{user}@{host}")
    ssh_cmd.append(command)
    
    return runner.run(ssh_cmd, sensitive_args=[str(key_file)] if key_file else None, **kwargs)