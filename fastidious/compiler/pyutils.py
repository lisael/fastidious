"""
Utility functions to generate python code.
"""


def indent(code, space):
    ind = " " * space * 4
    return ind + ("\n" + ind).join([l for l in code.splitlines()])
