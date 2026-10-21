.PHONY: test eval run cli docker-build

test:
	python3 -m unittest discover -s tests -p "test_*.py" -v

eval:
	python3 eval/eval_harness.py

run:
	python3 app.py

cli:
	python3 cli.py

docker-build:
	docker build -t cloud-finops-copilot:latest .
