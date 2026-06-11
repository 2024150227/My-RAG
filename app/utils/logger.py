import logging
import time
from uuid import uuid4

class RequestIdFilter(logging.Filter):
    def __init__(self):
        self.request_id = str(uuid4())
    
    def filter(self, record):
        record.request_id = getattr(record, 'request_id', self.request_id)
        return True

def get_logger(name: str = __name__) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    
    if not logger.handlers:
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(request_id)s - %(message)s'
        )
        
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        console_handler.setFormatter(formatter)
        console_handler.addFilter(RequestIdFilter())
        
        logger.addHandler(console_handler)
    
    return logger

logger = get_logger("rag_system")