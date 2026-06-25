import sys

class TestCLI:
    def test_help(self):
        from etf_platform.cli import app
        old = sys.argv
        try:
            sys.argv = ["etf", "--help"]
            app()
        finally:
            sys.argv = old

    def test_run_no_code(self):
        from etf_platform.cli import app
        old = sys.argv
        try:
            sys.argv = ["etf", "run"]
            app()
        finally:
            sys.argv = old

    def test_unknown_cmd(self):
        from etf_platform.cli import app
        old = sys.argv
        try:
            sys.argv = ["etf", "foobar"]
            app()
        finally:
            sys.argv = old
