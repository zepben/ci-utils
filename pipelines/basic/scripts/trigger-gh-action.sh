#!/bin/bash
# Trigers Github actions

source "$(dirname "$0")/common.sh"

extra_args=""
if [[ "${DEBUG}" == "true" ]]; then
  info "Enabling debug mode."
  extra_args="--verbose"
fi

# mandatory variables
CI_GH_TOKEN=${CI_GH_TOKEN:?'Github token variable missing.'}
EVENT_TYPE=${1:?'Event type variable missing.'}
PRODUCT_KEY=${2:?'Product key variable missing.'}
DOWNLOAD_URL=${3:?'Downloas url variable missing.'}
GH_DOCS_URL=${GH_DOCS_URL:?'Github Docs URL variable missing.'}

info "Triggerring Github action..."

curl_output_file="/tmp/trigger-gh-$RANDOM.txt"

payload=$(jq -n \
  --arg EVENT_TYPE "${EVENT_TYPE}" \
  --arg PRODUCT_KEY "${PRODUCT_KEY}" \
  --arg DOWNLOAD_URL "${DOWNLOAD_URL}" \
'{
    "event_type": "\($EVENT_TYPE)", 
    "client_payload": 
    {
        "product_key": "\($PRODUCT_KEY)", 
        "download_url": "\($DOWNLOAD_URL)"}
}')

info "API: $GH_DOCS_URL"
info "Payload: $payload"
status_code=$(curl -s -X POST --output ${curl_output_file} -w "%{http_code}" \
  -H "Accept: application/vnd.github.everest-preview+json" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${CI_GH_TOKEN}" \
  -d "${payload}" \
  ${extra_args} \
  ${GH_DOCS_URL})

info "HTTP Status: $status_code"
response=$(cat ${curl_output_file})
debug "HTTP Response: $response"

if [[ $status_code = 204 ]]; then
  success "Trigger successful."
else
  fail "Trigger failed."
fi