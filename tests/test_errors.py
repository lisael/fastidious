from unittest import TestCase

from fastidious import Parser
from fastidious import ParserError
from fastidious.parser import NewParser


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

    def test_new_error(self):
        class Simple(NewParser):
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
