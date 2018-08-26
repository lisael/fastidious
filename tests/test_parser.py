from unittest import TestCase

from fastidious.parser_base import ParserMixin


class ParserMixinTest(TestCase):
    def current_pos(self, parser):
        return (parser.p_current_line, parser.p_current_col)

    def forward(self, p, num):
        for _ in range(num):
            p.p_next()

    def test_current_col_line(self):
        p = ParserMixin("""abc
def
ghi""")
        self.assertEqual(self.current_pos(p), (0, 0))
        p.p_next()
        self.assertEqual(self.current_pos(p), (0, 1))
        self.forward(p, 3)
        self.assertEqual(self.current_pos(p), (1, 1))
        self.forward(p, 4)
        self.assertEqual(self.current_pos(p), (2, 1))
        self.forward(p, 12)
        self.assertEqual(self.current_pos(p), (2, 4))
