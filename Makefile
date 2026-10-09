REGISTRY  := ghcr.io/ptinkler
IMAGE_APP := $(REGISTRY)/pollo-api
IMAGE_NGX := $(REGISTRY)/pollo-nginx
TAG       := latest

.PHONY: build push tag dev dev-api dev-frontend lint format test hooks vpn-restart vpn-status vpn-logs db-migrate db-upgrade db-downgrade db-history

build:
	docker build -t $(IMAGE_APP):$(TAG) .
	docker build -f nginx/Dockerfile -t $(IMAGE_NGX):$(TAG) .

push: build
	docker push $(IMAGE_APP):$(TAG)
	docker push $(IMAGE_NGX):$(TAG)

tag:
	$(eval LATEST := $(shell git tag --sort=-version:refname | head -1 || echo "v0.0.0"))
	$(eval PATCH  := $(shell echo $(LATEST) | awk -F. '{print $$3+1}'))
	$(eval NEXT   := $(shell echo $(LATEST) | awk -F. -v p=$(PATCH) '{print $$1"."$$2"."p}'))
	git tag $(NEXT) && git push origin $(NEXT)

dev-api:
	.venv/bin/python -m uvicorn web.api:app --reload --port 5000

dev-frontend:
	cd web/frontend && npm run dev

dev:
	$(MAKE) -j2 dev-api dev-frontend

# Code standards: ruff (Python) and ESLint + Prettier (frontend). CI runs `lint`.
lint:
	.venv/bin/ruff check .
	.venv/bin/ruff format --check .
	cd web/frontend && npm run lint && npm run format:check

format:
	.venv/bin/ruff check --fix .
	.venv/bin/ruff format .
	cd web/frontend && npm run lint:fix && npm run format

# Run the lint checks on every commit (.githooks/pre-commit runs .pre-commit-config.yaml;
# from git for Windows it runs them inside WSL)
hooks:
	git config core.hooksPath .githooks

test:
	.venv/bin/python -m pytest -q
	cd web/frontend && npm test

vpn-restart:
	docker restart pollo-vpn

vpn-status:
	docker exec pollo-vpn cat /tmp/gluetun/ip
	@echo "---"
	docker exec pollo-vpn wget -qO- ifconfig.me 2>/dev/null || echo "(could not reach ifconfig.me)"

vpn-logs:
	docker logs pollo-vpn --tail 30

# ── Database migrations (Alembic) ──────────────────
db-migrate:  ## Generate a new migration: make db-migrate msg="add foo column"
	alembic revision --autogenerate -m "$(msg)"

db-upgrade:  ## Apply all pending migrations
	alembic upgrade head

db-downgrade:  ## Revert the last migration
	alembic downgrade -1

db-history:  ## Show migration history
	alembic history --verbose
