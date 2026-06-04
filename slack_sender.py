import os
import time
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# files limit per message
def chunk_list(data, size=25):
    """Split list into chunks in given size"""
    for i in range(0, len(data), size):
        yield data[i:i + size]


def send_files_to_slack(
    slack_token: str,
    channel_id: str,
    file_paths: list,
    report_name: str
):
    client = WebClient(token=slack_token)

    try:
        
        # Remove previous pinned messages
        
        pins = client.pins_list(channel=channel_id)
        for item in pins.get("items", []):
            if "message" in item:
                client.pins_remove(
                    channel=channel_id,
                    timestamp=item["message"]["ts"]
                )

       
        # Prepare uploads for carousel
        
        uploads = []
        for path in file_paths:
            if os.path.exists(path):
                uploads.append({
                    "file": path,
                    "title": os.path.basename(path)
                })
            else:
                print(f"File not found: {path}")

        if not uploads:
            print("❌ No valid images to upload")
            return

        
        # Upload images (carousel, chunked)
       
        first_message_ts = None

        for idx, chunk in enumerate(chunk_list(uploads, 10)):
            response = client.files_upload_v2(
                channel=channel_id,
                initial_comment=f"*{report_name}*" if idx == 0 else None,
                file_uploads=chunk
            )
            
            # Capture timestamp from first upload only
            if idx == 0:
                files = response.get("files", [])
                if files:
                    shares = files[0].get("shares", {})

                    # Privte Channel
                    if "private" in shares and channel_id in shares["private"]:
                        first_message_ts = shares["private"][channel_id][0]["ts"]

                    # Fallback (public)
                    elif "public" in shares and channel_id in shares["public"]:
                        first_message_ts = shares["public"][channel_id][0]["ts"]

            time.sleep(1)
        # Pin the carousel message
        
        if first_message_ts:
            client.pins_add(
                channel=channel_id,
                timestamp=first_message_ts
            )

        print("✅ Sent to Slack")

    except SlackApiError as e:
        print(f"❌ Slack error: {e.response['error']}")


# Send Output Folder Images

def send_output_folder_to_slack(
    slack_token: str,
    channel_id: str,
    output_folder_path: str,
    report_name: str
):
    from slack_sdk import WebClient
    from slack_sdk.errors import SlackApiError
    import os

    client = WebClient(token=slack_token)

    try:
        if not os.path.exists(output_folder_path):
            print(f"❌ Output folder not found: {output_folder_path}")
            return

        file_paths = [
            os.path.join(output_folder_path, f)
            for f in os.listdir(output_folder_path)
            if f.lower().endswith(".png")
        ]

        if not file_paths:
            print(f"⚠️ No images found in: {output_folder_path}")
            return

        uploads = [{"file": p, "title": os.path.basename(p)} for p in file_paths]

        first_message_ts = None

        for idx, chunk in enumerate(chunk_list(uploads, 20)):
            response = client.files_upload_v2(
                channel=channel_id,
                initial_comment=f"*{report_name}*" if idx == 0 else None,
                file_uploads=chunk
            )

            if idx == 0:
                files = response.get("files", [])
                if files:
                    shares = files[0].get("shares", {})
                    if "private" in shares and channel_id in shares["private"]:
                        first_message_ts = shares["private"][channel_id][0]["ts"]
                    elif "public" in shares and channel_id in shares["public"]:
                        first_message_ts = shares["public"][channel_id][0]["ts"]

        if first_message_ts:
            client.pins_add(channel=channel_id, timestamp=first_message_ts)

        print(f"✅ Output folder sent: {output_folder_path}")

    except SlackApiError as e:
        print(f"❌ Slack error: {e.response['error']}")
