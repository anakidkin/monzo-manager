import logging
import os
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path


def setup_rotating_logger():
    # Define the default path using pathlib
    script_path = Path(__file__).resolve()
    default_log_dir = script_path.parent.parent / "logs"

    # Get the path from the environment variable (it will be a string or None)
    log_path_from_env = os.environ.get('LOG_PATH')

    # Decide which path to use and ensure the final result is a Path object
    if log_path_from_env:
        # If the environment variable is set, use it and convert it to a Path object
        log_dir = Path(log_path_from_env)
    else:
        # Otherwise, use the default Path object
        log_dir = default_log_dir

    # Create the log directory if it does not exist
    try:
        os.makedirs(log_dir, exist_ok=True)
        print(f"Logs will be stored in: {log_dir}")
    except OSError as e:
        print(f"Error: Could not create log directory {log_dir}. {e}")
        # Fallback to a temporary directory or handle the error as needed
        # For this example, we'll just print the error and continue
        # In a real app, you might want to exit or use a default temp dir
        log_dir = "/tmp/"

    # --- Logger Configuration ---

    logger = logging.getLogger("MonzoLogger")
    logger.setLevel(logging.INFO)

    # Prevent log messages from being propagated to the root logger
    logger.propagate = False

    # Define the log file name and path
    log_file_path = os.path.join(log_dir, 'app.log')

    # Create a timed rotating file handler
    # Rotates at midnight, creates a new file daily, and keeps 30 old files
    handler = TimedRotatingFileHandler(
        log_file_path,
        when="midnight",
        interval=1,
        backupCount=30,
        encoding='utf-8'
    )

    # Set the format for the log messages
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    handler.setFormatter(formatter)

    # Add the handler to the logger if it's not already added
    if not logger.handlers:
        logger.addHandler(handler)

        # Also add a handler to print to console for immediate feedback
        # (optional, but useful for development)
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger
