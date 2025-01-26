import logging

_LOGGER_ = logging.getLogger(__name__)


def configure_logger(log_file, verbose=0, quiet=0):
    log_level = logging.WARNING + 10 * ((quiet or 0) - (verbose or 0))
    logging.basicConfig(filename=log_file, level=log_level,
                        format='%(asctime)s %(message)s')




