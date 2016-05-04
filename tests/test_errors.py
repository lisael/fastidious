import re  # noqa
from unittest import TestCase

from fastidious.expressions import *  # noqa
from fastidious import Parser


class ErrorHandlingTests(TestCase):
    def test_error(self):
        class Simple(Parser):
            __code_gen__ = True
            __debug___ = True
            __grammar__ = r"""
            calc <- num _ operator _ num EOF
            num <-  frac / "-"? int
            int <- ~"[0-9]+"
            frac <- int "." int
            `operator "OPERATOR" <- '+' / '-'
            _ <- [ \t\r]*
            EOF <- !.
            """
        correct = Simple("1 + 1")
        false = Simple("1 + 1error")
        Simple.p_parse("1 * 1")
        import ipdb; ipdb.set_trace()  # XXX BREAKPOINT

