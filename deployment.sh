#!/usr/bin/env bash
set -euo pipefail

if [[ -f .env ]]; then
  echo "Loading environment from .env"
  set -a                 # export every variable read from here on
  # shellcheck disable=SC1091
  source .env
  set +a
fi


: "${RG:=}"
: "${LOC:=}"
: "${APP:=}"
: "${ACR:=}"
: "${CAE:=}"
: "${PORT:=8000}"
: "${BUILD_MODE:=local}"
: "${IMAGE_NAME:=}"
: "${IMAGE_TAG:=}"
: "${PG_DSN:=}"

: "${AZURE_OPENAI_ENDPOINT:=}"
: "${OPENAI_API_VERSION:=}"
: "${AZURE_OPENAI_DEPLOYMENT_NAME:=}"
: "${AZURE_OPENAI_API_KEY:=}"
: "${AZURE_OPENAI_VERSION:=}"

# Ensure key configuration is present before we touch Azure.
require_var() {
  local name="$1"; shift
  local description="$*"
  if [[ -z "${!name:-}" ]]; then
    echo "error: environment variable $name is required (${description:-no description provided})." >&2
    exit 1
  fi
}

require_var RG "resource group"
require_var LOC "Azure region (e.g. westeurope)"
require_var APP "Container App name"
CAE="${CAE:-${APP}-env}"
require_var CAE "Container Apps environment name"
require_var AZURE_OPENAI_ENDPOINT "Azure OpenAI endpoint URL"
require_var OPENAI_API_VERSION "Azure OpenAI API version"
require_var AZURE_OPENAI_DEPLOYMENT_NAME "Azure OpenAI deployment name"
require_var AZURE_OPENAI_API_KEY "Azure OpenAI API key"
require_var AZURE_OPENAI_VERSION "Azure OpenAI version"
require_var PG_DSN "Postgres DSN"


PORT="${PORT:-8000}"
BUILD_MODE="${BUILD_MODE:-local}"  # local|remote
IMAGE_NAME="${IMAGE_NAME:-$APP}"
if [[ -z "$IMAGE_TAG" ]]; then
  IMAGE_TAG=$(date +%Y%m%d%H%M%S)
fi

echo "Using image tag: $IMAGE_TAG"

echo "Using resource group: $RG"
if ! az group show -n "$RG" >/dev/null 2>&1; then
  echo "error: resource group $RG not found." >&2
  exit 1
fi

# Create (or reuse) ACR
ACR="${ACR:-}"
if [[ -z "$ACR" ]]; then
  ACR="acr$RANDOM$RANDOM"
  echo "ACR not specified. Creating new registry: $ACR"
fi

if ! az acr show -g "$RG" -n "$ACR" >/dev/null 2>&1; then
  echo "Provisioning Azure Container Registry: $ACR"
  az acr create -g "$RG" -n "$ACR" --sku Basic --location "$LOC" >/dev/null
else
  echo "Reusing Azure Container Registry: $ACR"
fi

IMAGE_REPO="$ACR.azurecr.io/$IMAGE_NAME"
IMAGE="$IMAGE_REPO:$IMAGE_TAG"
IMAGE_LATEST="$IMAGE_REPO:latest"
BUILD_IMAGE_REF="$IMAGE_NAME:$IMAGE_TAG"

echo "Image reference: $IMAGE"

if [[ "$BUILD_MODE" == "remote" ]]; then
  echo "Building image remotely with ACR (this can take a few minutes)…"
  az acr build \
    --registry "$ACR" \
    --image "$BUILD_IMAGE_REF" \
    --image "$IMAGE_NAME:latest" \
    . >/dev/null
else
  if ! command -v docker >/dev/null 2>&1; then
    echo "error: docker CLI not found. Install Docker or set BUILD_MODE=remote to use az acr build." >&2
    exit 1
  fi

  echo "Building image locally and pushing to ACR…"
  az acr login -n "$ACR" >/dev/null
  docker build -t "$IMAGE" -t "$IMAGE_LATEST" . >/dev/null
  docker push "$IMAGE" >/dev/null
  docker push "$IMAGE_LATEST" >/dev/null
fi

# Create (or reuse) Container Apps Environment
if ! az containerapp env show -g "$RG" -n "$CAE" >/dev/null 2>&1; then
  echo "Creating Container Apps environment: $CAE"
  az containerapp env create -g "$RG" -n "$CAE" -l "$LOC" >/dev/null
else
  echo "Reusing Container Apps environment: $CAE"
fi

# Create or update Container App
if ! az containerapp show -g "$RG" -n "$APP" >/dev/null 2>&1; then
  echo "Creating Container App: $APP"
  az containerapp create \
    -g "$RG" -n "$APP" \
    --environment "$CAE" \
    --image "$IMAGE" \
    --ingress external --target-port "$PORT" \
    --min-replicas 1 --max-replicas 2 \
    --registry-server "$ACR.azurecr.io" \
    --registry-identity system \
    --secrets openai-key="$AZURE_OPENAI_API_KEY" \
    --env-vars \
      PORT="$PORT" \
      AZURE_OPENAI_ENDPOINT="$AZURE_OPENAI_ENDPOINT" \
      OPENAI_API_VERSION="$OPENAI_API_VERSION" \
      AZURE_OPENAI_DEPLOYMENT="$AZURE_OPENAI_DEPLOYMENT_NAME" \
      AZURE_OPENAI_API_KEY=secretref:openai-key \
      AZURE_OPENAI_VERSION="$AZURE_OPENAI_VERSION" \
      PG_DSN="$PG_DSN" >/dev/null
else
  echo "Updating Container App: $APP"
  az containerapp secret set \
    -g "$RG" -n "$APP" \
    --secrets openai-key="$AZURE_OPENAI_API_KEY" >/dev/null

  az containerapp update \
    -g "$RG" -n "$APP" \
    --image "$IMAGE" \
    --min-replicas 1 \
    --max-replicas 2 \
    --set-env-vars \
      PORT="$PORT" \
      AZURE_OPENAI_ENDPOINT="$AZURE_OPENAI_ENDPOINT" \
      OPENAI_API_VERSION="$OPENAI_API_VERSION" \
      AZURE_OPENAI_DEPLOYMENT="$AZURE_OPENAI_DEPLOYMENT_NAME" \
      AZURE_OPENAI_API_KEY=secretref:openai-key \
      AZURE_OPENAI_VERSION="$AZURE_OPENAI_VERSION" \
      PG_DSN="$PG_DSN" >/dev/null

  az containerapp ingress update \
    -g "$RG" -n "$APP" \
    --type external \
    --target-port "$PORT" >/dev/null
fi

FQDN=$(az containerapp show -g "$RG" -n "$APP" --query "properties.configuration.ingress.fqdn" -o tsv)
echo "✅ Deployed. Public URL: https://$FQDN"
echo "Health check:  curl https://$FQDN/health"
