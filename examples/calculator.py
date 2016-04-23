#! /usr/bin/python
from fastidious import Parser


class Calculator(Parser):
    __grammar__ = r"""
    eval <- e:expr EOF {@e}
    expr <- _ first:term rest:( _ add_op _ term  )* _ {on_expr}
    term <- first:factor rest:( _ mult_op _ factor )* {on_expr}
    add_op <- '+' / '-'
    mult_op <- '*' / '/'
    factor <- ( '(' factor:expr ')' ) / factor:integer {@factor}
    integer <- '-'? [0-9]+ {on_integer}
    _ <- [ \n\t\r]*
    EOF <- !.
    """

    def on_expr(self, value, first, rest):
        result = first
        for r in rest:
            op = r[1]
            if op == '+':
                result += r[3]
            elif op == '-':
                result -= r[3]
            elif op == '*':
                result *= r[3]
            else:
                result /= r[3]
        return result

    def on_integer(self, value):
        return int(self.flatten(value))

if __name__ == "__main__":
    import sys
    print Calculator("".join(sys.argv[1:])).eval()
