#!/bin/bash
# Trigers Azure DevOps to build .Net Framework projects
# Required:
#  BUILD_DEFINITION_NUM
#  BITBUCKET_COMMIT
#  BUILD_USERNAME
#  BUILD_PASSWORD
#  BUILD_API
#  1 - PARAMETERS

source "$(dirname "$0")/common.sh"

extra_args=""
if [[ "${DEBUG}" == "true" ]]; then
  info "Enabling debug mode."
  extra_args="--verbose"
fi

# mandatory variables
BUILD_DEFINITION_NUM=${AZURE_BUILD_DEFINITION_NUM:?'Pipeline definition ID variable missing.'}
BITBUCKET_COMMIT=${BITBUCKET_COMMIT:?'Commit hash variable missing.'}
BUILD_USERNAME=${AZURE_PIPELINES_USERNAME:?'Azure Devops Username variable missing.'}
BUILD_PASSWORD=${AZURE_PIPELINES_PASSWORD:?'Azure Devops Password variable missing.'}
BUILD_API=${AZURE_BUILD_URL:?'Azure Devops API URL variable missing.'}
BUILD_STATUS_API=${AZURE_BUILD_STATUS_URL:?'Azure Devops Build Status API URL variable missing.'}
BUILD_RESULT_URL=${AZURE_PIPELINES_RESULT_URL:?'Azure Devops Build Result URL variable missing.'}
PARAMETERS=${1:?'Parameters variable missing.'}
INITIAL_WAIT_TIME=${2:-3m}

info "Triggerring Azure DevOps pipeline..."

curl_output_file="/tmp/trigger-azure-$RANDOM.txt"

payload=$(jq -n \
  --arg BUILD_DEFINITION_NUM "${BUILD_DEFINITION_NUM}" \
  --arg BITBUCKET_COMMIT "${BITBUCKET_COMMIT}" \
  --arg PARAMETERS "${PARAMETERS}" \
'{ 
    "definition": { "id": $BUILD_DEFINITION_NUM },
    "parameters": "{ \($PARAMETERS) }", 
    "sourceVersion": $BITBUCKET_COMMIT
}')

info "API: $BUILD_API"
info "Payload: $payload"
status_code=$(curl -s -X POST -u $BUILD_USERNAME:$BUILD_PASSWORD --output ${curl_output_file} -w "%{http_code}" \
  -H "Content-Type: application/json" \
  -d "${payload}" \
  ${extra_args} \
  ${BUILD_API})

info "HTTP Status: $status_code"
response=$(cat ${curl_output_file})
debug "HTTP Response: $response"

if [[ $status_code = 200 ]]; then
  success "Trigger successful."
else
  fail "Trigger failed."
fi

build_id=$(echo $response | jq -r '.id')
info "Build ID: $build_id"
BUILD_STATUS_API=${BUILD_STATUS_API/\{buildId\}/$build_id}
info "Status API: $BUILD_STATUS_API"

info "Waiting for the Azure pipelines to finish its build."
run sleep $INITIAL_WAIT_TIME
while : ; do
    curl_output_file="/tmp/azure-pipeline-$RANDOM.txt"
    run curl -u $BUILD_USERNAME:$BUILD_PASSWORD --output ${curl_output_file} $BUILD_STATUS_API
    response=$(cat ${curl_output_file})
    debug "HTTP Response: $(echo ${response})"
    status=$(echo $response | jq -r '.status')
    debug "Status: $status"    
    [[ $status != "completed" ]] || break
    run sleep 1m
done
info "Azure pipelines build is finished."

result=$(echo $response | jq -r '.result')
debug "Result: $result"
BUILD_RESULT_URL=${BUILD_RESULT_URL/\{buildId\}/$build_id}
if [[ $result == "succeeded" ]]; then
  success "The build in Azure DevOps has succeeded. $BUILD_RESULT_URL"
else
  fail "The build in Azure DevOps has failed. Please see $BUILD_RESULT_URL for details."
fi