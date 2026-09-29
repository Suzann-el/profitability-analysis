.PHONY: build test mutation clean

build:
	python -m profit build

test:
	pytest tests/ -q

mutation:
	python scripts/mutation_check.py

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; \
	find . -name "*.pyc" -delete 2>/dev/null; \
	rm -rf .pytest_cache; \
	echo "nettoyé"
