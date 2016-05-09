import re  # noqa
from unittest import TestCase

from fastidious.expressions import *  # noqa
from fastidious import Parser
from fastidious import ParserError


class ErrorHandlingTests(TestCase):
    def test_error(self):
        class Simple(Parser):
            __grammar__ = r"""
            calc <- num _ operator _ num EOF
            num "NUMBER" <-  frac / "-"? int
            int <- ~"[0-9]+"
            frac <- int "." int
            operator "OPERATOR" <- '+' / '-'
            _ <- [ \t\r]*
            EOF <- !.
            """
        Simple.p_parse("1 + 1")
        with self.assertRaisesRegexp(ParserError,
                                     "Got `! 1` expected OPERATOR"):
            Simple.p_parse("1 ! 1")
