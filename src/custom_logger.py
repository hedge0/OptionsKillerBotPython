import logging

CUSTOM_LEVEL_NUM = 15
logging.addLevelName(CUSTOM_LEVEL_NUM, "CUSTOM")

def custom(self, message, *args, **kwargs):
    if self.isEnabledFor(CUSTOM_LEVEL_NUM):
        self._log(CUSTOM_LEVEL_NUM, message, args, **kwargs)

logging.Logger.custom = custom

class CustomFilter(logging.Filter):
    def filter(self, record):
        return record.levelno in (logging.ERROR, CUSTOM_LEVEL_NUM)

def init_custom_logger(log_filename="trade_bot.log"):
    """
    Initializes the custom logger that logs only ERROR and CUSTOM level messages.

    Args:
        log_filename (str): The name of the log file where logs will be written.

    Returns:
        None
    """
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    file_handler = logging.FileHandler(log_filename, mode='w')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    file_handler.addFilter(CustomFilter())

    if logger.hasHandlers():
        logger.handlers.clear()

    logger.addHandler(file_handler)
