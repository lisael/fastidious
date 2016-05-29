from unittest import TestCase

from fastidious import Parser


class Parent(Parser):
    __grammar__ = r"""
    parent_letters <- some_as some_cs {p_flatten}
    some_as <- 'a'+
    some_cs <- 'C'+
    """


class Child(Parent):
    __grammar__ = r"""
    letters <- some_as some_bs some_cs EOF {p_flatten}
    some_bs <- 'b'+
    some_cs <- 'c'*
    EOF <- !.
    """


class ParserInheritanceTest(TestCase):
    def test_parent(self):
        result = Parent.p_parse("aaC")
        self.assertEquals(result, 'aaC')

    def test_child(self):
        result = Child.p_parse("aaabbb")
        self.assertEquals(result, "aaabbb")

    def test_override(self):
        result = Child.p_parse("aaabbbcc")
        self.assertEquals(result, "aaabbbcc")
