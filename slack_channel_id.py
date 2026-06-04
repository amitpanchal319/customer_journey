from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError


def get_channel_id_by_name(slack_token: str, channel_name: str) -> str:
    client = WebClient(token=slack_token)
    try:
        cursor = None
        while True:
            response = client.conversations_list(
                types="public_channel,private_channel",
                limit=200,
                cursor=cursor
            )

            for channel in response.get("channels", []):
                if channel.get("name") == channel_name:
                    print(f"✅ Slack channel found: #{channel_name} → {channel['id']}")
                    return channel["id"]

            cursor = response.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break

        raise ValueError(
            f"Slack channel '{channel_name}' not found. "
            f"Make sure the bot is added to the channel."
        )

    except SlackApiError as e:
        error = e.response.get("error")
        raise Exception(
            f"Slack API error while finding channel '{channel_name}': {error}"
        )
