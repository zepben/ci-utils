#!/usr/bin/env bash
#
# Send a notification to Slack, https://api.slack.com/docs/messages
#
# Required:
#  WEBHOOK_URL
#  MESSAGE

source "$(dirname "$0")/common.sh"

if [[ "${SLACK_NOTIFICATION}" != "YES" ]]; then
  info "Slack notification is turned off. Please see SLACK_NOTIFICATION environment variable."
  exit 0
fi

extra_args=""
if [[ "${DEBUG}" == "true" ]]; then
  info "Enabling debug mode."
  extra_args="--verbose"
fi

# mandatory variables
WEBHOOK_URL=${SLACK_WEBHOOK:?'Webhook URL variable missing.'}
MESSAGE=${1:?'MESSAGE variable missing.'}

info "Sending notification to Slack..."

curl_output_file="/tmp/slack-notification-$RANDOM.txt"

payload=$(jq -n \
  --arg MESSAGE "${MESSAGE}" \
  --arg BITBUCKET_WORKSPACE "${BITBUCKET_WORKSPACE}" \
  --arg BITBUCKET_REPO_SLUG "${BITBUCKET_REPO_SLUG}" \
  --arg BITBUCKET_BUILD_NUMBER "${BITBUCKET_BUILD_NUMBER}" \
  --arg BITBUCKET_REPO_FULL_NAME "${BITBUCKET_REPO_FULL_NAME}" \
'{ attachments: [
  {
    "fallback": $MESSAGE,
    "color": "#439FE0",
    "pretext": "*<https://bitbucket.org/\($BITBUCKET_REPO_FULL_NAME)|\($BITBUCKET_REPO_SLUG)>*: <https://bitbucket.org/\($BITBUCKET_WORKSPACE)/\($BITBUCKET_REPO_SLUG)/addon/pipelines/home#!/results/\($BITBUCKET_BUILD_NUMBER)|Pipeline #\($BITBUCKET_BUILD_NUMBER)>",
    "text": $MESSAGE,
    "mrkdwn_in": ["pretext"]
  }
]}')

run curl -s -X POST --output ${curl_output_file} -w "%{http_code}" \
  -H "Content-Type: application/json" \
  -d "${payload}" \
  ${extra_args} \
  ${WEBHOOK_URL}

response=$(cat ${curl_output_file})
info "HTTP Response: $(echo ${response})"

if [[ "${response}" = "ok" ]]; then
  success "Notification successful."
else
  fail "Notification failed."
fi