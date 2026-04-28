FILES=converter icons icon.png info.plist poscUnits22.xml README.rst
OUTFILE=unit_converter.alfredworkflow
ZIP_EXCLUDES=*.pyc *__pycache__* *.tmp *.tmp.* .DS_Store */.DS_Store units.pickle */units.pickle htmlcov/* tests/* docs/*
ZIP_EXCLUDE_ARGS=$(foreach pattern,${ZIP_EXCLUDES},--exclude '${pattern}')

.PHONY: all clean

all:
	rm -vf ${OUTFILE} units.pickle
	zip --recurse-paths --verbose ${OUTFILE} ${FILES} ${ZIP_EXCLUDE_ARGS}

clean:
	rm -vf ${OUTFILE} units.pickle
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +
	find . -name '*.pyc' -delete
	find . -name '*.tmp' -delete
	rm -rf htmlcov .pytest_cache .tox
