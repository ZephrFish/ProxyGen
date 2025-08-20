#!/usr/bin/env python3
"""
Progress bar utility for ProxyGen operations.
Provides visual feedback for long-running operations.
"""

import time
import sys
import threading
from typing import Optional, Callable, Any


class ProgressBar:
    """Simple progress bar for command line operations."""
    
    def __init__(self, total: int = 100, width: int = 50, description: str = "Processing"):
        """Initialize progress bar.
        
        Args:
            total: Total number of steps
            width: Width of progress bar in characters
            description: Description text to display
        """
        self.total = total
        self.width = width
        self.description = description
        self.current = 0
        self.start_time = time.time()
        
    def update(self, step: int = 1, description: Optional[str] = None):
        """Update progress bar.
        
        Args:
            step: Number of steps to advance
            description: Update description text
        """
        self.current = min(self.current + step, self.total)
        if description:
            self.description = description
        self._draw()
        
    def set_progress(self, current: int, description: Optional[str] = None):
        """Set absolute progress.
        
        Args:
            current: Current progress value
            description: Update description text
        """
        self.current = min(current, self.total)
        if description:
            self.description = description
        self._draw()
    
    def _draw(self):
        """Draw the progress bar."""
        if self.total == 0:
            return
            
        percent = (self.current / self.total) * 100
        filled_width = int(self.width * self.current // self.total)
        
        # Create bar
        bar = '#' * filled_width + '-' * (self.width - filled_width)
        
        # Calculate elapsed time and ETA
        elapsed = time.time() - self.start_time
        if self.current > 0:
            eta = (elapsed / self.current) * (self.total - self.current)
            eta_str = f"ETA: {self._format_time(eta)}"
        else:
            eta_str = "ETA: --:--"
        
        # Format output
        output = f"\r{self.description}: [{bar}] {percent:5.1f}% {self.current}/{self.total} - {eta_str}"
        
        # Write to stdout
        sys.stdout.write(output)
        sys.stdout.flush()
        
        # Add newline when complete
        if self.current >= self.total:
            sys.stdout.write('\n')
            sys.stdout.flush()
    
    def _format_time(self, seconds: float) -> str:
        """Format time in MM:SS format."""
        minutes = int(seconds // 60)
        seconds = int(seconds % 60)
        return f"{minutes:02d}:{seconds:02d}"
    
    def finish(self):
        """Complete the progress bar."""
        self.current = self.total
        self._draw()


class SpinnerProgress:
    """Spinning progress indicator for indeterminate operations."""
    
    def __init__(self, description: str = "Processing"):
        """Initialize spinner.
        
        Args:
            description: Description text to display
        """
        self.description = description
        self.spinning = False
        self.spinner_chars = ['|', '/', '-', '\\']
        self.spinner_index = 0
        self.thread = None
        
    def start(self):
        """Start the spinner."""
        self.spinning = True
        self.thread = threading.Thread(target=self._spin)
        self.thread.daemon = True
        self.thread.start()
        
    def stop(self, final_message: Optional[str] = None):
        """Stop the spinner.
        
        Args:
            final_message: Optional final message to display
        """
        self.spinning = False
        if self.thread:
            self.thread.join()
        
        # Clear spinner line
        sys.stdout.write('\r' + ' ' * (len(self.description) + 10) + '\r')
        
        if final_message:
            sys.stdout.write(final_message + '\n')
        
        sys.stdout.flush()
        
    def update_description(self, description: str):
        """Update the description text.
        
        Args:
            description: New description text
        """
        self.description = description
        
    def _spin(self):
        """Internal spinner animation."""
        while self.spinning:
            spinner_char = self.spinner_chars[self.spinner_index]
            output = f"\r{self.description} {spinner_char}"
            sys.stdout.write(output)
            sys.stdout.flush()
            
            self.spinner_index = (self.spinner_index + 1) % len(self.spinner_chars)
            time.sleep(0.1)


class StepProgress:
    """Step-by-step progress tracker for complex operations."""
    
    def __init__(self, steps: list, description: str = "Operation"):
        """Initialize step progress.
        
        Args:
            steps: List of step descriptions
            description: Overall operation description
        """
        self.steps = steps
        self.description = description
        self.current_step = 0
        self.total_steps = len(steps)
        self.start_time = time.time()
        
    def start_step(self, step_index: Optional[int] = None, description: Optional[str] = None):
        """Start a specific step.
        
        Args:
            step_index: Index of step to start (None for next step)
            description: Override step description
        """
        if step_index is not None:
            self.current_step = step_index
        
        step_desc = description or self.steps[self.current_step]
        elapsed = time.time() - self.start_time
        
        output = f"[{self.current_step + 1}/{self.total_steps}] {step_desc}... ({self._format_time(elapsed)})"
        print(output)
        
    def complete_step(self, message: Optional[str] = None):
        """Complete current step.
        
        Args:
            message: Optional completion message
        """
        if message:
            print(f"  ✓ {message}")
        else:
            print(f"  ✓ Completed")
        
        self.current_step += 1
        
    def fail_step(self, error_message: str):
        """Mark current step as failed.
        
        Args:
            error_message: Error description
        """
        print(f"  ✗ Failed: {error_message}")
        
    def finish(self, message: Optional[str] = None):
        """Complete all steps.
        
        Args:
            message: Optional final message
        """
        elapsed = time.time() - self.start_time
        final_msg = message or f"{self.description} completed"
        print(f"\n{final_msg} (Total time: {self._format_time(elapsed)})")
        
    def _format_time(self, seconds: float) -> str:
        """Format time in MM:SS format."""
        minutes = int(seconds // 60)
        seconds = int(seconds % 60)
        return f"{minutes:02d}:{seconds:02d}"


def with_progress_bar(total: int, description: str = "Processing"):
    """Decorator to add progress bar to functions.
    
    Args:
        total: Total number of steps
        description: Progress description
        
    Returns:
        Decorator function
    """
    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs) -> Any:
            progress = ProgressBar(total, description=description)
            
            # Add progress callback to kwargs if function accepts it
            if 'progress_callback' in func.__code__.co_varnames:
                kwargs['progress_callback'] = progress.update
                
            try:
                result = func(*args, **kwargs)
                progress.finish()
                return result
            except Exception as e:
                progress.finish()
                raise
                
        return wrapper
    return decorator


def with_spinner(description: str = "Processing"):
    """Decorator to add spinner to functions.
    
    Args:
        description: Spinner description
        
    Returns:
        Decorator function
    """
    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs) -> Any:
            spinner = SpinnerProgress(description)
            spinner.start()
            
            try:
                result = func(*args, **kwargs)
                spinner.stop("Completed")
                return result
            except Exception as e:
                spinner.stop(f"Failed: {str(e)}")
                raise
                
        return wrapper
    return decorator