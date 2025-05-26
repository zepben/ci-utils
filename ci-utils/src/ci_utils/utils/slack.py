import logging
import os
import click
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# WebClient instantiates a client that can call API methods
# When using Bolt, you can use either `app.client` or the `client` passed to listeners.
client = WebClient(token=os.environ.get("SLACK_BOT_TOKEN"))
logger = logging.getLogger(__name__)


class Slack:
    def __init__(self, ctx):
        self.ctx = ctx
        self.channel = "evolve-builds"

    def send_message(self, msg: str):
        should_notify = os.getenv("SLACK_NOTIFICATION", None)
        if should_notify is None or should_notify != "YES":
            self.ctx.info("Slack notification is turned off. Please see SLACK_NOTIFICATION environment variable.")
            click.echo(msg)
            return

        # extra_args=""
        # if [[ "${DEBUG}" == "true" ]]; then
        #   info "Enabling debug mode."
        #   extra_args="--verbose"
        # fi

        # mandatory variables
        # webhook_url = os.getenv("SLACK_WEBHOOK", None)
        # if webhook_url is None:
        #     self.ctx.fail("Webhook URL SLACK_WEBHOOK variable missing")
        #
        if len(msg) == 0:
            self.ctx.fail("MESSAGE is missing.")

        self.ctx.info("Sending notification to Slack...")

        conversation_id = None
        try:
            # Call the conversations.list method using the WebClient
            for result in client.conversations_list():
                if conversation_id is not None:
                    break
                for channel in result["channels"]:
                    if channel["name"] == self.channel:
                        conversation_id = channel["id"]
                        # Print result
                        print(f"Found conversation ID: {conversation_id}")
                        break

        except SlackApiError as e:
            print(f"Error: {e}")

        # ID of channel you want to post message to

        try:
            # Call the conversations.list method using the WebClient
            GITHUB_REPOSITORY = os.getenv("GITHUB_REPOSITORY")
            GITHUB_SERVER_URL = os.getenv("GITHUB_SERVER_URL")
            GITHUB_RUN_ID = os.getenv("GITHUB_RUN_ID")
            GITHUB_RUN_NUMBER = os.getenv("GITHUB_RUN_NUMBER")
            GITHUB_REPOSITORY = os.getenv("GITHUB_REPOSITORY")
            result = client.chat_postMessage(
                attachments=[
                    {
                        "fallback": msg,
                        "color": "#439FE0",
                        "pretext": f"*<{GITHUB_SERVER_URL}/{GITHUB_REPOSITORY}>*: <{GITHUB_SERVER_URL}/{GITHUB_REPOSITORY}/actions/runs/{GITHUB_RUN_ID}|Pipeline #{GITHUB_RUN_NUMBER}>",
                        "text": msg,
                        "mrkdwn_in": ["pretext"],
                    }
                ],
                channel=conversation_id,
                text=msg,
                # You could also use a blocks[] array to send richer content
            )
            # Print result, which includes information about the message (like TS)
            self.ctx.info("Notification successful.")

        except SlackApiError as e:
            self.ctx.fail("Notification failed: ", e)
