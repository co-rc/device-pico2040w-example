import unittest
import logging
import io
import sys
import os

class TestLogging(unittest.TestCase):
    def setUp(self):
        # Reset logging state before each test
        logging.shutdown()
        # Clear root handlers manually just in case
        root = logging.getLogger()
        root.handlers = []
        root.setLevel(logging.WARNING)

    def test_basic_logging(self):
        log_stream = io.StringIO()
        logging.basicConfig(stream=log_stream, level=logging.DEBUG, format="%(levelname)s:%(message)s")
        
        logger = logging.getLogger("test")
        logger.debug("debug message")
        logger.info("info message")
        logger.warning("warning message")
        
        output = log_stream.getvalue()
        self.assertIn("DEBUG:debug message\n", output)
        self.assertIn("INFO:info message\n", output)
        self.assertIn("WARNING:warning message\n", output)

    def test_flexible_formatting(self):
        log_stream = io.StringIO()
        logging.basicConfig(stream=log_stream, level=logging.DEBUG, format="%(message)s")
        
        logger = logging.getLogger("test")
        # Standard printf style
        logger.info("value: %d", 123)
        # Dictionary style
        logger.info("value: %(val)d", {"val": 456})
        # Appending style (custom feature)
        logger.info("new connection:", "BleConn", 1)
        
        output = log_stream.getvalue()
        self.assertIn("value: 123\n", output)
        self.assertIn("value: 456\n", output)
        self.assertIn("new connection: BleConn 1\n", output)

    def test_concurrency_record_isolation(self):
        # In a real concurrent scenario this is hard to test deterministically without mocks,
        # but we can verify that each call produces a distinct record conceptually.
        records = []
        class CaptureHandler(logging.Handler):
            def emit(self, record):
                records.append(record)
        
        logger = logging.getLogger("iso")
        logger.setLevel(logging.DEBUG) # Ensure logger is enabled
        handler = CaptureHandler()
        logger.addHandler(handler)
        
        logger.info("msg 1")
        logger.info("msg 2")
        
        self.assertEqual(len(records), 2)
        self.assertNotEqual(records[0], records[1])
        self.assertEqual(records[0].message, "msg 1")
        self.assertEqual(records[1].message, "msg 2")

    def test_shutdown(self):
        log_stream = io.StringIO()
        logging.basicConfig(stream=log_stream)
        logger = logging.getLogger("to_shutdown")
        
        self.assertTrue(len(logging.getLogger().handlers) > 0)
        logging.shutdown()
        self.assertEqual(len(logging._loggers), 0)

    def test_remove_handler(self):
        root = logging.getLogger()
        handler = logging.StreamHandler()
        root.addHandler(handler)
        self.assertIn(handler, root.handlers)
        
        root.removeHandler(handler)
        self.assertNotIn(handler, root.handlers)

    def test_exception_logging(self):
        log_stream = io.StringIO()
        # Redirect stderr to capture print_exception output if it falls back to it
        old_stderr = sys.stderr
        sys.stderr = log_stream
        try:
            logging.basicConfig(stream=log_stream, level=logging.ERROR)
            logger = logging.getLogger("test_exc")
            try:
                1/0
            except ZeroDivisionError:
                logger.exception("Something went wrong")
            
            output = log_stream.getvalue()
            self.assertIn("ERROR:test_exc:Something went wrong", output)
            self.assertIn("ZeroDivisionError", output)
        finally:
            sys.stderr = old_stderr

if __name__ == "__main__":
    unittest.main()
