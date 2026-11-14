from functools import wraps
import time
import logging
from flask import jsonify
from typing import Callable, Any, Tuple, Optional
import requests
from backend.network.config import REQUEST_TIMEOUT


def add_timing(func):
    """Decorator to add response time to the JSON response"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs) #this calls the decorated function
        end_time = time.time()
        print(f"{func.__name__} took {end_time -start_time} sec")
        return result
    return wrapper


def handle_exceptions(func):
    """
    Convert exceptions into Flask JSON responses.

    ONLY use this on Flask route handlers. It returns ``(jsonify(...), status)``
    tuples, which breaks the return contract of data-layer functions
    (fetch/parsers/services) and causes errors to be swallowed silently.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except FileNotFoundError:
            logging.error(f"File not found  in {func.__name__}") 
            return jsonify({"Error":"Data file not found"}),500
        except ValueError as e:
            logging.error(f"Value error in {func.__name__}:{str(e)}")
            return jsonify({"Error":"Invalid data format"}),400
        
        except Exception as e:
            logging.error(f"Unexpected error in {func.__name__}: {str(e)}")
            return jsonify({"Error":"Internal server error"}),500
    return wrapper    
    

def handle_service_exception(func):
    """Decorator to handle exceptions in services"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except FileNotFoundError:
            logging.error(f"File not found in {func.__name__}")
            return None
        except ValueError as e:
            logging.error(f"Value error in {func.__name__}:{str(e)}")
            return None
        except Exception as e:
            logging.error(f"Unexpected error in {func.__name__}:{str(e)}")
            return None
    return wrapper


def handle_http_request_exception(func):
    """ Decorator to handle http request exceptions"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        
        except requests.Timeout:
            error_message = f"ARSO API request timeout after {REQUEST_TIMEOUT} seconds"
            logging.error(error_message)
            return False, None, error_message
        
        except requests.ConnectionError as e:
            error_message = f"Cannot connect to ARSO, check your internet connection: {str(e)}"
            logging.error(error_message)
            return False, None, error_message

        except requests.RequestException as e:
            error_message = f"HTTP request to ARSO failed: {str(e)}"
            logging.error(error_message)
            return False, None, error_message

    return wrapper



    


