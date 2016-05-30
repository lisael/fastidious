flake:
	flake8 fastidious tests examples

_test:
	nosetests -s ./tests/

_vtest:
	nosetests -s -v ./tests/

test: flake _test

vtest: flake _vtest

_cov: 
	nosetests -s --with-cover --cover-html --cover-branches --cover-html-dir ./coverage ./tests/
	@echo "open file://`pwd`/coverage/index.html"

cov: flake _cov

clean:
	rm -rf `find . -name __pycache__`
	rm -f `find . -type f -name '*.py[co]' `
	rm -f `find . -type f -name '*~' `
	rm -f `find . -type f -name '.*~' `
	rm -f `find . -type f -name '@*' `
	rm -f `find . -type f -name '#*#' `
	rm -f `find . -type f -name '*.orig' `
	rm -f `find . -type f -name '*.rej' `
	rm -f .coverage
	rm -rf coverage
	rm -rf build
	rm -rf cover

doc:
	make -C docs html
	@echo "open file://`pwd`/docs/_build/html/index.html"

.PHONY: all build venv flake test vtest _cov cov clean doc _test _vtest
