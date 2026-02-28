#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 4 ]]; then
  cat <<'USAGE'
Usage:
  ./scripts/deploy_azure_webapp.sh <subscription_id> <resource_group> <location> <app_name>

Example:
  ./scripts/deploy_azure_webapp.sh 00000000-0000-0000-0000-000000000000 rg-ratebench eastus ratebench-prod
USAGE
  exit 1
fi

SUBSCRIPTION_ID="$1"
RESOURCE_GROUP="$2"
LOCATION="$3"
APP_NAME="$4"
PLAN_NAME="${APP_NAME}-plan"
ACR_NAME="${APP_NAME//-/}acr"
IMAGE_NAME="rate-benchmark-web"
IMAGE_TAG="$(date +%Y%m%d%H%M%S)"
IMAGE_FQN="${ACR_NAME}.azurecr.io/${IMAGE_NAME}:${IMAGE_TAG}"

command -v az >/dev/null 2>&1 || { echo "Azure CLI (az) is required."; exit 1; }

echo "Setting subscription..."
az account set --subscription "${SUBSCRIPTION_ID}"

echo "Creating resource group..."
az group create --name "${RESOURCE_GROUP}" --location "${LOCATION}" >/dev/null

echo "Creating Azure Container Registry..."
az acr create \
  --resource-group "${RESOURCE_GROUP}" \
  --name "${ACR_NAME}" \
  --sku Basic \
  --admin-enabled true >/dev/null

echo "Building and pushing image from Dockerfile.web..."
az acr build \
  --registry "${ACR_NAME}" \
  --image "${IMAGE_NAME}:${IMAGE_TAG}" \
  --file Dockerfile.web \
  . >/dev/null

echo "Creating App Service plan..."
az appservice plan create \
  --name "${PLAN_NAME}" \
  --resource-group "${RESOURCE_GROUP}" \
  --is-linux \
  --sku B1 >/dev/null

echo "Creating Web App..."
az webapp create \
  --resource-group "${RESOURCE_GROUP}" \
  --plan "${PLAN_NAME}" \
  --name "${APP_NAME}" \
  --deployment-container-image-name "${IMAGE_FQN}" >/dev/null

echo "Configuring registry credentials and app settings..."
ACR_USERNAME="$(az acr credential show --name "${ACR_NAME}" --query username -o tsv)"
ACR_PASSWORD="$(az acr credential show --name "${ACR_NAME}" --query passwords[0].value -o tsv)"

az webapp config container set \
  --name "${APP_NAME}" \
  --resource-group "${RESOURCE_GROUP}" \
  --container-image-name "${IMAGE_FQN}" \
  --container-registry-url "https://${ACR_NAME}.azurecr.io" \
  --container-registry-user "${ACR_USERNAME}" \
  --container-registry-password "${ACR_PASSWORD}" >/dev/null

az webapp config appsettings set \
  --name "${APP_NAME}" \
  --resource-group "${RESOURCE_GROUP}" \
  --settings WEBSITES_PORT=8000 SCM_DO_BUILD_DURING_DEPLOYMENT=false >/dev/null

URL="https://${APP_NAME}.azurewebsites.net"
echo
printf 'Deployment complete.\nURL: %s\nImage: %s\n' "${URL}" "${IMAGE_FQN}"
