.PHONY: help install test corpus tick probe rename
# Prefer the project venv when it exists, so `make test` and `make scan` work
# without remembering to activate it first. Falls back to the system
# interpreter, which is what `make install` bootstraps from.
PY := $(shell [ -x .venv/bin/python ] && echo .venv/bin/python || echo python3)

help:
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-10s\033[0m %s\n",$$1,$$2}'

install:  ## create venv and install deps
	$(PY) -m venv .venv && .venv/bin/pip install -q -r requirements.txt
	@echo "run: source .venv/bin/activate"

test:  ## run the full suite (no cloud credentials needed)
	$(PY) -m pytest -q

corpus:  ## generate the synthetic case corpus
	PYTHONPATH=src $(PY) scripts/generate_corpus.py -n 40

corpora:  ## fetch the benign skill corpus used as a false-positive control
	./scripts/fetch_corpora.sh

scan:  ## scan a skill folder: make scan SKILL=data/replicas/credential-helper
	@test -n "$(SKILL)" || (echo "usage: make scan SKILL=<path> [ARGS=--structural-only]"; exit 1)
	PYTHONPATH=src $(PY) -m hopscotch.skills.cli $(SKILL) $(ARGS)

tick:  ## run one tick locally against Firestore
	PYTHONPATH=src $(PY) -m hopscotch.jobs.tick

probe:  ## day-1 provisioning probe
	./deploy/probe.sh

rename:  ## rename the project: make rename NAME=SixtyDays
	@test -n "$(NAME)" || (echo "usage: make rename NAME=YourName"; exit 1)
	@slug=$$(echo "$(NAME)" | tr '[:upper:]' '[:lower:]'); \
	grep -rl -e hopscotch -e Hopscotch . --exclude-dir=.git --exclude-dir=.venv \
	  | xargs sed -i '' -e "s/Hopscotch/$(NAME)/g" -e "s/hopscotch/$$slug/g"; \
	git mv src/hopscotch src/$$slug 2>/dev/null || mv src/hopscotch src/$$slug; \
	echo "renamed to $(NAME) ($$slug) -- review with git diff before committing"

diagrams:  ## re-render docs/diagrams/*.mmd to PNG (needs node)
	@cd docs/diagrams && for f in *.mmd; do \
	  npx -y @mermaid-js/mermaid-cli@11 -i "$$f" -o "$${f%.mmd}.png" \
	    -c mermaid-config.json -b white -s 3 --quiet; \
	done && echo "rendered $$(ls docs/diagrams/*.png | wc -l | tr -d ' ') diagrams"
