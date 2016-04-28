# Fastidious
A python PEG parser generator

## Usage
From [the calculator example](examples/calculator.py)

```python
#! /usr/bin/python
from fastidious import Parser


class Calculator(Parser):
    __grammar__ = r"""
    eval <- :expr EOF {@expr}
    expr <- _ first:term rest:( _ add_op _ term  )* _
    term <- first:factor rest:( _ mult_op _ factor )* {on_expr}
    add_op <- '+' / '-'
    mult_op <- '*' / '/'
    factor <- ( '(' factor:expr ')' ) / factor:integer {@factor}
    integer <- '-'? [0-9]+
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
    c = Calculator("".join(sys.argv[1:]))
    print(c.eval())
```
Then you have a full-fledge state-of-the-art integer only calculator \o/

```sh
examples/calculator.py " -21 *  ( 3 + 1 ) / -2"
42
```

## TODO
- make it pip installable
- add error reporting using this paper http://arxiv.org/pdf/1405.6646v1.pdf
- make a tool to generate standalone modules
- python3
- more tests
- tox
- travis


